# Local hosting at higayon.idofrenkel.com

The app runs on this computer with Docker Compose: Gunicorn, PostgreSQL 17 and
a Cloudflare Tunnel. Cloudflare terminates public HTTPS and forwards to the app
over the private Docker network. The app keeps Google login, the allowlist,
secure cookies and CSRF checks enabled. No paid VPS or managed Kubernetes is used.

## Current setup

- `compose.local.yaml` has started the app and its persistent PostgreSQL volume.
- Existing users, verified Google account records and both puzzles were copied
  from SQLite, including the newspaper puzzle and its stable ID.
- `.local/` contains private, ignored configuration and the original SQLite
  snapshot/import fixture; it is also excluded from Docker builds. Files use
  mode 0600 and the directory uses 0700.
- Cloudflare DNS, a named tunnel token and the production Google callback still
  need to be connected before the public hostname is available.

This computer must stay awake, connected to the internet, with Docker running.
Containers restart with Docker (`unless-stopped`); enable Docker Desktop startup
at login if desired. This is a single-machine deployment: downtime or disk loss
affects the site. No offsite backup service is configured.

## 1. Private configuration

For a fresh setup, first configure the existing development `.env` with real
Google credentials, `OWNER_EMAIL` and `ALLOWED_EMAILS` (including the owner).
Do not overwrite an existing `.env`. From the repository root:

```sh
uv sync --locked
uv run --env-file .env python scripts/prepare_local.py
docker compose -f compose.local.yaml up -d --build app
```

The preparation command generates independent high-entropy deployment secrets
and a PostgreSQL password. It copies Google/allowlist values into `.local/app.env`,
creates `.local/db.env`, and creates `.local/tunnel.env` with an empty token.
It refuses to overwrite these files. Compose reads their values without shell
or `$` interpolation (`env_file.format: raw`, Compose 2.30 or later).

The deployed app uses `DEBUG=false`, PostgreSQL, `TRUST_PROXY=true`,
`ALLOWED_HOSTS=higayon.idofrenkel.com,localhost,127.0.0.1` and
`CSRF_TRUSTED_ORIGINS=https://higayon.idofrenkel.com`. A separate migration
service must finish successfully before Gunicorn starts.

PostgreSQL has no published host port. The app's diagnostic port is bound only
to `127.0.0.1:8766`; public traffic comes through Cloudflare. Do not expose that
port to the LAN/internet: forwarded protocol headers are trusted only because
the origin is private. HTTP requests without a trusted HTTPS header redirect
to HTTPS; port 8766 is not a separate browser-facing HTTPS server.

If Google credentials or the allowlist change, edit `.local/app.env` and run:

```sh
docker compose -f compose.local.yaml up -d --force-recreate app
```

Editing the development `.env` alone does not change the deployment. Rotating
`OWNER_API_TOKEN` in `.local/app.env` revokes the previous deployment API token.
Do not regenerate or change the database password without also changing the
existing PostgreSQL user's password.

## 2. Cloudflare DNS (domain registration stays at Porkbun)

1. Create a [Cloudflare account](https://dash.cloudflare.com/sign-up), add
   `idofrenkel.com` as a domain, and select the **Free** plan.
2. Review imported DNS records and preserve any email/verification records.
3. Cloudflare assigns two nameservers. At Porkbun, open the domain's nameserver
   settings and replace the Porkbun nameservers with those exact two values.
   Do not transfer the domain registration or buy another domain.
4. Wait for Cloudflare to mark the domain **Active**. If DNSSEC is enabled at
   the registrar, follow Cloudflare's nameserver-change instructions for it.

See [Cloudflare primary DNS setup](https://developers.cloudflare.com/dns/zone-setups/full-setup/setup/).
The current domain had no DS record when checked before this migration.

## 3. Named tunnel

In Cloudflare, go to **Networking → Tunnels** (or the Cloudflare One tunnel
section if shown in your account) and create a remotely managed `cloudflared`
tunnel named **higayon-local**. No paid Access plan is needed: the app already
authenticates its invited users with Google.

For the tunnel's published application route, use:

| Setting | Value |
|---|---|
| Subdomain | `higayon` |
| Domain | `idofrenkel.com` |
| Service type | `HTTP` |
| Service URL | `app:8000` (full URL `http://app:8000`) |

`app` is the app service on the connector's Docker network; `localhost` would
refer to the connector container itself. Keep the original public Host header.
Use Cloudflare's HTTPS redirect option so visitors use HTTPS.

The dashboard offers an installation command containing a long `eyJ...` token.
Copy **only the token** into `.local/tunnel.env` locally:

```dotenv
TUNNEL_TOKEN=YOUR_TUNNEL_TOKEN
```

The actual file uses the raw token without quotes. Do not paste it into chat,
put it in a command-line argument, or commit it. The connector reads it from
the environment. Then run:

```sh
docker compose -f compose.local.yaml --profile public up -d cloudflared
docker compose -f compose.local.yaml logs --tail=30 cloudflared
```

Ensure the published route creates the `higayon` DNS record pointing to the
named tunnel. If an existing parking record conflicts, replace only that
hostname's record. Preserve unrelated root, MX and TXT records. Wait for the
connector to show Healthy in Cloudflare. The app should then appear at
`https://higayon.idofrenkel.com/login/`.

Sources: [Tunnel setup](https://developers.cloudflare.com/tunnel/get-started/),
[published HTTP applications](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/routing-to-tunnel/protocols/),
[tunnel tokens](https://developers.cloudflare.com/tunnel/reference/tunnel-tokens/),
and [forwarded HTTPS headers](https://developers.cloudflare.com/fundamentals/reference/http-headers/#x-forwarded-proto).

## 4. Google OAuth callback

In the existing Google OAuth **Web application** client, add this authorized
redirect URI, keeping the current localhost URI too:

```text
https://higayon.idofrenkel.com/accounts/google/login/callback/
```

If Google's consent configuration requests an authorized domain, add
`idofrenkel.com`. If the app is in Testing, invited users must also be listed
as test users in Google. The server's existing `ALLOWED_EMAILS` restriction
still applies. Google login must be tested in a real browser after DNS/tunnel
activation; do not enable any local-login bypass.

## 5. Routine operation

```sh
docker compose -f compose.local.yaml ps
docker compose -f compose.local.yaml logs --tail=50 app
# Deploy code updates: run migrations first, then recreate the app.
docker compose -f compose.local.yaml build app
docker compose -f compose.local.yaml run --rm migrate
docker compose -f compose.local.yaml up -d app
# Stop the public connector only:
docker compose -f compose.local.yaml --profile public stop cloudflared
# Stop the whole deployment (keeps the PostgreSQL volume):
docker compose -f compose.local.yaml --profile public down
```

Do not use `down -v` unless you deliberately want to delete the deployment
database. PostgreSQL data remains in the `higayon-local_local-postgres` Docker
volume. The original SQLite database and private migration snapshot remain
available separately, but do not receive subsequent deployment edits.

The development site at `http://127.0.0.1:8765` remains a separate SQLite
environment. Browser progress is per origin and device: entries saved there
will not appear automatically at `https://higayon.idofrenkel.com`.
