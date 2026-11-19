"""Bounded, application-wide measurements. No URL or identity labels."""

from prometheus_client import Counter, Gauge, Histogram

groups = Counter("higayon_groups", "Solving groups created")
joins = Counter("higayon_joins", "New memberships including group creators", ["kind"])
edits = Counter("higayon_clue_edits", "Committed answer transitions", ["action"])
connections = Gauge("higayon_live_connections", "Open event streams in this process")
players = Gauge("higayon_connected_players", "Distinct active group memberships across replicas")
requests = Counter("higayon_requests", "Application HTTP responses", ["status_class"])
latency = Histogram("higayon_request_duration_seconds", "Application time to response headers")
sync_failures = Counter("higayon_sync_failures", "Unsuccessful answer requests seen by the server")
conflicts = Counter("higayon_version_conflicts", "Answer batches rejected for a stale version")
for kind in ("guest", "registered"):
    joins.labels(kind)
for action in ("completion", "revision", "withdrawal"):
    edits.labels(action)


def connected_players():
    from django.db import connections
    from django.utils import timezone

    from .models import ConnectionLease

    try:
        return (
            ConnectionLease.objects.filter(expires_at__gt=timezone.now())
            .values("member_id")
            .distinct()
            .count()
        )
    finally:
        connections.close_all()
