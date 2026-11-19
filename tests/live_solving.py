"""Run with uv run python -m tests.live_solving; optionally supply a local PostgreSQL URL."""

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from socket import create_server
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen
from uuid import uuid4

import django
import psycopg
from playwright.sync_api import expect, sync_playwright
from psycopg import sql


def port():
    with create_server(("127.0.0.1", 0)) as sock:
        return sock.getsockname()[1]


def start(number, stack):
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "higayon.asgi:application",
            "--port",
            str(number),
            "--no-access-log",
            "--timeout-graceful-shutdown",
            "2",
        ]
    )

    def stop():
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)

    stack.callback(stop)
    url = f"http://127.0.0.1:{number}"
    for _ in range(100):
        try:
            with urlopen(url + "/health/live/", timeout=1):
                return proc, url
        except OSError:
            if proc.poll() is not None:
                break
            time.sleep(0.05)
    raise RuntimeError("ASGI server failed to start")


def run(db_url, stack):
    os.environ.update(
        DATABASE_URL=db_url,
        DEBUG="true",
        OWNER_EMAIL="owner@example.com",
        DJANGO_SETTINGS_MODULE="higayon.settings",
        LIVE_SOLVING="true",
    )
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.test import Client

    from puzzles.domain import save_puzzle
    from puzzles.models import SessionMember
    from puzzles.tests import AppTests, payload

    call_command("migrate", verbosity=0)
    call_command("collectstatic", interactive=False, verbosity=0)
    owner = AppTests.user(settings.OWNER_EMAIL)
    owner.first_name = "עידו"
    owner.save()
    client = Client()
    client.force_login(owner)
    login = client.cookies[settings.SESSION_COOKIE_NAME].value
    group = client.post(
        "/api/v1/sessions/",
        {"puzzle_id": str(save_puzzle(payload()).pk)},
        content_type="application/json",
    ).json()
    pg = db_url.startswith("postgres")
    number = port()
    server, primary = start(number, stack)
    secondary = start(port(), stack)[1] if pg else primary
    path = "/sessions/" + group["id"] + "/"
    state_path = "/api/v1" + path
    with sync_playwright() as pw, ThreadPoolExecutor(max_workers=1) as pool:
        browser = pw.chromium.launch(channel="chrome")
        registered = browser.new_context()
        registered.add_cookies(
            [{"name": settings.SESSION_COOKIE_NAME, "value": login, "url": primary}]
        )
        page = registered.new_page()
        page.goto(primary + path)
        expect(page.locator("#presence-count")).to_have_text("1")
        guest = browser.new_context().new_page()
        guest.goto(secondary + urlsplit(group["invite_url"]).path)
        guest.get_by_label("השם שלך במפגש").fill("נועה")
        guest.get_by_role("button", name="הצטרפות כאורח").click()
        for tab in (page, guest):
            expect(tab.locator("#presence-count")).to_have_text("2")
        guest.locator("#show-roster").focus()
        guest.keyboard.press("Enter")
        expect(guest.locator("#roster-names")).to_have_text("עידונועה (אני)")
        guest.keyboard.press("Escape")
        expect(guest.locator("#roster")).to_be_hidden()
        duplicate = registered.new_page()
        duplicate.goto(primary + path)
        expect(duplicate.locator("#presence-count")).to_have_text("2")
        duplicate.close()
        reads, writes = [], []
        guest.on("request", lambda r: reads.append(r.url) if r.url.endswith(state_path) else None)
        page.on(
            "request",
            lambda r: (
                writes.append((r.post_data_json or {})["changes"])
                if r.url.endswith("/answers/")
                else None
            ),
        )
        across = page.locator("#across .clue").first
        entry = page.locator("#entry")
        across.click()
        entry.fill("אב")
        page.wait_for_timeout(10500)
        assert reads == [] and writes == []
        started = time.monotonic()
        entry.fill("גדהוז")
        page.locator("#down .clue").first.click()
        entry.fill("אבגדה")
        badge = guest.locator("#across .count-value").first
        expect(badge).to_have_text("1", timeout=1000)
        elapsed = time.monotonic() - started
        assert elapsed < 1 and len(writes) == 1 and len(writes[0]) == 2
        assert not any(guest.locator(".letter").all_text_contents())
        print(f"Completion with crossing: {elapsed:.3f}s", flush=True)
        across.click()
        started = time.monotonic()
        entry.press("Delete")
        expect(badge).to_have_text("0", timeout=1000)
        elapsed = time.monotonic() - started
        assert elapsed < 1 and [change["answer"] for change in writes[-1]] == [None, None]
        print(f"Withdrawal: {elapsed:.3f}s", flush=True)
        route = "**/answers/"
        page.route(route, lambda r: r.abort())
        across.click()
        entry.fill("ח")
        expect(page.locator("#sync-status")).to_contain_text("אין חיבור")
        page.reload()
        expect(page.locator("#sync-status")).to_contain_text("אין חיבור")
        page.unroute(route)
        expect(badge).to_have_text("1")
        held = []
        page.route(route, lambda r: held.append(r))
        across.click()
        entry.fill("ק")
        page.wait_for_timeout(400)
        assert held
        across.click()
        entry.fill("ר")
        held.pop().continue_()
        page.unroute(route)
        page.wait_for_function(
            """async path => (await (await fetch(path)).json()).own['across:1'].answer === 'רבגדהוז'""",
            arg=state_path,
            polling=100,
        )

        if pg:
            server.kill()
            server.wait()
            expect(page.locator("#presence-count")).to_have_text("…")
            expect(guest.locator("#presence-count")).to_have_text("1", timeout=82000)
            start(number, stack)
            expect(page.locator("#presence-count")).to_have_text("2", timeout=15000)
            expect(guest.locator("#presence-count")).to_have_text("2")
        pool.submit(lambda: SessionMember.objects.filter(user__isnull=True).delete()).result()
        expect(guest.locator("#presence-status")).to_have_text(
            "הגישה למפגש הסתיימה.", timeout=22000
        )
        expect(page.locator("#presence-count")).to_have_text("1", timeout=22000)
        browser.close()


if __name__ == "__main__":
    with TemporaryDirectory() as tmp, ExitStack() as resources:
        url = f"sqlite:///{tmp}/stream.sqlite3"
        if pg_url := os.getenv("LIVE_TEST_POSTGRES"):
            parts = urlsplit(pg_url)
            assert parts.hostname in {"localhost", "127.0.0.1"}
            name = "live_test_" + uuid4().hex
            with psycopg.connect(pg_url, autocommit=True) as admin:
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            url = urlunsplit(parts._replace(path="/" + name))
        run(url, resources)
