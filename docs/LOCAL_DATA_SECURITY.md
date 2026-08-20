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

## LOCAL_ONLY mode

`backend/app/core/config.py` defines `local_only: bool = True` (default
**on**). When enabled:

- CORS is force-restricted to `http://localhost:*` / `http://127.0.0.1:*` /
  `http://[::1]:*` origins, **regardless of what `CORS_ORIGINS` is set to**
  in `.env` — a misconfigured env var cannot open the API to a non-local
  origin while `LOCAL_ONLY=true`.
- There is currently nothing else to gate: the codebase has zero external
  integrations to begin with (see "Outbound network audit" below), so
  `LOCAL_ONLY` is a structural guarantee against ever accidentally adding
  one silently, not a toggle that disables existing behavior.

Set via `.env` (see `.env.example`): `LOCAL_ONLY=true`.

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

`backend/app/services/redaction.py` scans every raw CSV column **header**
(not value) against a list of patterns: `password`, `passwd`, `pwd`,
`credential`, `secret`, `hash`, `ntlm`, `cleartext`, `plaintext`,
`privatekey`, `apikey`, `token`, `evidence`. If a header matches, that
column's **value** is replaced with a fixed marker
(`[REDACTED - sensitive field, value not stored]`) before it is ever
written to the database — this applies to both the raw-row audit trail and
the unmapped-fields metadata. This runs on every row regardless of finding
type, so a credential-shaped column can't slip through even on a row the
classifier doesn't recognize as credential-related.

**Known limitation**: this only inspects column headers, not free-text
content. If a real Pentera export embeds an actual password inside a
`Description` or `Recommendation` column's free text (rather than its own
column), it will **not** be redacted — there is no reliable way to do that
without false-positiving heavily on legitimate remediation guidance text
(e.g. "reset the password" is normal advice, not a leak). If you know your
export does this, tell us the column name and we can add a targeted rule.

## Upload retention

Uploaded files are **never written to disk**. `routers/imports.py` reads
the multipart upload into memory (`await file.read()`), parses it, and
discards the bytes — confirmed by code inspection (no file-write or
`uploads/`-directory logic exists anywhere in `backend/app/`). Only the
sanitized **filename** (not the content) is stored on the `Assessment`
record, for display purposes.

## Logging

`backend/app/core/logging_config.py` configures a local-only logger:
console (visible in the `uvicorn` terminal) + a local file at
`backend/logs/app.log` (git-ignored). No remote log handler exists.

What gets logged, exactly (from `services/import_service.py`):
```
Pentera import started: file_size_bytes=<N>
Pentera import completed: assessment_id=<N> rows_processed=<N> rows_imported=<N>
    rows_skipped=<N> warnings=<N> new=<N> recurring=<N> resolved=<N>
Pentera import failed at parse stage: <ExceptionClassName>
```
That is the entirety of what this application logs. No raw CSV rows, no
usernames, no domains, no IPs, no credentials, no finding titles/metadata,
no file contents. (Separately, `uvicorn`'s own access log will show
`POST /imports/pentera` with a status code, per its default behavior — it
does not log request bodies.)

## Resetting local data

There is no DELETE API by design (this keeps the write surface minimal).
Use the script instead:

```bash
cd backend && source venv/bin/activate
python3 ../scripts/reset_local_data.py --yes
```

This deletes all rows from `FindingInstance`, `ValidationRecord`,
`Remediation`, `Finding`, `Asset`, and `Assessment` (in FK-safe order).
Owners (team labels like "Identity Team") are kept by default — pass
`--include-owners` to clear those too. **This only ever deletes database
rows** — it never touches source code, migrations, or git history, and
never deletes `backend/app.db` itself (the file and schema remain; it just
becomes empty).

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

- Free-text `Description`/`Recommendation` columns are not scanned for
  embedded secrets (see "Known limitation" above).
- No per-assessment-source data segregation — real and demo data will
  display together if both are imported into the same database at once.
  Use the reset workflow above to avoid this.
- No authentication/access control exists (out of scope for this MVP) — if
  you ever bind the backend to something other than `localhost`, anyone who
  can reach that address can read/write your data. Do not do that with real
  data loaded.
- The Docker Compose path (Postgres) has not been proven end-to-end in this
  environment (see `CLAUDE.md`) — the local SQLite fallback documented here
  is what has actually been verified.

## Verification performed this session

- Grepped the entire codebase for outbound-call and telemetry/AI SDK
  patterns — zero results beyond the one intentional local `fetch()`.
- Ran a live import with a fake "Cracked Password" column containing a
  fake credential value; confirmed the value was replaced with the redacted
  marker in the stored `raw_row`, while the functional asset identifier in
  the same row was preserved correctly.
- Inspected the resulting log output; confirmed only the operational
  summary lines above were written, no row content.
- Ran `reset_local_data.py` against a seeded database, confirmed via the
  API that findings/assessments counts dropped to zero, then reseeded
  successfully.
- Confirmed via `git check-ignore` that sanitized `sample-data/*.csv` files
  are tracked while `data/`, `local-data/`, `real-data/` are ignored.
