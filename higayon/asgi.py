import asyncio
import os
from contextlib import suppress
from time import monotonic

from django.conf import settings
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from django.core.asgi import get_asgi_application
from prometheus_client import start_http_server

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "higayon.settings")
django_app = get_asgi_application()

if settings.DEBUG:
    django_app = ASGIStaticFilesHandler(django_app)

from puzzles import metrics
from puzzles.events import hub


async def application(scope, receive, send):
    if scope["type"] == "lifespan":
        await receive()
        hub.loop = asyncio.get_running_loop()
        listener = None
        if settings.DATABASES["default"]["ENGINE"].endswith("postgresql"):
            hub.listening = asyncio.Event()
            listener = asyncio.create_task(hub.listen())
        server = None
        if port := os.getenv("METRICS_PORT"):
            metrics.players.set_function(metrics.connected_players)
            server, _ = start_http_server(int(port))
        await send({"type": "lifespan.startup.complete"})
        try:
            await receive()
        finally:
            if listener:
                listener.cancel()
                with suppress(asyncio.CancelledError):
                    await listener
            if server:
                server.shutdown()
                server.server_close()
            hub.loop = None
            hub.listening = None
        await send({"type": "lifespan.shutdown.complete"})
        return

    start = monotonic()
    measured = not scope["path"].startswith(("/static/", "/health/"))

    async def record(message):
        if measured and message["type"] == "http.response.start":
            status = message["status"]
            metrics.requests.labels(f"{status // 100}xx").inc()
            metrics.latency.observe(monotonic() - start)
            if status >= 400 and scope["path"].endswith("/answers/"):
                metrics.sync_failures.inc()
        await send(message)

    await django_app(scope, receive, record)
