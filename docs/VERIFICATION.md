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
