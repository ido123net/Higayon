"""One PostgreSQL listener per event loop. Payloads are invalidations, never answers."""

import asyncio
import json
import logging
import os
from collections import defaultdict
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from time import monotonic
from uuid import uuid4

import psycopg
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import get_user
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import ObjectDoesNotExist
from django.db import close_old_connections, connection, transaction
from django.http import StreamingHttpResponse
from django.utils import timezone

from . import metrics
from .auth import invited
from .models import ConnectionLease, SessionMember
from .sessions import member_api, membership
from .views import error

log = logging.getLogger(__name__)
RENEW_SECONDS = 20
TTL_SECONDS = 60


class Hub:
    def __init__(self):
        self.loop = None
        self.groups = defaultdict(set)
        self.listening = None

    def deliver(self, group, event):
        for sub in self.groups.get(group, ()):
            sub.pending.add(event)
            sub.wake.set()

    @asynccontextmanager
    async def subscribe(self, group):
        sub = Subscription()
        self.groups[group].add(sub)
        try:
            yield sub
        finally:
            self.groups[group].remove(sub)
            if not self.groups[group]:
                del self.groups[group]

    async def listen(self):
        assert self.listening is not None
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(
                    os.environ["DATABASE_URL"], autocommit=True
                ) as db:
                    await db.execute("LISTEN higayon_live")
                    self.listening.set()
                    for group in tuple(self.groups):
                        self.deliver(group, "state")
                        self.deliver(group, "presence")
                    async for notice in db.notifies():
                        group, event = notice.payload.split("/", 1)
                        self.deliver(group, event)
            except (psycopg.Error, OSError):
                self.listening.clear()
                for group in tuple(self.groups):
                    self.deliver(group, "disconnected")
                log.exception("PostgreSQL live listener disconnected")
                await asyncio.sleep(1)


class Subscription:
    def __init__(self):
        self.pending = set()
        self.wake = asyncio.Event()


hub = Hub()


def publish(group, event):
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_notify('higayon_live', %s)", [f"{group}/{event}"])
    elif loop := hub.loop:
        transaction.on_commit(lambda: loop.call_soon_threadsafe(hub.deliver, str(group), event))


def renew(request, group, member_id, lease, first):
    # Re-read the login session and allowlist; the opening request may be hours old.
    request.session = SessionStore(session_key=request.COOKIES.get(settings.SESSION_COOKIE_NAME))
    request.user = get_user(request)
    if request.user.is_authenticated and not invited(request.user):
        return False
    try:
        if membership(request, group).pk != member_id:
            return False
    except ObjectDoesNotExist:
        return False
    now = timezone.now()
    with transaction.atomic():
        ConnectionLease.objects.filter(expires_at__lte=now).delete()
        updated = ConnectionLease.objects.filter(pk=lease).update(
            expires_at=now + timedelta(seconds=TTL_SECONDS)
        )
        if not updated:
            ConnectionLease.objects.create(
                pk=lease, member_id=member_id, expires_at=now + timedelta(seconds=TTL_SECONDS)
            )
        if first or not updated:
            publish(group, "presence")
    return True


def leave(group, lease):
    with transaction.atomic():
        if ConnectionLease.objects.filter(pk=lease).delete()[0]:
            publish(group, "presence")


def roster(group, member_id):
    members = (
        SessionMember.objects.filter(session_id=group, leases__expires_at__gt=timezone.now())
        .order_by("pk")
        .values_list("pk", "guest_name", "user__first_name")
        .distinct()
    )
    return [
        {"name": guest or first or "משתתף", "me": pk == member_id} for pk, guest, first in members
    ]


@sync_to_async
def stream_query(operation, *args):
    try:
        return operation(*args)
    finally:
        close_old_connections()


def frame(event, data=None):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def stream(request, group, member_id):
    lease = uuid4()
    previous = None
    async with hub.subscribe(str(group)) as sub:
        if hub.listening is not None:
            await hub.listening.wait()
        metrics.connections.inc()
        try:
            deadline = 0
            first = True
            while True:
                events = sub.pending.copy()
                sub.pending.clear()
                sub.wake.clear()
                if "disconnected" in events:
                    return
                if monotonic() >= deadline:
                    if not await stream_query(renew, request, group, member_id, lease, first):
                        yield frame("revoked")
                        return
                    deadline = monotonic() + RENEW_SECONDS
                    events.add("presence")
                    yield ": heartbeat\n\n"
                if first or "state" in events:
                    yield frame("state")
                if "presence" in events:
                    names = await stream_query(roster, group, member_id)
                    if names != previous:
                        yield frame("presence", names)
                        previous = names
                first = False
                with suppress(TimeoutError):
                    await asyncio.wait_for(sub.wake.wait(), max(0, deadline - monotonic()))
        finally:
            metrics.connections.dec()
            await asyncio.shield(stream_query(leave, group, lease))


@member_api
def events(request, session_id):
    if request.method != "GET":
        return error("פעולה זו אינה נתמכת.", 405)
    member = membership(request, session_id)
    return StreamingHttpResponse(
        stream(request, session_id, member.pk),
        content_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "private, no-store"},
    )
