# Local Data Security

This document describes exactly what happens to data in this application,
in support of running it locally against **real** Pentera assessment data.
It reflects the code as it exists — every claim here was verified against
the implementation, not assumed. See "Verification" at the bottom for how.

## Summary

**This application is local-only.** There is no telemetry, analytics, error
reporting, remote logging, or AI/LLM integration anywhere in the codebase.
The frontend makes exactly one kind of outbound call: `fetch()` to your own
backend at `http://localhost:8000`. The backend makes zero outbound network
calls of any kind. Everything lives in one local SQLite file.

## Work Laptop / Real Data procedure

Follow this exact sequence the first time you run this on a machine you're
about to load real Pentera assessment data into:

1. **Clone the private repo.**
   `git clone https://github.com/Tahaa21/adpa-tracker.git && cd adpa-tracker`
2. **Run `./start.sh`** (`.\start.ps1` on Windows — see the note at the top
   of that file; it hasn't been run on an actual Windows machine yet).
   This single command does steps that used to be manual: installs backend
   and frontend dependencies (only if needed), sets
   `DATABASE_URL=sqlite:///./app.db` and `LOCAL_ONLY=true`, runs database
   migrations, **runs the security preflight and refuses to start the app
   if it fails**, then starts the backend on `127.0.0.1:8000` and the
   frontend on `localhost:5173` (never `0.0.0.0`). You do not need to run
   the preflight separately — `start.sh` already gates on it. If you want
   to run it standalone anyway (e.g. before cloning is even finished
   installing), it's `python3 scripts/local_security_preflight.py`, and it
   must print `PASS: Local-only security preflight`.
3. **Confirm the application loads** — `start.sh` prints
   `ADPA Tracker is running at http://localhost:5173` once both the
   backend (`http://127.0.0.1:8000/health`) and frontend are actually
   responding; it polls both before printing that line, so seeing it is
   itself a confirmation.
4. **Confirm the database is empty** before importing real data — either
   it's a fresh clone (nothing seeded yet) or run
   `python3 scripts/reset_local_data.py --yes` to clear any leftover demo
   data first. Real and demo findings will display mixed together if you
   skip this (see "Recommended workflow" below).
5. **Import your Pentera CSV manually through the browser**:
   Assessments → "+ New Assessment" → fill in the form → choose your file
   → Import. Do not script this step for a real file — do it by hand so
   you see exactly what's happening.
6. **Review the import warnings** shown in the summary card (and, for
   more detail, on the assessment's detail page) — they tell you which
   columns/rows weren't recognized. This is also where you'd notice if
   the parser misread your export's structure.
7. **Use the application** — findings, remediation workflow, validation,
   dashboard trends, etc.
8. **Stop the app** with Ctrl+C in the terminal running `start.sh` (cleans
   up both processes), or `./stop.sh` if a previous run was left dangling.
9. **Reset local data when finished**, if desired:
   `cd backend && source venv/bin/activate && python3 ../scripts/reset_local_data.py --yes`.
   This wipes assessments, findings, assets, remediations, validations,
   and owners — not source code, not git history, not the database
   file/schema itself (it becomes empty, not deleted).

(The manual step-by-step — separate venv setup, separate `alembic upgrade
head`, separate preflight run, `uvicorn`/`npm run dev` in two terminals —
still works exactly as before and is documented in the README under
"Manual / development startup"; use it if you need `--reload` or are
debugging a `start.sh` failure.)

### AI coding assistants and real data

**Do not point an AI coding assistant (Claude Code, Cursor, Copilot, or
similar) at the live database, a real Pentera export file, or an
application screen/terminal currently displaying real assessment data**
unless your organization's policy explicitly permits it. This includes:
asking an assistant to inspect `backend/app.db` while it holds real data,
pasting real CSV content into a chat, sharing screenshots of the app with
real findings visible, or letting an assistant run commands that would
read `backend/app.db`'s contents (as opposed to just its path/existence,
which is what `local_security_preflight.py` does — that script
deliberately never opens the database). If you want AI assistance while
working with real data loaded, reset to demo data first
(`scripts/reset_local_data.py` then `scripts/load_sample_data.py`), do the
AI-assisted work, then re-import real data afterward.

## LOCAL_ONLY mode — what it actually guarantees (and what it doesn't)

`backend/app/core/config.py` defines `local_only: bool = True` (default
**on**). Set via `.env` (see `.env.example`): `LOCAL_ONLY=true`.

**What it does:**
- Force-restricts CORS to `http://localhost:*` / `http://127.0.0.1:*` /
  `http://[::1]:*` origins, **regardless of what `CORS_ORIGINS` is set to**
  in `.env` — a misconfigured env var cannot open the API to a non-local
  browser origin while `LOCAL_ONLY=true`.
- Documents and enforces, as a matter of code review policy, that no
  external integration (telemetry, analytics, error reporting, cloud
  storage, AI/LLM calls) may be added to this codebase while it's true.
  There are currently zero such integrations (see "Outbound network audit"
  below) — LOCAL_ONLY is what keeps that intentional rather than
  accidental.

**What it explicitly does NOT do — be accurate about this:**
- **CORS is not an egress firewall.** It is a browser-enforced restriction
  on which web-page origins are allowed to call this API via
  JavaScript's `fetch`/`XHR`. It has zero effect on server-to-server
  requests, `curl`, Python scripts, or any non-browser client — and it does
  nothing to physically prevent the backend process itself from opening an
  outbound connection if code that did so were ever added.
  `LOCAL_ONLY=true` does not, by itself, stop that; what stops it today is
  that no such code exists (verified below), not the CORS setting.
- It is **not** an OS-level or network-level outbound firewall. If you need
  a hard guarantee that this machine cannot send data anywhere over the
  network regardless of application code, that has to be enforced outside
  this application (OS firewall rules, running without network access,
  etc.) — this app does not attempt to provide that itself.
- It does not add authentication, encryption at rest, or any other control
  outside the specific items listed above.

In short: LOCAL_ONLY plus the current absence of any outbound integration
means the app doesn't send your data anywhere today. LOCAL_ONLY is what
keeps that from silently regressing; it is not a technical barrier that
would stop it if someone (a person or a future change) deliberately added
an outbound call.

## Outbound network audit

Audited (2026-08-20) via full-text search across `backend/app/`,
`frontend/src/`, `backend/requirements.txt`, and `frontend/package.json` for:
`fetch(`, `axios`, `requests.`, `httpx.`, `urllib.request`, Sentry,
analytics/telemetry SDK names (Mixpanel, Segment, Amplitude, PostHog,
Datadog, New Relic, Bugsnag, LogRocket, Google Analytics), and AI/LLM SDK
names (OpenAI, Anthropic, LangChain, Cohere, HuggingFace).

**Result:**
- **Backend**: zero outbound calls of any kind. `httpx` is a dependency but
  is only used by `TestClient` in the test suite (in-process, never hits a
  real network).
- **Frontend**: exactly one outbound call — `fetch()` in
  `frontend/src/api/client.ts`, targeting `VITE_API_BASE_URL` (defaults to
  `http://localhost:8000`). No analytics/telemetry packages in
  `package.json`. React, Vite, Recharts, React Router — none of these ship
  runtime telemetry.
- No Sentry, no analytics SDKs, no AI/LLM SDKs anywhere.

Nothing was removed because nothing existed to remove.

## Network exposure (host bindings)

Distinct from "does the app call out" (above) is "can something else on
your network reach in." Every path this app can be run through is
localhost-only:

- **Docker Compose**: `backend` and `frontend` host port mappings in
  `docker-compose.yml` are `127.0.0.1:<port>:<container-port>` — not the
  bare `<port>:<port>` shorthand, which Docker publishes on **all** host
  interfaces (0.0.0.0) by default. `db` (Postgres) has **no** `ports:`
  mapping at all — the `backend` container reaches it over the internal
  Compose network (hostname `db`, port 5432) without ever touching the
  host's network stack. Each service's process still binds `0.0.0.0`
  *inside its own container* (`uvicorn --host 0.0.0.0`, `vite --host
  0.0.0.0`) — that's required for Docker's port-forwarding to reach the
  process at all and is not, by itself, a LAN-exposure decision. The
  exposure decision is entirely the host-side `127.0.0.1:` prefix in the
  `ports:` mapping; `docker-compose.yml` has comments at each of these
  spots explaining the distinction — don't "simplify" one back to
  `"<port>:<port>"`.
- **Non-Docker backend**: the documented command is
  `uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload` — the
  `--host 127.0.0.1` is stated explicitly in README/CLAUDE.md rather than
  relying on uvicorn's default (which also happens to be `127.0.0.1`, but
  this app doesn't rely on that silently — see it stated in every doc that
  shows the command).
- **Non-Docker frontend**: `frontend/vite.config.ts` has no `server.host`
  override, so `npm run dev` binds to localhost only (Vite's default).
  Never add `host: true` or `host: '0.0.0.0'` there.
- **SQLite**: not a network service at all — a local file, not reachable
  over the network in any configuration.

Run `python3 scripts/local_security_preflight.py` to check these
statically before starting the app (see "Preflight check" below).

## What data is stored, and where

A single SQLite file: **`backend/app.db`** (path resolved from
`DATABASE_URL=sqlite:///./app.db`, relative to wherever the backend process
is started from — in the documented workflow, always `backend/`, so the
absolute path is `<repo>/backend/app.db`).

Tables (see `docs/DATA_MODEL.md` for full schema): `assessments`, `assets`,
`findings`, `finding_instances`, `owners`, `remediations`,
`validation_records`.

Every value from your uploaded CSV that the parser recognizes (finding
title, severity, asset name/type, domain, description, remediation
guidance, exploitability) is stored normalized on `Finding`/`Asset`. The
**full original raw row** is also stored (on `FindingInstance.raw_row`) and
unrecognized columns are preserved (on `Finding.source_metadata`) for
audit/traceability — with one exception, see next section.

## Credential/secret redaction

Two layers, both in `backend/app/services/redaction.py`, both run on
**every row** regardless of which finding type the classifier assigned (a
credential-shaped column or phrase can appear on any row, not just ones
recognized as credential-related):

1. **Header-based, whole-value redaction.** Every raw CSV column header is
   checked against a pattern list: `password`, `passwd`, `pwd`,
   `credential`(s), `secret`, `hash` (also catches "NT hash", "LM hash",
   "NTLM hash", "password hash"), `ntlm`, `cracked`, `cleartext`,
   `plaintext`, `privatekey`, `apikey`, `token`, `evidence`. If a header
   matches, that column's entire value is replaced with a fixed marker
   (`[REDACTED - sensitive field, value not stored]`) before anything is
   written to the database. Applies to both the raw-row audit trail
   (`FindingInstance.raw_row`) and unmapped-field metadata
   (`Finding.source_metadata.unmapped_fields`).
2. **Inline pattern redaction, for free text.** Applied to (a) the
   recognized `description`/`remediation_guidance` fields and (b) any
   value from step 1 that survived because its own header wasn't flagged
   (e.g. a generic "Notes" column). A regex matches the common
   `key: value` / `key=value` shape (`password: X`, `credential=Y`, `NTLM
   hash: aad3b435...`) and redacts only the value half, keeping the
   surrounding sentence readable — e.g. `"Account svc_backup password =
   Summer2024!"` becomes `"Account svc_backup password: [REDACTED]"`. The
   finding itself (e.g. "Credential exposure detected for account X") is
   preserved; only the actual secret value is removed.

**Known limitation, stated plainly**: layer 2 requires an explicit
key/value delimiter (`:` or `=`). Prose that states a secret *without* one
— e.g. `"the password is Summer2024!"` — is **not** caught, because a
pattern broad enough to catch that would also flag legitimate remediation
guidance that merely discusses passwords without stating one (e.g. "reset
the password regularly"). This is a deliberate, conservative trade-off, not
an oversight. If you know your real export puts secrets in free text
without a `key: value` shape, tell us the exact phrasing pattern and we can
add a targeted rule — don't assume this covers every case.

## Upload retention

Uploaded files are **never written to disk**. `routers/imports.py` reads
the multipart upload into memory (`await file.read()`), parses it, and
discards the bytes — confirmed by code inspection (no file-write or
`uploads/`-directory logic exists anywhere in `backend/app/`). Only the
sanitized **filename** (not the content) is stored on the `Assessment`
record, for display purposes.

## Upload size limit

Controlled by exactly one setting: `MAX_UPLOAD_SIZE_MB` (default **100**,
i.e. 104,857,600 bytes / 100 MiB), read once into
`Settings.max_upload_size_bytes` (`backend/app/core/config.py`) and
enforced in exactly one place (`routers/imports.py`), for both `.json` and
`.csv` uploads identically — there is no separate or duplicated limit
anywhere else in the frontend or backend. The comparison is against the
**actual bytes read**, never `Content-Length` or any other header. A file
of exactly 100 MiB is accepted; only a file one byte over is rejected,
with a response naming the exact detected and maximum byte counts (never
file contents):

```
Upload rejected: detected 104857601 bytes; maximum 104857600 bytes.
```

The same two numbers are logged locally (see "Logging" below) — nothing
else about the upload is logged on rejection.

### Guaranteed restart procedure

**Editing `.env` alone does not change a running backend's behavior.**
`get_settings()` is cached for the lifetime of the process — a backend
that was already running when you edit `MAX_UPLOAD_SIZE_MB` (or pull new
code) keeps using whatever value it read at startup until it is actually
killed and restarted. This matters especially because **`.env` is
git-ignored** — `git pull` never touches your local copy, so a `.env`
created early in this project's life can silently keep an old value
forever regardless of what changes upstream. If uploads are still being
rejected at a size that shouldn't be, do this, in order, every time:

```bash
# 1. Stop everything definitively (frees ports even if a prior run didn't
#    shut down cleanly; harmless if nothing was running).
./stop.sh

# 2. Pull the latest code.
git pull

# 3. Confirm your local .env has the value you expect (this file is
#    git-ignored — pulling never changes it). If MAX_UPLOAD_SIZE_MB is
#    missing entirely, the code default (100) applies; if it's present
#    with an old/wrong number, edit it by hand.
grep MAX_UPLOAD_SIZE_MB .env 2>/dev/null || echo "not set in .env — using code default"

# 4. Start fresh — start.sh always launches new backend/frontend
#    processes, so this alone guarantees you're not running stale code
#    *if* step 1 actually stopped the old ones first.
./start.sh
```

To directly confirm which value a freshly-started backend is actually
using (bypasses guesswork entirely — inspects configuration only, never
assessment data):

```bash
cd backend && source venv/bin/activate
python3 -c "from app.core.config import Settings; print(Settings().max_upload_size_bytes)"
# Expect: 104857600
```

## Logging

`backend/app/core/logging_config.py` configures a local-only logger:
console (visible in the `uvicorn` terminal) + a local file at
`backend/logs/app.log` (git-ignored). No remote log handler exists.

What gets logged, exactly (from `services/import_service.py` and
`routers/imports.py`):
```
Pentera import started: file_size_bytes=<N>
Pentera import completed: assessment_id=<N> rows_processed=<N> rows_imported=<N>
    rows_skipped=<N> warnings=<N> new=<N> recurring=<N> resolved=<N>
Pentera import failed at parse stage: <ExceptionClassName>
Pentera upload rejected: detected_bytes=<N> max_bytes=<N>
```
That is the entirety of what this application logs. No raw CSV rows, no
usernames, no domains, no IPs, no credentials, no finding titles/metadata,
no file contents. (Separately, `uvicorn`'s own access log will show
`POST /imports/pentera` with a status code, per its default behavior — it
does not log request bodies.)

## Preflight check

`./start.sh` (and `.\start.ps1`) run this automatically before starting
either service, and refuse to start the app if it fails — you don't need
to run it separately in the normal `start.sh` flow. To run it standalone
(e.g. via the manual startup path, or just to check without starting
anything):

```bash
python3 scripts/local_security_preflight.py
```

A lightweight, static-only script — it checks configuration and file
layout, and **never opens, queries, or prints the contents of
`backend/app.db` or any assessment data**. It verifies: `LOCAL_ONLY` is
enabled; the database URL points somewhere local (SQLite, or a Postgres
host of `localhost`/`127.0.0.1`/`db`); the SQLite file path is git-ignored
(via `git check-ignore`, with a text-based fallback if git isn't
available); the usual upload/data directories are git-ignored; Vite has no
`host: true`/`0.0.0.0` override; Docker Compose port mappings are
`127.0.0.1`-bound and Postgres has no active host port publish; no
unexpected non-localhost URLs appear in backend/frontend source; and the
expected config files exist. Prints `PASS: Local-only security preflight`
(exit 0) or lists specific `FAIL`/`WARN` lines (`FAIL` → exit 1). Run it
before every real-data session, not just once.

## Resetting local data

There is no DELETE API by design (this keeps the write surface minimal).
Use the script instead:

```bash
cd backend && source venv/bin/activate
python3 ../scripts/reset_local_data.py --yes
```

This deletes all rows from `FindingInstance`, `ValidationRecord`,
`Remediation`, `Finding`, `Asset`, `Assessment`, and `Owner` (in FK-safe
order) — owners are wiped by default too, since an owner created during
real usage could itself be a real person's name. Pass `--keep-owners` if
you specifically want to preserve organizational labels (e.g. "Identity
Team") across a reset. **This only ever deletes database rows** — it never
touches source code, migrations, or git history, and never deletes
`backend/app.db` itself (the file and schema remain; it just becomes
empty).

## Reseeding sanitized demo data

```bash
python3 scripts/load_sample_data.py http://localhost:8000
```

Loads the two sanitized, synthetic sample assessments from `sample-data/`
(fictional `fabrikam.local` domain — see `scripts/generate_sample_data.py`
for how they were generated). Safe to run anytime; safe to commit; this is
the only data intended to ever be committed to git.

## Recommended workflow: demo data vs. real data

These two are not meant to coexist in the same database — the app has no
per-source segregation in its dashboard/findings views, so real and demo
findings would display mixed together if both are present.

| Goal | Commands |
|---|---|
| Start clean | `python3 scripts/reset_local_data.py --yes` |
| Run with sanitized demo data | `python3 scripts/load_sample_data.py` |
| Clear demo data before real import | `python3 scripts/reset_local_data.py --yes` |
| Import real data | Use the UI: Assessments → New Assessment → upload your CSV |
| Wipe real data | `python3 scripts/reset_local_data.py --yes` |
| Reseed demo data afterward | `python3 scripts/load_sample_data.py` |

## Database persistence

- **Path**: `backend/app.db` (SQLite file, absolute path
  `<repo>/backend/app.db` in the documented local workflow).
- **Persists across**: browser refresh, backend restart, frontend restart,
  full computer restart — it's a plain file on disk, not in-memory. You
  will need to manually restart `uvicorn`/`npm run dev` after a reboot, but
  the data itself survives.
- **Backup**: it's a single file — `cp backend/app.db backend/app.db.bak`
  (or copy it anywhere local) is a complete backup. Do not commit this
  backup to git (same `*.db` gitignore rule applies to any copy).
- **Full reset (alternative to the script)**: `rm backend/app.db && cd
  backend && alembic upgrade head` recreates an empty schema from scratch.

## Git safety

`.gitignore` excludes: `*.db`, `*.sqlite`, `*.sqlite3`, `backend/app.db`
explicitly, `backend/uploads/`, `uploads/`, `data/`, `local-data/`,
`real-data/`, `sample-data/real/`, `logs/`, `*.log`, `.env` /`.env.*`
(except `.env.example`). The sanitized demo files under `sample-data/*.csv`
are **intentionally tracked** — verified with `git check-ignore` that they
are not caught by any of the above patterns.

**You are still responsible for**: not manually adding a real assessment
CSV into a tracked path (e.g. don't drop it in `sample-data/` directly —
use `sample-data/real/`, which is ignored, if you want a local-only copy on
disk at all — you don't need one, since upload doesn't persist the file
anyway), and not pasting real finding data into commit messages, issues, or
screenshots you choose to share.

## Remaining limitations (be aware of these)

- Inline free-text redaction requires an explicit `key: value` /
  `key=value` delimiter — prose stating a secret without one (e.g. "the
  password is X") is not caught (see "Known limitation" under
  Credential/secret redaction above).
- No per-assessment-source data segregation — real and demo data will
  display together if both are imported into the same database at once.
  Use the reset workflow above to avoid this.
- No authentication/access control exists (out of scope for this MVP).
  Localhost-only binding is the actual control here — do not bind the
  backend or frontend to anything other than `localhost`/`127.0.0.1` while
  real data is loaded, since anyone who could reach a non-localhost address
  would have full read/write access with no login.
- LOCAL_ONLY and CORS restrictions are application-level safeguards, not an
  OS/network-level egress firewall — see "LOCAL_ONLY mode" above for the
  precise distinction. If your organization requires a hard network-level
  guarantee, enforce it outside this application (OS firewall, air-gapped
  execution, etc.).
- The Docker Compose path (Postgres) has not been proven end-to-end in this
  environment (see `CLAUDE.md`) — the local SQLite fallback documented here
  is what has actually been verified end-to-end. The port-binding fixes in
  `docker-compose.yml` have been reviewed and are believed correct but have
  not been confirmed against a live `docker compose up`.

## Verification performed (across sessions)

- Grepped and manually inspected (not just grepped) the entire codebase for
  outbound-call, telemetry, analytics, error-reporting, AI/LLM, and CDN/
  external-resource patterns — including `aiohttp`, WebSocket usage,
  remote logging services, cloud storage SDKs, and external fonts/scripts/
  images in `index.html`/CSS/components. Zero results beyond the one
  intentional local `fetch()` and one doc-comment link
  (`https://vite.dev`, not a runtime call).
- Ran a live import with a fake "Cracked Password" column containing a
  fake credential value; confirmed the value was replaced with the redacted
  marker in the stored `raw_row`, while the functional asset identifier in
  the same row was preserved correctly.
- Ran a live import with a fake `password = Summer2024!` pattern embedded
  in free-text description/recommendation fields and in a generic
  non-flagged "Notes"-style column; confirmed both were redacted while
  surrounding context (e.g. the asset name) stayed readable. 11 automated
  tests cover this (`backend/tests/test_redaction.py`).
- Inspected the resulting log output; confirmed only the operational
  summary lines above were written, no row content.
- Reviewed every `FindingInstanceOut`/`FindingDetail` API schema field and
  every `raise`/exception-message call site in the backend; confirmed
  `raw_row` is never returned by any endpoint, `source_metadata` (which
  does get returned) only ever contains already-redacted values, and no
  exception message embeds row content.
- Ran `reset_local_data.py` (including the owner-wipe default) against a
  seeded database, confirmed via direct query that findings/owners/
  assessments counts dropped to zero, then reseeded successfully.
- Confirmed via `git check-ignore` that sanitized `sample-data/*.csv` files
  are tracked while `data/`, `local-data/`, `real-data/`, `logs/` are
  ignored, and ran `git status --ignored` to visually confirm the expected
  paths appear under "Ignored files".
- Ran `scripts/local_security_preflight.py` in three scenarios: normal
  (all PASS), explicit SQLite `DATABASE_URL` override (all PASS,
  including `git check-ignore`-confirmed DB path), and a deliberately
  broken config (`LOCAL_ONLY=false`) — confirmed it correctly reports FAIL
  and exits non-zero. Also caught and fixed a false-positive in the
  script's own Vite-config check (it was matching example code quoted
  inside a warning comment, not real config) before trusting it.
- Verified `frontend/vite.config.ts` has no `host` override and
  `docker-compose.yml`'s backend/frontend `ports:` mappings are prefixed
  `127.0.0.1:`, with the Postgres service publishing no host port at all.
