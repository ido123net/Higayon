Build **higayon**, a private Hebrew cryptic-crossword website for me and a small group of invited friends. Implement a working first version in this repository, including the application, tests, documentation, containerization, Kubernetes deployment, and Terraform configuration. Do not stop after producing a plan or scaffolding.

The requirements below reflect product decisions already made. Make sensible decisions about minor implementation details and proceed without reopening these decisions. Read and follow any applicable repository instructions first.

1. Product scope

- The entire application UI must be in Hebrew and use RTL where appropriate. The product name is `higayon`.
- This is a website for solving Hebrew cryptic crosswords, initially based on the fixed crossword layout in the newspaper's Dyokan supplement of Makor Rishon.
- Support independent solving and optional shared sessions for a single puzzle. Authorized Google users may create invitation links and explicitly join sessions. Each participant keeps a personal local draft and explicitly confirms complete clue answers. Share only counts of other participants who confirmed, never their names or answers. Poll every ten seconds; do not add presence, WebSockets, or additional infrastructure.
- Crossword definitions will be supplied manually through an API or through an owner-only editing screen that uses that same API.
- Do not implement image uploads, OCR, image parsing, PDF import, scraping, automatic crossword generation, or AI features. Reading the supplied reference image once to verify the fixed layout is implementation preparation, not an application feature.
- There are initially no known answers. Include an owner-only API for uploading optional solutions, but do not add answer checking, hints, or solution-reveal features to the player UI in this version.
- Do not add pencil mode, uncertain-answer markings, chat, scoring, subscriptions, or other unrequested features.

2. Technology

- Use Python and Django as a straightforward monolithic application.
- Use Django templates, plain CSS, and small amounts of vanilla JavaScript. No frontend framework, component library, CSS framework, or unnecessary JavaScript build pipeline.
- A small, maintained backend library is acceptable when it meaningfully simplifies API handling or Google authentication. Do not implement Google OAuth/OIDC yourself.
- PostgreSQL is the deployment database. SQLite must also work for local development without requiring PostgreSQL. Configure the choice through environment variables and use portable Django models and migrations.
- Use maintained, compatible versions of dependencies, verify their configuration against official documentation, and pin dependencies reproducibly.
- Keep the implementation small. Do not introduce Redis, background workers, separate microservices, or speculative extension frameworks.

3. Fixed crossword template

Every puzzle uses exactly the same grid, black squares, numbering, and clue slots. Only clue content and optional solutions change. There is no grid editor in this version.

The reference photo is available on the original workstation at `/Users/idof/Downloads/IMG_0818.HEIC`. The following transcription makes the prompt usable independently of that file.

The grid is 11 by 11. Each row below describes its PHYSICAL position from LEFT to RIGHT, with rows running TOP to BOTTOM. `.` is a playable cell and `#` is a black square:

```text
...#.......
.#.#.#.#.#.
.....#.....
.###.#.#.#.
......#....
##.#####.##
....#......
.#.#.#.###.
.....#.....
.#.#.#.#.#.
.......#...
```

Numbered cells use zero-based `[row, column]` coordinates, measured from the physical top-left corner:

```json
{
  "1": [0, 10], "2": [0, 8], "3": [0, 6], "4": [0, 4],
  "5": [0, 2], "6": [0, 0], "7": [2, 10], "8": [2, 4],
  "9": [4, 10], "10": [4, 5], "11": [4, 2], "12": [6, 10],
  "13": [6, 6], "14": [6, 3], "15": [6, 0], "16": [7, 4],
  "17": [8, 10], "18": [8, 8], "19": [8, 4], "20": [10, 10],
  "21": [10, 6]
}
```

- Across answers run RIGHT to LEFT: column indices decrease. Down answers run TOP to BOTTOM: row indices increase.
- Across clue numbers and cell counts are: `1:7, 5:3, 7:5, 8:5, 9:4, 10:6, 12:6, 14:4, 17:5, 19:5, 20:3, 21:7`.
- Down clue numbers and cell counts are: `1:5, 2:7, 3:4, 4:5, 5:3, 6:5, 11:7, 12:5, 13:5, 15:5, 16:4, 18:3`.
- There are 21 numbered cells and 24 clue slots. Validate the transcription against these invariants and the image if available. Do not substitute a generic crossword layout.
- Define the template once as canonical data. Prevent RTL layout rules from accidentally mirroring the physical grid or reversing its coordinates a second time.

4. Solver experience

- The primary device is a phone. Build a responsive, mobile-first layout that also works on desktop.
- Make it resemble a newspaper crossword: white background, black grid and black squares, readable Hebrew text, restrained styling, and minimal controls. Use clear but subtle focus and selection states.
- Opening the site after authentication opens the most recently ADDED puzzle, ordered by immutable creation timestamp with a deterministic tie-breaker. Editing an older puzzle must not make it the latest.
- Provide a simple way to select older puzzles. Display addition dates; publication-date ordering is outside the current scope.
- On mobile, fit the complete grid within the viewport width. Keep the active clue easy to read while the native keyboard is open, and provide access to both clue lists labeled `מאוזן` and `מאונך`.
- Tapping a clue selects and highlights its cells. Tapping a cell selects its applicable word; tapping an intersection again switches between across and down. Clearly show the active cell and clue.
- Use the phone's native keyboard. Do not build an on-screen keyboard. Preserve input focus sensibly so entering each letter does not repeatedly close and reopen the keyboard.
- Implement sensible automatic advancement within the selected word, backspace behavior, editing existing letters, pasting, and desktop keyboard navigation. Do not accidentally jump into unrelated words at word boundaries.
- Support native input and composition events; do not depend solely on desktop keydown events.
- Normalize final Hebrew letters to ordinary letters on entry and paste: `ך→כ`, `ם→מ`, `ן→נ`, `ף→פ`, `ץ→צ`. Use the same normalization for uploaded solutions.
- Store one Hebrew letter per playable cell. Black squares cannot accept input. Pasting must respect the selected word and its length.
- Preserve punctuation and other content in clue text. Support optional answer-length groups such as `[4, 3]`, render their order unambiguously within RTL text, and validate that their sum matches the slot length.
- Users can always replace or delete their own entered letters. With no supplied answer key, a filled grid must not be claimed to be correct.
- Use accessible labels, readable contrast, visible focus, and practical touch targets. All application messages, empty states, validation errors, and loading or failure states must be in Hebrew.

5. Browser-only solving progress

- Save progress automatically in browser storage so it survives refreshes, closing the browser, and returning later.
- Keep independent progress separate for each user and puzzle, and session drafts separate for each user and session. Never mix accounts, puzzles, or sessions.
- Puzzle definitions, accounts, shared-session membership, and explicitly confirmed answers live on the server. Draft letters stay local. Never submit answers on typing, completion, timers, navigation, refresh, or page close.
- Persist only explicitly confirmed clue answers, with version checks preventing stale overwrites. A full answer can be confirmed, updated, or withdrawn explicitly. Before leaving changed confirmed clues, require a decision for all affected crossing clues: replace complete answers, withdraw incomplete answers, restore the confirmed local letters, or return to editing. Preserve pending drafts across refreshes. Own confirmed answers are readable on another device; local drafts take precedence.
- Keep the small browser-storage implementation separate from grid interaction code. This is ordinary code organization, not a request to design future synchronization.
- Handle unavailable browser storage gracefully with a clear Hebrew message rather than silently promising persistence.

6. Authentication and permissions

- Use Google sign-in for browser users and Django session authentication afterward.
- Access is restricted to a configured allowlist of verified Google email addresses. Enforce it server-side for puzzle pages and API access.
- Configure my owner identity explicitly. Only I can add puzzles, edit definitions, or upload solutions. Invited friends can read puzzle content, solve locally, and create or join shared sessions. Session creators and the owner may revoke invitation links; existing members retain access. The owner manages session membership in Django admin.
- Validate the Google identity through the maintained authentication integration, including verified email and normal OAuth/OIDC protections. Do not trust an email sent directly by the client or grant owner access to the first person who signs in.
- Browser requests to the API use the existing session and normal CSRF protection for writes.
- External scripts use a personal owner API token sent as `Authorization: Bearer <token>`. This token authenticates the configured owner and receives only the necessary puzzle-management permissions.
- Generate a high-entropy token and load it through a server-side secret. Use a timing-safe comparison or an appropriate maintained implementation. Document replacement and revocation by rotating the configured secret.
- Never embed the owner token in client-side code, browser storage, a URL, source control, or logs. Production access uses HTTPS.
- Keep session and token authentication paths explicit; adding token authentication must not disable CSRF protection for session-authenticated browser writes.
- Include clear configuration instructions for allowed emails, owner email, Google credentials, redirect URIs, and the owner API token. Missing credentials must not silently enable an authentication bypass.

7. Owner editing interface and shared API

- Provide a simple Hebrew owner-only screen to add a puzzle and edit its clue definitions. Group fields by direction and show the fixed clue numbers and slot lengths.
- Both the solver UI and owner editor must read and write puzzle content through the documented API. Use browser requests to that API rather than building a separate set of form handlers with duplicated business logic.
- Share validation and domain behavior in Python. Enforce permissions at API endpoints, not merely by hiding UI controls.
- Preserve user input when a save fails and show useful Hebrew feedback.
- Do not require optional solutions when creating a puzzle.

Provide a small versioned JSON API with these capabilities; equivalent clean endpoint naming is acceptable:

- `GET /api/v1/puzzles/`: list puzzles, newest added first, with enough metadata for selecting an old puzzle.
- `GET /api/v1/puzzles/latest/`: fetch the latest puzzle, with a documented empty-state response.
- `GET /api/v1/puzzles/{id}/`: fetch the grid template and clue definitions needed for solving.
- `POST /api/v1/puzzles/`: create a puzzle and its full set of clue definitions atomically.
- `PATCH /api/v1/puzzles/{id}/`: update puzzle metadata and definitions with clear, atomic update semantics.
- `PUT /api/v1/puzzles/{id}/solutions/`: upload or replace an optional answer key. Keep this owner-only and separate from ordinary puzzle responses.

Use stable puzzle IDs, immutable creation timestamps, and unique clue identities per puzzle based on number and direction. Validate clue identities against the fixed template, reject duplicates, check required slots and field types, and validate optional enumerations and solution lengths. A partial invalid request must not leave partially saved data.

Do not include solutions in normal read responses or preload them into the browser. Document request/response schemas, authentication, validation errors, status codes, and complete example payloads and curl commands for adding a puzzle, editing clues, and uploading solutions.

8. Infrastructure and portability

- Supply a Dockerfile suitable for deployment and a straightforward local-development workflow. Support SQLite development and an optional local PostgreSQL setup, such as Docker Compose.
- Supply Kubernetes deployment resources and Terraform configuration that can install the application into an EXISTING Kubernetes cluster using its configured context.
- Do not select or provision a cloud provider yet. Cloud account, networking, cluster creation, and managed PostgreSQL provisioning can be added after I choose a provider. Document those boundaries accurately.
- Parameterize the image, namespace, hostname, ingress class, TLS references, resource requests/limits, and database configuration rather than hardcoding a particular provider.
- Use PostgreSQL in the deployment configuration and allow an externally provided PostgreSQL connection. SQLite remains a development option.
- Include an application Service, configurable Ingress, appropriate configuration and secret references, health/readiness checks, static-file handling, and an explicit database-migration step suitable for Kubernetes.
- Terraform should reference existing Kubernetes Secrets instead of receiving or managing their secret values. Do not commit credentials or place real secrets in Terraform configuration, example tfvars, or state managed by this repository.
- Include environment-variable examples with placeholders and instructions for creating the required runtime secrets.
- Avoid unnecessary infrastructure components. Do not deploy anything to a real cloud account as part of implementation.

9. Verification and handoff

- Write focused tests for the fixed grid and clue slots, API validation and atomicity, latest-puzzle ordering, access restrictions, owner-only writes, API-token authentication, and protection of optional solutions.
- Verify database portability with SQLite and PostgreSQL when the environment permits. Do not claim PostgreSQL was tested if it was not available.
- Test or otherwise directly verify Hebrew normalization, RTL coordinate handling, word navigation, and browser-storage separation and restoration.
- Inspect the UI at narrow phone sizes and on desktop. Pay particular attention to intersections, clue selection, answer-length display, and viewport behavior when a native keyboard opens. State any real-device testing limitations honestly.
- Run the relevant application checks, migrations, tests, container checks, and Terraform formatting/validation that the available environment supports. Fix failures that are within scope and report checks you could not run.
- Seed the fixed template reproducibly. If demo puzzles are helpful, provide an explicit optional demo-data command with clearly labeled Hebrew sample clues; do not invent authentic newspaper content or require OCR.
- Write a concise README covering local startup with SQLite and PostgreSQL, Google login setup, owner and allowlist configuration, API examples, tests, Docker, Kubernetes/Terraform deployment to an existing cluster, migrations, required external resources, and the limits of browser-only progress.
- Finish with a concise account of what was implemented, what was verified, and the exact configuration still required to run it. If credentials or external infrastructure are unavailable, complete everything that can be implemented locally and clearly identify those remaining setup steps.

Optimize for a usable, simple first release and understandable code. Deliver the agreed scope end to end rather than expanding the product.
