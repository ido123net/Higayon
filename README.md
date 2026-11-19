# higayon

Private, Hebrew, RTL cryptic crosswords built with Django 5.2 LTS, templates and vanilla JavaScript. The canonical 11×11 Dyokan layout is code in `puzzles/grid.py`; no layout editor, import, AI, answer checking or hints. Optional shared sessions let authorized friends solve independently and share completion counts. Optional solutions stay server-side and are never sent to solvers. Draft progress stays in this browser, separated by user and puzzle or shared session. Clearing site data deletes drafts. Complete session answers sync to the server after a 250 ms typing pause. Storage failures show a Hebrew notice.

## Local startup (uv / SQLite)

```sh
uv sync --locked
cp .env.example .env
# First setup only: keep your existing .env if it is already configured.
# Edit .env, then load it explicitly for each command:
uv run --env-file .env python manage.py migrate
uv run --env-file .env uvicorn higayon.asgi:application --port 8765
# Optional, clearly labeled synthetic puzzle:
uv run --env-file .env python manage.py demo
```

Python 3.12 is pinned in `.python-version`. Use DEBUG=true only for local development. Public deployments require DEBUG=false, PostgreSQL and DJANGO_SECRET_KEY, and use HTTPS redirects and secure cookies. Google sign-in requires configured client credentials and an allowlisted, verified email. There is no local-login bypass or public signup. The owner manages invited email addresses in the Google-protected Django admin at `/admin/`.

## Try two players in one browser

Run `uv run python -m scripts.multiuser_demo` and open [the local two-player demo](http://localhost:8771/).
The page shows Noa and Amit solving the same sample puzzle side by side, with independent drafts.
Amit has already completed 1 across. Fill that clue in Noa’s board to see its green check.
Amit’s clue count updates live. The people button beside the title opens the connected-player list. Each board also has a link to open it in a full tab.

The demo binds to loopback ports 8771 and 8772 and uses a temporary SQLite database and two test identities.
Stop it with Ctrl+C and rerun the command for a fresh session. No Google credentials or `.env` file are needed.

## Host at home with a public domain

The local deployment uses Docker Compose, PostgreSQL, Gunicorn and a Cloudflare
Tunnel for `https://higayon.idofrenkel.com`. No VPS, Kubernetes cluster or router
port forwarding is required. See [the local deployment guide](docs/LOCAL_DEPLOYMENT.md)
for the private configuration, DNS, Google callback and tunnel setup.

```sh
# First setup only; reads your configured Google/owner values from .env:
uv run --env-file .env python scripts/prepare_local.py
docker compose -f compose.local.yaml up -d --build app
# After configuring the named tunnel and .local/tunnel.env:
docker compose -f compose.local.yaml --profile public up -d cloudflared
```

The app and PostgreSQL have been started locally, with the existing accounts and
puzzles copied into the new persistent database. Cloudflare DNS/tunnel and the
Google callback must be configured before the public domain works. Keep the
computer awake with Docker running. The separate development site on port 8765
uses SQLite; subsequent edits there do not sync to the deployment database.

For PostgreSQL development: `docker compose up -d db`, set `DATABASE_URL=postgresql://higayon:local-only@localhost:5432/higayon`, then run migrations and the server normally. The Compose password is for local development only. Without DATABASE_URL, SQLite is used.

## Google and access configuration

Create a Google OAuth **Web application** client, configure the consent screen and test users if appropriate. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET. Authorized redirect URI is `http://127.0.0.1:8765/accounts/google/login/callback/` locally (use the same host in your browser), and `https://higayon.idofrenkel.com/accounts/google/login/callback/` for the local public deployment (or `https://YOUR_HOST/accounts/google/login/callback/` elsewhere). django-allauth handles OAuth state, exchange and provider validation. Its social adapter requires Google's verified email and the configured allowlist before login. Every page/API read checks verified Google account membership again, so removing an address revokes current session access on its next request.

Set OWNER_EMAIL explicitly and include it in comma-separated ALLOWED_EMAILS. On the first migration, this list seeds the database allowlist. Owner status is never assigned from signup order: the configured owner email becomes an administrator only after a verified Google sign-in. Open `/admin/` with that Google account to add or remove invited email addresses without restarting the app. Only the owner sees `/editor/` and can write puzzle definitions via the API. Authorized participants may sync their own completed session answers.

Generate a token with `uv run python -c 'import secrets; print(secrets.token_urlsafe(48))'` and put it in server-side OWNER_API_TOKEN, never browser code or git. A missing token disables bearer auth. Rotate this secret and restart all replicas to replace/revoke it; there is one owner token. Browser writes use sessions plus CSRF. Production token use requires HTTPS. See [API schemas, complete payloads and curl](docs/API.md).

Configuration: `.env.example` lists all variables. Set ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, DEBUG=false, TRUST_PROXY=true only behind a trusted ingress that replaces X-Forwarded-Proto. Google secrets, database URL, token and Django secret belong in a runtime secret. Do not expose the application service outside that trusted proxy.

## Checks

```sh
DEBUG=true uv run python manage.py check
DEBUG=true uv run python manage.py makemigrations --check --dry-run
DEBUG=true uv run python manage.py test
uv run ruff check .
uv run ruff format --check .
uv run ty check
node --test tests/browser-units.mjs
DEBUG=true uv run python tests/browser_smoke.py
uv run pre-commit install  # once this directory is a git checkout
uv run pre-commit run --all-files
```

The browser smoke test runs its own temporary test database and server, creates Google-backed test sessions directly through Django test helpers, and launches installed Chrome. It adds no application authentication bypass. Real Google login still needs credentials. See [verification notes](docs/VERIFICATION.md) for actual runs and limits.

## Container

```sh
docker build -t higayon:local .
docker run --rm --env-file .env -p 8000:8000 higayon:local
# Production database migrations are an explicit step:
docker run --rm --env-file .env higayon:local python manage.py migrate --noinput
```

The image installs the locked runtime dependencies, collects WhiteNoise static files and runs Gunicorn as a non-root user. Use external PostgreSQL for deployment. Docker's localhost is the container itself; configure DATABASE_URL accordingly.

## Kubernetes deployment

The personal K3s cluster is hosted on a single AWS EC2 instance. The shared
infrastructure repository manages K3s, Traefik, cert-manager and the Let's
Encrypt issuers. This app repository manages Higayon and its optional
single-node PostgreSQL database. A managed database is not provisioned.

For this hobby deployment, `infra/kubernetes/postgres.yaml` creates PostgreSQL
17 on K3s `local-path` storage (10 GiB on the encrypted EC2 root disk). That
volume survives pod restarts but is not an offsite backup and will be lost with
the host. Offsite backups are currently disabled. To use an external PostgreSQL
instead, skip the manifest and set `DATABASE_URL` to that database.

Build the app image for the EC2 host's amd64 architecture and transfer it to
the cluster, or push it to a registry accessible to K3s. Create the namespace
and PostgreSQL secret out of band, then apply the database manifest. The
runtime secret contains only server-side values (`DJANGO_SECRET_KEY`,
`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `OWNER_API_TOKEN`, and `DATABASE_URL`)
and stays outside Terraform and Git:

```sh
kubectl create namespace higayon
kubectl -n higayon create secret generic higayon-postgres-auth --from-env-file=/secure/path/postgres.env
kubectl apply -f infra/kubernetes/postgres.yaml
# Wait until the StatefulSet is ready before deploying the app.
kubectl -n higayon rollout status statefulset/higayon-postgres --timeout=300s
kubectl -n higayon create secret generic higayon-runtime --from-env-file=/secure/path/runtime.env
```

Terraform manages the Higayon namespace, configuration, Services, Ingress and
monitoring dashboards. Set the cluster connection, hostname, ingress class,
TLS issuer and allowed emails in an ignored tfvars file. Import the namespace
if it already exists. The Kubernetes Deployment and migration Jobs are
application release resources. For a new installation, customize
`infra/kubernetes/app.yaml` for the target cluster. Run its migration Job and
wait for success before applying the Deployment. Choose one owner for the
shared resources before applying the ConfigMap, Services or Ingress from the
plain manifest. GitHub promotions update an existing Deployment.

Readiness checks database availability, liveness checks the process. WhiteNoise serves collected assets. Migrations use the same external PostgreSQL connection and image as the application; replicas never run migrations on startup. For secret rotation, update the existing Secret outside Terraform, then `kubectl -n higayon rollout restart deployment/higayon`.

Configuration was checked against the official [django-allauth Google provider guide](https://docs.allauth.org/en/latest/socialaccount/providers/google.html), [adapter hooks](https://docs.allauth.org/en/latest/socialaccount/adapter.html), and [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).


## Solve together

Sign in with an authorized Google account and select **לפתור ביחד** in the puzzle menu.
The group opens on a sharing screen. Select **העתקת קישור** to copy its invitation,
or **מעבר לתשבץ** to start solving. A visitor opening the invitation can sign in
with Google or enter a name and select **הצטרפות כאורח**. The guest membership
belongs to that browser session. Someone using the same name in another browser
gets an independent board. Guests can solve only groups they joined via an invitation.
Clearing the session cookie loses access to the previous guest identity.

Filling the last cell marks a clue complete immediately, including words completed by crossings.
After a 250 ms typing pause, the browser sends affected complete answers and withdrawals in one versioned batch. Partial letters stay local. An authenticated event stream tells group members when to refresh their own state. Each connected member appears once in the group header across their tabs. Membership and login are rechecked every 20 seconds. Lost connections expire after 60 seconds.

Drafts and queued edits survive a refresh. Reopening a session resumes pending sync.
Transient failures retry with backoff. If another device changed the same clue, the local
draft is kept and a further edit is required to replace the newer answer. Independent puzzles
save only in the browser.

Creators can revoke the invitation from the session menu. The owner can manage
sessions and membership at `/admin/`. Revoking a link prevents new joins but does
not remove existing participants. The session migration is additive and never
uploads existing browser progress. Run `uv run --env-file .env python manage.py
migrate` before starting the updated app; container deployments must run their
migration job before replacing the app.

Session HTTP endpoints and payloads are documented in [docs/API.md](docs/API.md).
Browser verification: `uv run --env-file .env python manage.py test
tests.browser_smoke.BrowserTests tests.browser_sessions.SharedBrowserTests`
(requires installed Chrome).

## Live solving and monitoring

Run `uv run python -m tests.live_solving` to exercise the live SQLite flow. Set
`LIVE_TEST_POSTGRES` to a disposable loopback PostgreSQL server to replay it across
two app processes, including process loss and lease expiry. The test creates a
uniquely named database on that server.

Production runs one Uvicorn process per pod. Each process listens on a dedicated
PostgreSQL connection. The separate internal metrics service exposes port 9091.
Terraform supplies the Usage and Health dashboards from `monitoring/dashboards`.
The personal infrastructure repository installs Prometheus and Grafana in the
application namespace. Set `live_solving=false` to serve the polling browser
during rollout or rollback. Existing open tabs continue to use the versioned API.

## CI and production releases

GitHub Actions scans Git history for secrets and runs the locked Python checks,
SQLite and PostgreSQL suites, browser and Node tests, Terraform validation, and
a container build on pull requests and main. A successful main push publishes
a public amd64 image to GHCR and stores its commit and immutable digest in the
`release-metadata` workflow artifact for 90 days. The build context contains
only the application files and dependency manifests. Supply production values
through the Kubernetes runtime Secret at deployment. To promote an older
image, retain the corresponding successful workflow run and artifact.

Production releases use the manually dispatched **Promote production** workflow
on `main`. Enter a successful **CI and image** main-branch workflow run ID. The
workflow verifies the recorded commit and digest and serializes deployments.
A GitHub-hosted runner uses AWS OIDC and the Systems Manager session document
`Higayon-K3sTunnel` to reach the K3s API on port 6443 through local port 6445.

### Configure production access

- Restrict the GitHub `production` environment to `main`. The AWS deployment
  role trusts that environment. Its Session Manager policy grants access to
  the production instance and the fixed-port tunnel document.
- Apply `kubectl apply -f infra/kubernetes/github-deploy.yaml` as an operator.
  Store a token for the `higayon-github-deploy` service account as
  `HIGAYON_KUBE_TOKEN` in the GitHub `production` environment. Set
  `HIGAYON_KUBE_CA_DATA` to the base64 `certificate-authority-data` from the
  production kubeconfig. Use `kubectl -n higayon create token
  higayon-github-deploy --duration=24h` to issue a token and refresh the
  environment secret before its actual expiration. The API server can cap the
  requested lifetime. A fresh token can be used for each manual promotion.
- The public package allows anonymous image pulls. The first promotion with
  this setup removes the old `higayon-ghcr` reference. Once it succeeds and
  the old pods are gone, revoke the old classic token and remove the unused
  registry Secret.

### Hand off the existing Deployment

For an installation where Terraform previously owned the app Deployment and
migration Job, take a protected backup of the Terraform state, then review a
plan using the existing production tfvars. Remove obsolete values for image,
release, resources, replicas, runtime secret name, image pull secret name and
live solving from the tfvars. Those values now belong to the Kubernetes pod
configuration. The two `removed` blocks should show Terraform relinquishing
ownership without deleting either live object. Apply that reviewed handoff
before the first promotion. Keep Terraform state in the existing operator
environment.

### Release failure and rollback

The workflow creates a migration Job from the live app container configuration,
using the requested public image digest. The app
image changes only after the Job succeeds. If a migration fails, inspect its
logs in Actions or via `kubectl -n higayon logs job/JOB`. Fix the issue and
trigger another promotion. Migration Jobs are retained for 24 hours.

If the new app fails to become ready, inspect the Deployment and pod events.
Promote an earlier successful run with retained image metadata to revert the
app version. Application rollback does not reverse database migrations.
