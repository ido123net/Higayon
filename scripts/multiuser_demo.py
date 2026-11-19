"""Run two independent solver views against one disposable local Django database."""

import os
import secrets
from contextlib import ExitStack
from pathlib import Path
from socket import create_server
from tempfile import TemporaryDirectory

import django
import uvicorn
from django.conf import settings
from django.core.management import call_command
from django.template import Context, Template
from django.test import Client

PORTS = (8771, 8772)
DASHBOARD = f"http://localhost:{PORTS[0]}"
SESSION_COOKIE = "higayon_demo_session"


def seed():
    from puzzles.models import (
        AuthorizedEmail,
        ConfirmedAnswer,
        Puzzle,
        SessionMember,
        SolvingSession,
    )
    from puzzles.tests import AppTests

    call_command("migrate", verbosity=0)
    call_command("demo")
    noa, amit = (AppTests.user(f"{name}@example.invalid") for name in ("noa", "amit"))
    for user, name in ((noa, "נועה"), (amit, "עמית")):
        user.first_name = name
        user.save(update_fields=["first_name"])
    session = SolvingSession.objects.create(puzzle=Puzzle.objects.get(), creator=noa)
    tickets = []
    for user in (noa, amit):
        AuthorizedEmail.objects.create(email=user.email)
        member = SessionMember.objects.create(session=session, user=user)
        if user == amit:
            ConfirmedAnswer.objects.create(
                member=member, direction="across", number=1, answer="אבגדהוז", version=1
            )
        client = Client()
        client.force_login(user)
        tickets.append(client.cookies[SESSION_COOKIE].value)
    return f"/sessions/{session.pk}/", tickets


def demo_app(app, session_path, tickets, dashboard_html):
    async def serve(scope, receive, send):
        if scope["type"] != "http":
            return await app(scope, receive, send)
        port = scope["server"][1]
        headers = dict(scope["headers"])
        cookie_name = f"{SESSION_COOKIE}_{port}".encode()
        common = [
            (b"cache-control", b"no-store"),
            (b"content-security-policy", f"frame-ancestors {DASHBOARD}".encode()),
        ]
        if headers.get(b"host") != f"localhost:{port}".encode():
            status, content = 400, b""
        elif scope["path"] == "/" and port == PORTS[0]:
            status, content = 200, dashboard_html.encode()
            common.append((b"content-type", b"text/html; charset=utf-8"))
        elif scope["path"] == "/play/":
            status, content = 302, b""
            token = tickets[PORTS.index(port)].encode()
            common += [
                (b"location", session_path.encode()),
                (
                    b"set-cookie",
                    cookie_name + b"=" + token + b"; Path=/; HttpOnly; SameSite=Strict",
                ),
            ]
        else:
            name = SESSION_COOKIE.encode() + b"="
            cookies = headers.get(b"cookie", b"").split(b"; ")
            headers[b"cookie"] = b"; ".join(
                name + item[len(cookie_name) + 1 :] if item.startswith(cookie_name + b"=") else item
                for item in cookies
                if not item.startswith(name)
            )

            async def respond(message):
                if message["type"] == "http.response.start":
                    message["headers"] = [
                        (
                            k,
                            cookie_name + b"=" + v[len(name) :]
                            if k == b"set-cookie" and v.startswith(name)
                            else v,
                        )
                        for k, v in message["headers"]
                        if k != b"x-frame-options"
                    ] + [common[1]]
                await send(message)

            return await app({**scope, "headers": list(headers.items())}, receive, respond)
        await send({"type": "http.response.start", "status": status, "headers": common})
        await send({"type": "http.response.body", "body": content})

    return serve


def main():
    with TemporaryDirectory(prefix="higayon-demo-") as directory, ExitStack() as stack:
        os.environ.update(
            DJANGO_SETTINGS_MODULE="higayon.settings",
            DATABASE_URL=f"sqlite:///{directory}/demo.sqlite3",
            DEBUG="true",
            DJANGO_SECRET_KEY=secrets.token_urlsafe(48),
            ALLOWED_HOSTS="localhost,testserver",
            ALLOWED_EMAILS="",
            OWNER_EMAIL="",
            OWNER_API_TOKEN="",
            GOOGLE_CLIENT_ID="",
            GOOGLE_CLIENT_SECRET="",
            CSRF_TRUSTED_ORIGINS="",
            TRUST_PROXY="false",
        )
        django.setup()
        settings.SESSION_COOKIE_NAME = SESSION_COOKIE
        settings.STORAGES["staticfiles"] = {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        }
        session_path, tickets = seed()
        template = Template(Path(__file__).with_name("multiuser_demo.html").read_text())
        players = [
            {"name": name, "url": f"http://localhost:{port}/play/"}
            for name, port in zip(("נועה", "עמית"), PORTS, strict=True)
        ]
        html = template.render(Context({"players": players}))
        from higayon.asgi import application

        sockets = [stack.enter_context(create_server(("127.0.0.1", port))) for port in PORTS]
        app = demo_app(application, session_path, tickets, html)
        print(f"Two-player demo running at {DASHBOARD}/", flush=True)
        uvicorn.Server(uvicorn.Config(app, access_log=False, timeout_graceful_shutdown=2)).run(
            sockets
        )


if __name__ == "__main__":
    main()
