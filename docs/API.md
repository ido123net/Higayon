# API v1

All endpoints require an allowlisted, verified Google-backed session or the configured owner bearer token. Browser writes require Django's `csrftoken` cookie in `X-CSRFToken`; same-origin only. Bearer authorization is evaluated explicitly before session auth, uses timing-safe comparison, and does not need CSRF. A bad bearer token never falls back to a session. Tokens cannot log into pages. No progress endpoints exist.

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
