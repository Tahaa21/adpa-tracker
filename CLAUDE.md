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
definition of done. Short version: import Pentera CSV assessments, normalize
findings, score/prioritize them, run them through an owner/status/notes
remediation workflow and a manual validation workflow, and show risk-reduction
trends across repeated assessments on a dashboard.

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
│           └── pentera/     parser.py / mapper.py / schemas.py
├── sample-data/          sanitized fake Pentera-style CSVs (2 assessments)
├── docs/                 ARCHITECTURE.md, DATA_MODEL.md, PENTERA_IMPORT.md, MVP_SCOPE.md
├── scripts/               helper scripts (seed sample data, etc.)
├── docker-compose.yml
├── .env.example
└── README.md
```

## Development commands

Full stack via Docker Compose (Postgres):

```bash
cp .env.example .env
docker compose up --build
# backend: http://localhost:8000  (docs at /docs)
# frontend: http://localhost:5173
```

Backend only, local Python + SQLite (fastest iteration loop):

```bash
cd backend
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=sqlite:///./app.db
alembic upgrade head
uvicorn app.main:app --reload
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

Load sample data (after the backend is running):

```bash
python3 scripts/load_sample_data.py
```

## Architecture rules

1. **A source system's data model must never become the internal data model.**
   Pentera (and any future source) is normalized through
   `integrations/<source>/{parser,mapper,schemas}.py` into the internal
   `Finding`/`FindingInstance`/`Asset` model. See
   [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
2. Routers are thin; business logic (risk scoring, fingerprinting, import
   orchestration, workflow transitions) lives in `app/services/`.
3. The frontend only talks to the backend via the REST API — no direct DB
   access, no business logic duplicated client-side beyond simple display
   formatting.
4. All DB access goes through the SQLAlchemy ORM — no raw/string-built SQL.

## Database / model conventions

- Primary keys are integer autoincrement `id`.
- Timestamps: `created_at`/`updated_at` where relevant, UTC.
- A **Finding** is a persistent logical issue, not one CSV row. A
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

_Last updated: 2026-08-20 (fourth checkpoint — MVP verified working via
local fallback after Docker engine proved unresponsive on this host)._

**The MVP is functionally complete and verified end-to-end in a real browser
against a live backend, and is running right now via the local
Python/SQLite + npm dev fallback.** Docker Compose has not yet been proven
end-to-end on this host due to Docker Desktop issues unrelated to the
application code (see "Docker Compose status" below) — per explicit user
direction, this was not chased further so as not to block a working MVP.

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
uvicorn app.main:app --port 8000 &

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
uvicorn app.main:app --reload
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

**The MVP itself needs no further work to be demoable** — it's running
right now via the local fallback (backend on :8000, frontend on :5173,
sample data loaded). The only open item is proving Docker Compose end-to-end
on a host where the Docker engine is actually responsive:

1. Confirm Docker Desktop is healthy: `docker compose version` should
   return instantly; `docker info` should also return within a few seconds
   (not hang). If `docker info` hangs, Docker Desktop's engine is stuck —
   that needs a manual restart or troubleshoot/reset from its own UI. Do
   not spend more than a couple of minutes on this before falling back to
   local dev again; it has already blocked two sessions.
2. Once `docker info` is responsive: `cd /Users/tahaa/ad-sec-tracker &&
   docker compose up --build` (a `.env` already exists locally, copied from
   `.env.example`; it's git-ignored).
3. Confirm all three containers (`db`, `backend`, `frontend`) come up
   healthy, the backend connects to Postgres (not SQLite) and runs its
   Alembic migration successfully, and the frontend loads at
   `http://localhost:5173` and can talk to the backend at
   `http://localhost:8000`.
4. Optionally re-run `scripts/load_sample_data.py` against the
   Postgres-backed backend to confirm the import pipeline works identically
   against Postgres as it did against SQLite.
5. Commit.

Everything else — backend logic, all APIs, the full frontend, and the
complete demo workflow — is built, tested, and has been verified live in a
browser across multiple sessions. Docker Compose is the last checklist item,
not a "re-verify everything" task, and is not required to use or demo the
product.
