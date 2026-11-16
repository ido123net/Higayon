# higayon

Private, Hebrew, RTL cryptic crosswords built with Django 5.2 LTS, templates and vanilla JavaScript. The canonical 11×11 Dyokan layout is code in `puzzles/grid.py`; no layout editor, import, AI, checking, hints or multiplayer. Optional solutions stay server-side and are never sent to solvers. Each user's progress stays in this browser, separately per account and puzzle. Clearing site data deletes it; it does not travel between devices. Storage failures show a Hebrew notice.

## Local startup (uv / SQLite)

```sh
uv sync --locked
cp .env.example .env
# Edit .env, then export it (this project does not implicitly load dotenv):
set -a; source .env; set +a
uv run python manage.py migrate
uv run python manage.py runserver
# Optional, clearly labeled synthetic puzzle:
uv run python manage.py demo
```

Python 3.12 is pinned in `.python-version`. Never deploy with DEBUG=true. With DEBUG=false the app requires DJANGO_SECRET_KEY and uses HTTPS redirects and secure cookies. Google sign-in requires configured client credentials and an allowlisted, verified email. There is no local-login bypass. There is no admin site or public signup.

For PostgreSQL development: `docker compose up -d db`, set `DATABASE_URL=postgresql://higayon:local-only@localhost:5432/higayon`, then run migrations and the server normally. The Compose password is for local development only. Without DATABASE_URL, SQLite is used.

## Google and access configuration

Create a Google OAuth **Web application** client, configure the consent screen and test users if appropriate. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET. Authorized redirect URI is `http://127.0.0.1:8000/accounts/google/login/callback/` locally (use the same host in your browser), and `https://YOUR_HOST/accounts/google/login/callback/` in production. django-allauth handles OAuth state, exchange and provider validation. Its social adapter requires Google's verified email and the configured allowlist before login. Every page/API read checks verified Google account membership again, so removing an address revokes current session access on its next request.

Set OWNER_EMAIL explicitly and include it in comma-separated ALLOWED_EMAILS. Owner status is never assigned from signup order. Invite friends by adding verified Google addresses to ALLOWED_EMAILS and restarting the app. Only the owner sees `/editor/` and can write via the API.

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

## Existing Kubernetes cluster

No cloud, network, cluster, database, ingress controller, registry, certificate issuer or DNS resources are provisioned. Supply an existing cluster/context, reachable PostgreSQL database, image registry access, ingress controller, DNS record, and existing TLS secret. Build/push an immutable image tag first. Database backups and cluster secret encryption are the operator's responsibility.

Create namespace and runtime secret out of band before deployment. Use a protected temporary env file containing only DJANGO_SECRET_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, OWNER_API_TOKEN and DATABASE_URL (`postgresql://...`, URL-encode credentials). Do not commit that file:

```sh
kubectl create namespace higayon
kubectl -n higayon create secret generic higayon-runtime --from-env-file=/secure/path/runtime.env
# Provision your certificate as existing Secret higayon-tls in this namespace.
```

Two equivalent deployment paths:

* **Terraform**: `cd infra/terraform`; `terraform init`; copy `example.tfvars` to a local ignored `.tfvars`, edit image, namespace, hostname, context, ingress class, TLS/runtime secret references and resources. If the namespace exists, `terraform import kubernetes_namespace_v1.app higayon`. Run `terraform fmt -check`, `terraform validate`, `terraform plan -var-file=local.tfvars`, then apply after reviewing the plan. The provider uses the existing kubeconfig context. No secret values are passed to Terraform or read into its state. Change `release` for each image rollout: the migration Job completes before Deployment changes. Preserve its completed Job until the next release. Existing secret names must match the chosen namespace.
* **Plain manifests**: customize `infra/kubernetes/app.yaml` (all placeholders, namespace, resources, config and image in both Job and Deployment). Apply Namespace/ConfigMap/Job first; wait with `kubectl -n higayon wait --for=condition=complete job/higayon-migrate-v1 --timeout=600s`; then apply Deployment/Service/Ingress. On later releases use a new migration Job name and wait before rolling out the new image. Do not blindly apply all resources concurrently to an unmigrated database.

Readiness checks database availability, liveness checks the process. WhiteNoise serves collected assets. Migrations use the same external PostgreSQL connection and image as the application; replicas never run migrations on startup. For secret rotation, update the existing Secret outside Terraform, then `kubectl -n higayon rollout restart deployment/higayon`.

Configuration was checked against the official [django-allauth Google provider guide](https://docs.allauth.org/en/latest/socialaccount/providers/google.html), [adapter hooks](https://docs.allauth.org/en/latest/socialaccount/adapter.html), and [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).
