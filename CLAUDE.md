# CLAUDE.md

Guidance for AI coding agents (Claude Code, Cursor, etc.) working in this repo.
Keep this file updated as the project evolves — it's the fastest way for an
agent to get oriented without re-reading the whole codebase.

## Product purpose

AD Security Remediation Tracker is a **remediation operations platform** that
sits between AD security assessment and measurable risk reduction:

```
Security Assessment → Risk Prioritization → Remediation → Validation → Risk Reduction
```

It answers: *what should we fix first, who owns it, has it been fixed, and can
we show risk was reduced?* Pentera is the first (and currently only) assessment
source. **This is not an attack-path graphing tool and does not replace
BloodHound.**

## Current MVP scope

See [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md) for the full scope and the
definition of done. Short version: import Pentera assessments (**JSON
preferred, CSV also supported, PDF not yet**), normalize findings,
score/prioritize them, run them through an owner/status/notes remediation
workflow and a manual validation workflow, and show risk-reduction trends
across repeated assessments on a dashboard.

## Technology stack

- **Frontend**: React + TypeScript + Vite + Tailwind CSS + Recharts
- **Backend**: Python + FastAPI + Pydantic + SQLAlchemy + Alembic
- **Database**: PostgreSQL via Docker Compose (intended deployment target).
  SQLite is supported as a zero-config local dev fallback
  (`DATABASE_URL=sqlite:///./app.db`) — see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Local env**: Docker + Docker Compose

## Repository structure

```
ad-security-remediation-tracker/          (local folder: ad-sec-tracker)
├── frontend/            React app (Vite)
├── backend/              FastAPI app
│   └── app/
│       ├── models/        SQLAlchemy ORM models
│       ├── schemas/        Pydantic DTOs
│       ├── services/        risk engine, fingerprinting, import orchestration
│       ├── routers/         FastAPI route modules
│       └── integrations/
│           └── pentera/     parser.py (CSV) / json_parser.py (JSON) /
│                              mapper.py / schemas.py — both parsers feed
│                              the same mapper.py, unmodified
├── sample-data/          sanitized fake Pentera-style CSV (2) + JSON (1)
├── docs/                 ARCHITECTURE.md, DATA_MODEL.md, PENTERA_IMPORT.md,
│                          MVP_SCOPE.md, LOCAL_DATA_SECURITY.md
├── scripts/               helper scripts (seed sample data, etc.)
├── docker-compose.yml
├── .env.example
└── README.md
```

## Development commands

**Primary path — one command** (macOS/Linux; `start.ps1` on Windows,
unverified): checks tools, creates/reuses `backend/venv`, installs deps
only when `requirements.txt`/`package-lock.json` changed, runs migrations,
runs `scripts/local_security_preflight.py` (blocks startup on failure),
starts backend on `127.0.0.1:8000` and frontend on `localhost:5173`
(never `0.0.0.0`), Ctrl+C stops both:

```bash
./start.sh
```

`./stop.sh` frees ports 8000/5173 if a previous run didn't shut down
cleanly. Full details/testing notes: see `start.sh`'s test verification in
the git log, and README's "Quick start" section.

**Manual / development steps** (what `start.sh` wraps — use these directly
for finer control, e.g. `--reload`, or to debug a `start.sh` failure):

Full stack via Docker Compose (Postgres) — not the primary path, see
"Docker Compose status" below:

```bash
cp .env.example .env
docker compose up --build
# backend: http://localhost:8000  (docs at /docs)
# frontend: http://localhost:5173
```

Backend only, local Python + SQLite (fastest iteration loop):

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=sqlite:///./app.db
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend only:

```bash
cd frontend
npm install
npm run dev
```

Backend tests:

```bash
cd backend && source venv/bin/activate && pytest
```

Load sample/demo data (after the backend is running):

```bash
python3 scripts/load_sample_data.py
```

Reset local data (clears assessments/findings/assets/remediations/
validations/owners by default — pass `--keep-owners` to preserve owners;
never touches source code or migrations):

```bash
cd backend && source venv/bin/activate
python3 ../scripts/reset_local_data.py --yes
```

Security preflight (run before working with real assessment data; static
checks only, never inspects data):

```bash
python3 scripts/local_security_preflight.py
```

## Local data security

This app is LOCAL-ONLY by design: `LOCAL_ONLY=true` (default) forces CORS to
localhost origins regardless of env misconfiguration (CORS restricts which
browser origins may call the API — it is not an egress firewall), all
Docker/uvicorn/Vite host bindings are localhost-only, there are zero
outbound network integrations anywhere in the codebase (audited — see the
doc below), uploaded files are never written to disk, and credential-shaped
fields are redacted before persistence — for CSV this covers columns and
inline free-text patterns; for JSON, `redact_json()` applies the same
redaction recursively through arbitrarily nested objects/arrays. Full details,
verification steps, and honestly-stated limitations:
**[docs/LOCAL_DATA_SECURITY.md](docs/LOCAL_DATA_SECURITY.md)**. Read this
before importing real Pentera assessment data — it includes the exact
"Work Laptop / Real Data" procedure and a `scripts/local_security_preflight.py`
script to run first.

## Architecture rules

1. **A source system's data model must never become the internal data model.**
   Pentera (and any future source) is normalized through
   `integrations/<source>/{parser,mapper,schemas}.py` into the internal
   `Finding`/`FindingInstance`/`Asset` model. Pentera has two format-specific
   parsers (`parser.py` for CSV, `json_parser.py` for JSON) that both
   produce the same `RawPenteraRow` shape and feed the same `mapper.py` —
   format-specific code never leaks past the parser layer. See
   [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and
   [docs/PENTERA_IMPORT.md](docs/PENTERA_IMPORT.md).
2. Routers are thin; business logic (risk scoring, fingerprinting, import
   orchestration, workflow transitions) lives in `app/services/`.
3. The frontend only talks to the backend via the REST API — no direct DB
   access, no business logic duplicated client-side beyond simple display
   formatting.
4. All DB access goes through the SQLAlchemy ORM — no raw/string-built SQL.

## Database / model conventions

- Primary keys are integer autoincrement `id`.
- Timestamps: `created_at`/`updated_at` where relevant, UTC.
- A **Finding** is a persistent logical issue, not one CSV row/JSON object. A
  **FindingInstance** is one observation of a Finding in one Assessment. See
  [docs/DATA_MODEL.md](docs/DATA_MODEL.md) for full field lists.
- Findings are deduplicated across assessments via a deterministic
  `fingerprint` (sha256 of normalized_type + domain + asset identifier +
  discriminator) — see [docs/PENTERA_IMPORT.md](docs/PENTERA_IMPORT.md).
- Status workflow: `OPEN → TRIAGED → ASSIGNED → IN_REMEDIATION →
  READY_FOR_VALIDATION → VALIDATED → CLOSED`, plus side-states
  `RISK_ACCEPTED`, `FALSE_POSITIVE`, `DEFERRED`, `REOPENED`. **A remediation
  action can move a finding to `READY_FOR_VALIDATION` at most — only a
  validation record can move it to `VALIDATED`.**
- Migrations: every model change gets an Alembic revision
  (`alembic revision --autogenerate -m "..."`). Don't hand-edit the DB schema.

## What NOT to build yet

Do not implement (see [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md) for the full
list and rationale): Neo4j/attack-path graphing/BloodHound ingestion,
PingCastle/Purple Knight/Defender for Identity ingestion, automatic
PowerShell remediation or validation, any real AD/LDAP connection or remote
agents, SSO/complex RBAC, Jira/ServiceNow integration, AI/LLM remediation
features, Kubernetes or cloud deployment infra. The `integrations/` folder
shape should stay ready for these, but only `pentera/` is implemented.

## Current implementation status

_Last updated: 2026-08-20 (seventh checkpoint — Pentera JSON ingestion added)._

**New this checkpoint**: Pentera **JSON** import, alongside the existing CSV
path — JSON is now the preferred format (Pentera's real export for this
deployment; CSV remains fully supported; PDF still not supported).

- [x] `backend/app/integrations/pentera/json_parser.py` (new): defensive
      JSON parser — detects the findings collection (top-level array,
      known-key nested array, or largest-array fallback with a warning),
      handles nested `asset`/`target`/`host` sub-objects, never silently
      drops a sibling collection, produces the exact same `RawPenteraRow`
      shape the CSV parser does.
- [x] `mapper.py` **unchanged** — both parsers feed it identically, proving
      the "reuse the same normalized model" requirement in practice, not
      just in design intent.
- [x] `import_service.py` refactored: shared `_import_parsed_rows()` core,
      thin `import_pentera_csv`/`import_pentera_json` wrappers. CSV
      behavior verified unchanged (same 44 pre-existing tests still pass
      after the refactor, before any JSON code was added).
- [x] `services/redaction.py`: new `redact_json()` — recursive redaction
      through arbitrarily nested dicts/lists, reusing the same
      header-pattern + inline-pattern logic as CSV. Explicitly covers
      `nt_hash`/`lm_hash`/`cracked_password`/`credentials` etc. (verified
      via substring-match on the existing pattern list, no new patterns
      needed).
- [x] `routers/imports.py`: single `/imports/pentera` endpoint now accepts
      `.json` or `.csv`, dispatches by extension. Raw JSON is read into
      memory and never written to disk — identical to the CSV path.
      LOCAL_ONLY guarantees unaffected (no new outbound calls introduced).
- [x] `ImportSummary`/`ImportSummaryOut` gained `unknown_mappings` (count
      of findings imported as `UNKNOWN` — never discarded solely for being
      unfamiliar, per the explicit requirement).
- [x] Frontend: upload control now accepts `.json,.csv`, labeled "Pentera
      JSON or CSV" (PDF intentionally not enabled), summary card shows
      Unknown Mappings.
- [x] Tests: 28 new (20 `test_pentera_json_parser.py` unit tests covering
      top-level array / nested array / unknown-structure fallback /
      missing fields / recursive credential redaction / inline secrets /
      malformed JSON / empty JSON / non-object array elements; 4
      `test_import_service_json.py` covering cross-import dedup, unknown
      finding handling, and skip-on-missing-fields at the full
      import-service level; 4 `test_api_json_import.py` at the router
      level including a CSV-still-works regression check). **72 total
      backend tests pass** (44 pre-existing + 28 new), frontend build+lint
      clean.
- [x] `scripts/generate_sample_data.py` extended to also emit
      `sample-data/pentera_assessment_3_2026-09-15.json` — a genuinely
      JSON-shaped sample (nested `asset` objects, not flattened columns)
      continuing the same fabrikam.local risk-reduction story, proving
      cross-format dedup (JSON assessment 3 recognizes CSV assessment 2's
      recurring findings as the same logical issues).
      `scripts/load_sample_data.py` now loads all three.
- [x] Docs updated: README, this file, and especially
      `docs/PENTERA_IMPORT.md` (new "JSON format handling" section) and
      `docs/ARCHITECTURE.md` (adapter diagram now shows both parsers
      converging on the shared mapper).
- [x] **Explicit, honest limitation stated everywhere it matters** (code
      docstring, docs/PENTERA_IMPORT.md, README): JSON support is
      structurally defensive but has **not** been validated against a real
      sanitized Pentera JSON export — this session had no such sample to
      work from. Every import's warnings surface when the parser had to
      guess at structure, so a real-export test will be self-diagnosing if
      the guesses are wrong.

_Prior checkpoint (sixth) — one-command startup added:_

**New that checkpoint**: `start.sh` (macOS/Linux, verified end-to-end
multiple times) and `start.ps1` (Windows, written but unverified — no
Windows/pwsh available in this dev environment) give a single-command
local startup: tool checks → venv create/reuse → conditional dependency
install → `DATABASE_URL`/`LOCAL_ONLY` env → `alembic upgrade head` →
security preflight (blocks startup on failure) → backend on
`127.0.0.1:8000` → frontend on `localhost:5173` → prints
`ADPA Tracker is running at http://localhost:5173`. `stop.sh`/`stop.ps1`
free ports 8000/5173 if a run didn't shut down cleanly. README's primary
"Quick start" is now `git clone && ./start.sh`; the old manual steps moved
to a "Manual / development startup" subsection, not deleted.

**Testing note on Ctrl+C**: verified the full lifecycle (start → run →
children terminated → `wait` unblocks → cleanup trap runs → clean exit)
end-to-end via `stop.sh` killing the backend/frontend processes directly.
Could **not** directly verify a literal terminal Ctrl+C keypress in this
non-interactive dev environment — `kill -INT`/`-TERM`/`-USR1` sent from a
separate tool invocation to a backgrounded bash script holding a `trap`
does not reach the handler here (confirmed via isolated minimal repros;
this looks like a sandbox/tool-environment characteristic, not a bash
logic bug — plain `kill` against non-trapped processes works fine, and
`start.sh` uses the standard, extremely common `trap ... INT TERM EXIT` +
background-PID + `wait` idiom). `stop.sh` is verified as the always-works
fallback regardless. If real interactive Ctrl+C ever doesn't clean up for
you, `./stop.sh` always will.

_Prior checkpoint (fifth) — network-exposure + LOCAL_ONLY hardening pass,
ahead of real-data use on a work laptop:_

**The MVP is functionally complete, verified end-to-end in a real browser,
and hardened for local-only use with real assessment data.** Two hardening
passes now: (1) redaction/logging/reset-script/gitignore work from the
prior checkpoint, and (2) this pass — Docker/uvicorn/Vite host bindings
locked to localhost/127.0.0.1, Postgres no longer published to the host at
all, LOCAL_ONLY/CORS documentation corrected to not overclaim (CORS is not
an egress firewall — said explicitly now), inline `key:value` credential
redaction added for free-text fields (closing the exact gap the user
flagged: `"password = X"` in a description), `reset_local_data.py` now
wipes owners by default, and a new `scripts/local_security_preflight.py`
static safety check. Docker Compose itself has still not been proven
end-to-end on this host (see "Docker Compose status" below) — the port-
binding fixes are reviewed/correct by inspection but unconfirmed against a
live `docker compose up`; the local SQLite fallback is what's actually
verified.

- [x] Repo structure, git init, docs (CLAUDE.md, docs/ARCHITECTURE.md,
      docs/DATA_MODEL.md, docs/PENTERA_IMPORT.md, docs/MVP_SCOPE.md)
- [x] Docker Compose + env (`docker-compose.yml`, `.env.example`,
      `backend/Dockerfile`, `frontend/Dockerfile`) — **not yet run
      end-to-end**; only the local Python/SQLite path and local
      `npm run build` have been verified so far.
- [x] Backend skeleton (`backend/app/main.py`, `core/config.py`, `core/db.py`)
- [x] Core DB schema (all 7 SQLAlchemy models) + Alembic migration
      (`backend/alembic/versions/31cd029594af_initial_schema.py`, generated
      and applied against SQLite; not yet run against real Postgres, but the
      models use portable types so it should Just Work)
- [x] Pentera parser/mapper/schemas + fingerprinting
      (`backend/app/integrations/pentera/`, `backend/app/services/fingerprint.py`)
- [x] Risk engine (`backend/app/services/risk_engine.py`)
- [x] Import service + `/imports/pentera` API
      (`backend/app/services/import_service.py`, `backend/app/routers/imports.py`)
- [x] Findings/Assessments/Remediation/Validation/Dashboard/Owners APIs
      (`backend/app/routers/*.py`) — all wired into `main.py`
- [x] Sample data: two sanitized fake Pentera CSVs in `sample-data/`
      (`pentera_assessment_1_2026-05-15.csv` = 48 findings,
      `pentera_assessment_2_2026-07-15.csv` = 43 findings: 10 resolved, 38
      recurring, 5 new — demonstrates ~22.6% risk reduction). Regenerate via
      `python3 scripts/generate_sample_data.py`. Load into a running backend
      via `python3 scripts/load_sample_data.py [API_BASE_URL]`.
- [x] Backend tests: 33 tests, all passing (`cd backend && source venv/bin/activate
      && pytest -q`) — covers CSV parsing tolerance, normalization/mapping,
      fingerprinting/dedup, risk scoring, repeated-assessment behavior
      (recurring/resolved/reopened), and the full API workflow (assign →
      remediate → block-direct-validate → validate → dashboard comparison).
- [x] Frontend shell: Vite + React + TypeScript + Tailwind CSS v4 (via
      `@tailwindcss/vite`, not the old `tailwind.config.js`/postcss flow) +
      Recharts + React Router. Dark enterprise-security styling. Sidebar nav
      (Overview / Assessments / Findings). `npm run build` passes clean
      (tsc -b && vite build), no TS errors.
- [x] Typed API client (`frontend/src/api/client.ts`,
      `frontend/src/api/types.ts`) mirroring `backend/app/schemas/*.py`.
- [x] Assessment upload UI + import summary
      (`frontend/src/pages/Assessments.tsx` — new-assessment form with CSV
      upload → shows `ImportSummaryOut` with warnings;
      `frontend/src/pages/AssessmentDetail.tsx` — per-assessment
      priority distribution + previous-assessment comparison).
- [x] Findings table + detail page
      (`frontend/src/pages/Findings.tsx` — search + priority/status/category/
      severity/owner filters, all wired to the GET /findings query params;
      `frontend/src/pages/FindingDetail.tsx` — risk explanation, asset info,
      assessment history, owner/status editing, remediation notes form,
      validation recording form).
- [x] Dashboard UI (`frontend/src/pages/Overview.tsx` — top metric cards,
      remediation funnel, Recharts pie (priority) + bar (category) charts,
      assessment comparison card).
- [x] **Full demo flow verified live in a real browser** (Claude Browser
      pane, not just `tsc`/`vite build`) against a running backend
      (`uvicorn` + SQLite) with the two sample assessments loaded: dashboard
      → findings list/filters → finding detail → created an owner inline →
      assigned it → `ASSIGNED` → `IN_REMEDIATION` → added a remediation note
      → `READY_FOR_VALIDATION` → recorded a `PASS` validation → `VALIDATED`
      → assessment detail page shows the 22.6% risk-reduction comparison.
      Every number shown in the UI was cross-checked against the API
      response. See "Known gaps" below for the one cosmetic issue found and
      fixed.
- [ ] **Docker Compose stack — BLOCKED, not application code's fault.** See
      "Docker Compose status" below.
- [x] README polished (this pass).

### Verified working, live, in a browser (this session)

- Dashboard: top metrics, remediation funnel, priority pie chart, category
  bar chart, and the assessment-over-assessment comparison card (39.4 →
  30.5 risk score, 22.6% reduction, 5 new / 38 recurring / 10 resolved) —
  all matched the API response exactly.
- Findings table: all 53 findings rendered, search/priority/status/
  category/severity/owner filters all present and wired to real query
  params; resolved (no-longer-observed) findings shown dimmed.
- Finding detail: risk explanation with all 5 scoring reasons rendered
  correctly for a P1 (100/100) finding; assessment history; remediation
  guidance.
- **Owner creation did not have a UI** when first tested — fixed this
  session by adding a "+ New owner / team" inline quick-add form to
  `FindingDetail.tsx` (`QuickAddOwner` component) that calls
  `POST /owners`. This was the only real gap found during live testing.
- Full workflow via the UI: assign owner (auto-moved `OPEN` → `ASSIGNED`) →
  moved to `IN_REMEDIATION` → added a remediation note + moved to
  `READY_FOR_VALIDATION` → recorded a `PASS` validation → status became
  `VALIDATED`. Confirmed both in the UI (after a fresh page load) and via
  direct API query.
- Assessment detail page: per-assessment priority distribution, previous-
  vs-current comparison, and import warnings list all render correctly.
- Browser console checked clean in a fresh tab (one stale HMR-only error
  from a live file edit did not reproduce after a hard reload / new tab).

### Docker Compose status: engine unavailable on this host, app runs fine via local fallback

`docker compose up --build` was attempted twice this session:

1. **First attempt**: both images built successfully (backend + frontend),
   but creating the Postgres container failed with `input/output error`.
   Root cause: the host disk had only ~160MB free — Docker's own internal
   metadata DBs couldn't be written.
2. User freed disk space (1.7GB free afterward). Restarted Docker Desktop.
   **Second attempt**: `docker compose version` works fine (CLI is present,
   v2.39.1-desktop.1), but `docker version` / `docker info` hung
   indefinitely with zero output — even the client-side portion, which
   normally doesn't need the daemon — and had to be force-killed. This
   points to the **Docker engine/daemon itself being unresponsive**, most
   likely because the earlier full-disk incident left its internal VM/DB
   state in a bad spot. This is a host Docker Desktop issue, not an
   application or `docker-compose.yml`/`Dockerfile` problem — both images
   build cleanly when the daemon is reachable enough to build them.

**Per explicit user direction, further Docker debugging was stopped** (not
worth burning time on a host installation issue) in favor of the documented
local fallback — which is fully working right now:

```bash
# Backend
cd backend && source venv/bin/activate
export DATABASE_URL=sqlite:///./app.db
uvicorn app.main:app --host 127.0.0.1 --port 8000 &

# Frontend
cd frontend && npm run dev &

# Sample data
python3 scripts/load_sample_data.py http://localhost:8000
```

Verified live: dashboard at `total_findings=53`, `overall_risk_score=30.5`,
`risk_reduction_pct=22.6` — matches every prior verification.

**Next session, if Docker is wanted**: try `docker compose up --build`
again — if it still hangs, Docker Desktop likely needs a manual
troubleshoot/reset from its own UI (Settings → Troubleshoot → "Clean /
Purge data" or similar), which is a destructive action outside what an
agent should do autonomously. **This is not required to demo or use the
MVP** — the local fallback is the fully-supported dev path and is what's
actually running right now.

### Known gaps / not yet verified

- **Docker Compose has never successfully brought up all three services in
  this environment** (disk-full, then daemon-unresponsive). The
  `docker-compose.yml`/`Dockerfile`s are believed correct (images built
  clean both times) but the full stack has literally never gone green here.
  This is the only remaining item before the MVP can be called fully done
  per the original spec's Docker requirement — it does not block using or
  demoing the app today via the local fallback.
- `backend/app.db` (SQLite dev DB), `backend/venv/`, and
  `frontend/node_modules/` are git-ignored and untracked, as intended —
  regenerate with the commands below.
- A local `.env` (copied from `.env.example`) exists on disk from the
  Docker attempts but is git-ignored, as intended — not committed.

## How to run the project right now

```bash
# Backend
cd backend
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=sqlite:///./app.db
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
# API docs: http://localhost:8000/docs

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
# App: http://localhost:5173

# Sample data (separate terminal, from repo root, backend must be running)
python3 scripts/load_sample_data.py http://localhost:8000
```

## Git / GitHub status

- Local git repo initialized, branch `main`.
- Remote `origin` = `https://github.com/Tahaa21/adpa-tracker.git` (connected
  this session). The remote repo pre-existed with a single placeholder commit
  (`README.md` containing only `# adpa-tracker`) — reconciled by keeping our
  full README and merging histories rather than force-pushing.
- GitHub CLI (`gh`) is **not installed** in this environment, so GitHub
  issues have not been created/updated from here. If `gh` becomes available:

  ```bash
  gh issue create --title "..." --body "..."
  ```

## Next recommended task (pick up here)

**The MVP itself needs no further work to be demoable** — `./start.sh`
brings it up fully working (backend on :8000, frontend on :5173, sample
data loadable in one command). Three open items remain, none blocking:

1. **Validate `json_parser.py` against a REAL sanitized Pentera JSON
   export.** This is the most important of the three — everything about
   the JSON parser is currently structurally defensive, not
   schema-verified, because this session had no real export to work from.
   Next session: get one real sanitized Pentera JSON export (or at minimum
   its top-level structure + a couple of full sample finding objects with
   values replaced by placeholders), import it via the UI, read the
   warnings carefully (they'll say exactly what structure was guessed —
   e.g. "no standard findings key... used the largest array... review
   this"), and adjust `FIELD_ALIASES`/`KNOWN_COLLECTION_KEYS`/
   `ASSET_CONTAINER_KEYS` in `json_parser.py` to match reality. This is a
   targeted data-driven fix, not a redesign — the pipeline
   (parser→mapper→import_service) doesn't change regardless of what's
   found.
2. **Verify `start.ps1`/`stop.ps1` on an actual Windows machine.** Written
   to mirror `start.sh` exactly, syntax-reviewed carefully, but never
   executed — no Windows/pwsh available in this dev environment. Run it,
   fix whatever breaks (most likely candidates: the `Scripts\` vs `bin/`
   venv path handling, or the `vite.cmd` invocation via `Start-Process`).
3. **Prove Docker Compose end-to-end** on a host where the Docker engine is
   actually responsive (`docker info` should return in a few seconds, not
   hang — if it hangs, Docker Desktop's engine is stuck and needs a manual
   restart/reset from its own UI; don't spend more than a couple minutes on
   this before falling back to `./start.sh`, it has blocked multiple past
   sessions). Once responsive: `docker compose up --build`, confirm all
   three containers come up healthy and the backend runs its Alembic
   migration against real Postgres, optionally re-run
   `scripts/load_sample_data.py` against it.

Everything else — backend logic, all APIs, the full frontend, the complete
demo workflow, both Pentera import formats' code paths, and the one-command
macOS/Linux startup — is built, tested, and has been verified live across
multiple sessions. None of the three remaining items is a "re-verify
everything" task, and none blocks using or demoing the product today via
`./start.sh` (with CSV, or with JSON keeping in mind item 1's caveat).
