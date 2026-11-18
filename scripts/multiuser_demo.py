"""Run two independent solver views against one disposable local Django database."""

import os
import secrets
from contextlib import ExitStack
from pathlib import Path
from socketserver import ThreadingMixIn
from tempfile import TemporaryDirectory
from threading import Thread
from wsgiref.simple_server import WSGIServer, make_server

import django
from django.conf import settings
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application
from django.http import HttpResponse, HttpResponseRedirect
from django.template import Context, Template
from django.test import Client

PORTS = (8771, 8772)
DASHBOARD = f"http://localhost:{PORTS[0]}"
SESSION_COOKIE = "higayon_demo_session"


class DemoServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


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


def demo_app(app, port, session_path, ticket, dashboard_html):
    # Cookies are shared across localhost ports. Give each player's cookie its own name.
    cookie_name = f"{SESSION_COOKIE}_{port}"

    def serve(environ, start_response):
        if environ.get("HTTP_HOST") != f"localhost:{port}":
            response = HttpResponse(status=400)
        elif environ["PATH_INFO"] == "/" and port == PORTS[0]:
            response = HttpResponse(dashboard_html)
        elif environ["PATH_INFO"] == "/play/":
            response = HttpResponseRedirect(session_path)
            response.set_cookie(cookie_name, ticket, httponly=True, samesite="Strict")
        else:
            cookies = environ.get("HTTP_COOKIE", "").split("; ")
            environ["HTTP_COOKIE"] = "; ".join(
                cookie.replace(cookie_name + "=", SESSION_COOKIE + "=", 1)
                for cookie in cookies
                if not cookie.startswith(SESSION_COOKIE + "=")
            )

            def headers(status, items, exc_info=None):
                result = []
                for key, value in items:
                    if key.lower() == "set-cookie":
                        value = value.lstrip()
                        if value.startswith(SESSION_COOKIE + "="):
                            value = cookie_name + value[len(SESSION_COOKIE) :]
                    if key.lower() != "x-frame-options":
                        result.append((key, value))
                result.append(("Content-Security-Policy", f"frame-ancestors {DASHBOARD}"))
                return start_response(status, result, exc_info)

            return app(environ, headers)

        response["Cache-Control"] = "no-store"
        response["Content-Security-Policy"] = f"frame-ancestors {DASHBOARD}"
        start_response(
            f"{response.status_code} {response.reason_phrase}",
            [
                *response.items(),
                *(("Set-Cookie", c.OutputString()) for c in response.cookies.values()),
            ],
        )
        return [response.content]

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
        app = StaticFilesHandler(get_wsgi_application())
        servers = [
            stack.enter_context(
                make_server(
                    "127.0.0.1", port, demo_app(app, port, session_path, ticket, html), DemoServer
                )
            )
            for port, ticket in zip(PORTS, tickets, strict=True)
        ]
        Thread(target=servers[1].serve_forever, daemon=True).start()
        stack.callback(servers[1].shutdown)
        print(f"Two-player demo running at {DASHBOARD}/", flush=True)
        try:
            servers[0].serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
