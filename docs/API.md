# API v1

Puzzle-management endpoints require an allowlisted, verified Google-backed session or the configured owner bearer token. Shared-session endpoints require a Google-backed browser session. Browser writes require Django's `csrftoken` cookie in `X-CSRFToken`; same-origin only. Bearer authorization is evaluated explicitly before session auth, uses timing-safe comparison, and does not need CSRF. A bad bearer token never falls back to a session. Tokens cannot log into pages. There are no endpoints for automatic draft-progress uploads. Shared-session endpoints below accept only explicitly confirmed answers.

JSON writes use `Content-Type: application/json`. Unknown fields, malformed types, duplicate/unknown slots and incomplete clue/solution sets return `400 {"error":"Hebrew message"}`. Limits: title 200 characters; clue text 5000; request 128 KiB. Text punctuation is preserved. `enumeration` is null or a nonempty array of positive integers adding up to the fixed slot length. Group order follows the input array, displayed left to right within an isolated RTL phrase. `direction` is `across` or `down`. Numbers are integers.

| Method | Path | Result |
|---|---|---|
| GET | `/api/v1/template/` | Canonical rows, numbered coordinates, 24 slots including physical cells |
| GET | `/api/v1/puzzles/` | `{"puzzles":[{"id":"UUID","title":"…","created_at":"ISO8601"}]}` newest creation first, descending UUID tie-breaker |
| GET | `/api/v1/puzzles/latest/` | Full puzzle, or `200 {"puzzle":null}` when empty |
| GET | `/api/v1/puzzles/{id}/` | Full puzzle with metadata, `template`, and `clues` |
| POST | `/api/v1/puzzles/` | Owner only; full title and 24 clues; `201` full puzzle |
| PATCH | `/api/v1/puzzles/{id}/` | Owner only; title and/or **complete replacement** of 24 clues; `200` full puzzle |
| PUT | `/api/v1/puzzles/{id}/solutions/` | Owner only; complete replacement of 24 answers; `200 {"message":"הפתרונות נשמרו."}` |

All writes are atomic. PATCH preserves omitted fields and immutable creation time. Invalid PATCH leaves both metadata and clues untouched. Solutions are separate, never included in reads; there is no answer-key read endpoint. Solutions require exactly one Hebrew character per slot cell, normalize final letters, and must agree at intersections. Replacing clues leaves the optional key unchanged because geometry never changes.

Other statuses: `401` missing/disallowed credentials; `403` non-owner write or invalid CSRF; `404` unknown UUID; `405` unsupported method; `413` request larger than 128 KiB (Hebrew JSON error). HTML pages redirect unauthenticated visitors to login. Error text is Hebrew.

## Complete example files and curl

The committed JSON files are complete payloads for all 24 slots: [create](examples/create.json), [patch](examples/patch.json), [solutions](examples/solutions.json). Clues and answers are explicitly synthetic, not newspaper content. The answer key uses a repeated letter solely to demonstrate valid crossing lengths.

```sh
# Set BASE_URL=https://your-host and OWNER_API_TOKEN through your secret manager.
# Avoid verbose curl, shell tracing, shared process environments and recorded terminals.
curl --fail-with-body -H "Authorization: Bearer $OWNER_API_TOKEN" \
  -H 'Content-Type: application/json' --data-binary @docs/examples/create.json \
  "$BASE_URL/api/v1/puzzles/"
# Copy the returned id to PUZZLE_ID.
curl --fail-with-body -X PATCH -H "Authorization: Bearer $OWNER_API_TOKEN" \
  -H 'Content-Type: application/json' --data-binary @docs/examples/patch.json \
  "$BASE_URL/api/v1/puzzles/$PUZZLE_ID/"
curl --fail-with-body -X PUT -H "Authorization: Bearer $OWNER_API_TOKEN" \
  -H 'Content-Type: application/json' --data-binary @docs/examples/solutions.json \
  "$BASE_URL/api/v1/puzzles/$PUZZLE_ID/solutions/"
```


## Shared solving sessions

These endpoints require an authorized, active, verified Google **session**;
the owner bearer token cannot act as a player. All writes require the standard
CSRF token. Session reads require membership and never return other users’
answers or names. Counts exclude the current user and unauthorized/inactive
participants. Existing puzzle-management endpoints are unchanged.

- `POST /api/v1/sessions/` with `{"puzzle_id":"UUID"}` creates a session and
  enrolls its creator. Returns HTTP 201 with `id`, `puzzle_id`, `can_manage`,
  `invite_active`, and `invite_url`.
- `GET /join/{token}/` shows a join page without enrolling the visitor;
  a CSRF-protected form POST explicitly joins and redirects to `/sessions/{id}/`.
  A revoked link returns 410. The solver page requires existing membership.
- `GET /api/v1/sessions/{id}/` returns session metadata, `counts` such as
  `{"across:1":2}`, and `own` such as
  `{"across:1":{"answer":"אבגדהוז","version":1}}`. Only the creator and owner
  receive an active invitation URL. Missing counts mean zero. The browser polls
  every ten seconds while visible; polling never writes answers or replaces drafts.
- `POST /api/v1/sessions/{id}/answers/` explicitly submits a batch:

  ```json
  {"changes":[{"direction":"across","number":1,"answer":"אבגדהוז","version":0}]}
  ```

  An absent record starts at version zero. Complete Hebrew answers are normalized
  and checked against the fixed slot length. Set `answer` to `null` to withdraw.
  Each successful change increments its version and returns the changed `own`
  entries. Withdrawal retains an empty answer/version record so stale clients
  cannot recreate an obsolete answer. Every field in each change is required.
  The batch is atomic: invalid input returns 400, version conflicts return 409
  with no writes. The client refreshes its baseline after a conflict, preserving
  local letters, and requires another explicit decision. There is no automatic
  upload or automatic write retry.
- `POST /api/v1/sessions/{id}/revoke/` revokes the invitation. Only a member who
  is the creator or owner can use this endpoint; the owner can also manage
  sessions and membership through Django admin. Existing members retain access.

Missing membership returns 404, unauthorized accounts return 401, unsupported
methods return 405, and missing CSRF protection returns 403. Invitation tokens
must be treated as private links. Confirmed answers are proposals, never a
correctness signal. No API allows reading another participant’s answer.
