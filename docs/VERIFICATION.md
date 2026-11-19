# Verification — 2026-11-16

Implemented and run locally:

- SQLite migrations, Django system checks and migration-drift check pass.
- All 8 backend tests pass on SQLite **and PostgreSQL 17** (temporary Docker database). They cover exact template geometry, all 24 slots and playable-cell coverage, final letters, required/duplicate slots, types and groups, atomic rejection, immutable timestamps and deterministic latest ordering, allowlist and verified Google identity restrictions, owner permissions, optional solution privacy, normalized keys, bearer authentication, disabled/invalid tokens, session CSRF, and malformed/oversized JSON requests.
- All 4 JavaScript unit tests pass: Hebrew filtering/normalization, word boundaries/overwriting/deletion, per-user/per-puzzle storage restoration and unavailable-storage feedback.
- Chrome browser smoke test passes with an isolated Django test database. It verifies the 121 physical grid cells and 21 numbers, intersection direction switching, native input/composition commits, Hebrew normalization, backspace, grouped-length isolation, refresh restoration, puzzle switching, account separation, owner creation through the API, Hebrew server validation with input retained after a failed save, an in-flight puzzle switch with a failed response, and editor controls locked throughout an in-flight save. Test users/sessions are created only in the test database; no production login bypass exists.
- Phone 375×812 and desktop 1280×900 screenshots were inspected. A narrow 320×400 viewport checks for horizontal overflow and active-clue visibility. Reference HEIC was decoded with a temporary development tool; its grid and numbering visually match the canonical transcription. The photo and decoding packages are not application assets or dependencies.
- Ruff lint, Ruff formatting and ty pass. All three configured pre-commit hooks were run successfully using a temporary Git index because the initial directory was not a Git checkout. The repository itself was not initialized or committed.
- Docker image builds successfully. Production `manage.py check --deploy` reports no issues. Gunicorn readiness reaches the external PostgreSQL test container; collected solver JS is served successfully by WhiteNoise. Temporary app and database containers were stopped after verification.
- Terraform 1.13.5 formatting, initialization and validation pass with Kubernetes provider 2.38.0. The provider lock includes Linux amd64/arm64 and macOS arm64 checksums. No Terraform apply or real cluster deployment was performed. Plain Kubernetes YAML was parsed and checked against the same service/configuration design; API-server validation remains an operator step.

Limitations: no real Google OAuth exchange was run because client credentials were not supplied. Real iOS/Android devices and their native keyboard viewport behavior were not tested; Chrome emulation and composition/beforeinput handling do not substitute for that final device check. No real ingress, TLS, DNS, or existing Kubernetes context was supplied or deployed. Production database connectivity/permissions and secret provisioning remain deployment tasks.

## Google-only browser login

The temporary local-login option was removed at the user's request after Google credentials were configured. A regression test verifies the old preview account cannot access pages or the API, even with its old session and an allowlisted email, and the removed login URL returns 404.

## Local public deployment preparation

- `compose.local.yaml` builds and starts Gunicorn and PostgreSQL 17, with explicit
  migration completion before app startup and a persistent database volume.
  Database and app health checks pass. The database has no published port; the
  diagnostic app port binds only to 127.0.0.1:8766.
- The existing SQLite database was snapshotted locally; 54 user, verified Google
  identity and puzzle objects were imported into PostgreSQL. The photographed
  puzzle remains the latest, with its original UUID and all 24 clues. The
  original SQLite database remains unchanged.
- All 11 tests pass on both SQLite and PostgreSQL, including private config
  permissions, literal secret preservation, refusal to overwrite deployment
  credentials, and rejection of injected newlines/invalid owner configuration.
  Ruff, formatting, ty, all 4 JS unit tests, and the Chrome browser smoke test pass.
- Production `manage.py check --deploy` passes with DEBUG=false. HTTP checks
  through the private origin with forwarded HTTPS headers return 200 for login,
  readiness and collected solver JS; anonymous API reads return 401, while a
  server-side owner-token read returns the actual puzzle with no solutions and
  private/no-store cache headers. Google login generates the expected HTTPS
  callback for higayon.idofrenkel.com; no real OAuth exchange was performed.
- Both Compose configurations (including the optional public tunnel profile)
  validate. `.local/`, the development `.env` and SQLite are absent from the built
  image. Cloudflared and PostgreSQL images are pinned by manifest digest.

Pending: Cloudflare domain activation and tunnel connection, the public Google
OAuth redirect registration, and an end-to-end public HTTPS/Google login check.
The local development server remains available separately at 127.0.0.1:8765.


## Shared sessions — 2026-11-18

- The backend suite passes on SQLite (the PostgreSQL row-lock concurrency test
  is skipped) and PostgreSQL 17 (all 19 tests pass). Session tests cover explicit
  joins, membership isolation, private answer reads, counts, normalization,
  atomic validation, withdrawal tombstones, stale versions, link revocation,
  account revocation, CSRF, and rejection of player operations via owner tokens.
- A PostgreSQL test issues two simultaneous first confirmations for one member:
  exactly one succeeds and the other receives 409, leaving version one.
- The Chrome shared-session test uses two browser contexts and advances their
  ten-second clocks independently. It checks immediate completion, batched updates
  and withdrawals across crossings, private letters, counts after the next read,
  reload with pending edits, offline retry, version conflicts, and desktop list scrolling.
- Shared solver phone (375×812) and desktop (1280×900) screenshots were inspected.
  Real mobile keyboards and a live Google OAuth exchange were not tested for
  this change; browser contexts use verified Google-backed test users.
- This feature adds an additive migration and changes application assets. The
  deployment must complete its migration job before rolling out the new app.

## Live solving and dashboards · 2026-11-19

Playwright used independent registered and guest sessions. With two ASGI processes
on PostgreSQL, a crossing completion propagated in 0.43 s and its withdrawal in
0.39 s. With one process on SQLite the times were 0.32 s and 0.28 s. The tests
checked no state reads over an idle polling interval, private partial letters,
atomic crossing changes, offline reload/retry, edits during a POST, duplicate
tabs, keyboard roster access, and revoked membership. Killing the PostgreSQL-backed
app process exercised lease expiry and automatic recovery after restart.

The production check opened two guest browsers through the existing HTTPS
Traefik ingress. A completion propagated in 0.70 s and its withdrawal in 0.81 s.
Prometheus recorded one completion, one revision, one withdrawal, two guest
joins, two connected memberships and 16 simultaneous event streams. Both gauges
returned to zero after the browsers closed. During the test the node had 2,025
MiB of available memory and 29 GiB of free disk. All 12 dashboard queries
evaluated successfully. Test group data was removed after verification.

The owner verified Google access through the private Grafana preview and confirmed
that a second account was denied. After that check, the Grafana ingress was enabled.
The deployed app returns HTTP 401 for an unauthenticated dashboard API request
and redirects Google login to the registered production callback.

Public DNS for `grafana.idofrenkel.com` resolved to the K3s node. Through that
hostname, HTTPS validated with a Let's Encrypt certificate, the health API
returned 200, both dashboards redirected signed-out visitors to login, and the
dashboard API returned 401. Google sign-in used the public callback.
