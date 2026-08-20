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

_Last updated: 2026-08-20 (second checkpoint — frontend scaffolded)._

**Backend: fully working and tested. Frontend: scaffolded and builds clean,
but NOT yet verified end-to-end against a live backend.**

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
- [ ] **NOT YET DONE: run the frontend against a live backend and click
      through the actual demo flow end-to-end** (upload → findings →
      assign → remediate → validate → second import → dashboard trends).
      This is the single most important remaining step — code has not been
      exercised in a browser yet, only `tsc`/`vite build` checked.
- [ ] Docker Compose stack smoke test (`docker compose up --build`) —
      not run this session.
- [ ] README polish pass after the live demo is confirmed working.

### Verified working (backend, via curl / TestClient, prior session)

- Upload a Pentera CSV → normalized findings with risk score/priority/reasons.
- Tolerant parsing across two different header sets (see the two sample CSVs).
- Unknown finding types import as `UNKNOWN`/`OTHER` instead of failing.
- Re-importing a second assessment correctly identifies new / recurring /
  resolved findings via fingerprint matching, and flips `currently_present`.
- Full workflow: assign owner → `IN_REMEDIATION` → blocked direct
  `VALIDATED` transition (400) → remediation note → `READY_FOR_VALIDATION` →
  validation `PASS` → `VALIDATED`. Validation `FAIL` correctly reopens to
  `IN_REMEDIATION`.
- Dashboard endpoint returns top metrics, remediation funnel, priority/category
  distribution, and previous-vs-current assessment comparison with risk
  reduction %.

### Known gaps / not yet verified

- **Frontend has not been run in a browser against the live backend yet** —
  only verified to type-check and build. Next session should start the
  backend (SQLite), start `npm run dev`, load sample data, and click through
  the whole `docs/MVP_SCOPE.md` "Definition of done" flow, fixing whatever
  breaks.
- Docker Compose stack has not been run in this session (only local SQLite +
  uvicorn was tested, and `npm run build` locally). Backend `Dockerfile`,
  `frontend/Dockerfile`, and `docker-compose.yml` exist but need a
  `docker compose up --build` smoke test.
- No Postgres run yet — only SQLite. Models avoid Postgres-only types so this
  should be low-risk, but has not been proven.
- `backend/app.db` (SQLite dev DB), `backend/venv/`, and
  `frontend/node_modules/` are git-ignored and untracked, as intended —
  regenerate with the commands below.

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

**Verify the frontend against the live backend, end to end.** The code for
every screen exists and builds clean, but has not been exercised in a
browser this session:

1. Start the backend (SQLite) and frontend per "How to run" above.
2. Load sample data via `scripts/load_sample_data.py`, or upload
   `sample-data/pentera_assessment_1_2026-05-15.csv` through the UI.
3. Walk the exact `docs/MVP_SCOPE.md` "Definition of done" flow by hand:
   dashboard → upload → findings list/filters → finding detail → assign
   owner → `IN_REMEDIATION` → remediation note → `READY_FOR_VALIDATION` →
   validation `PASS` → `VALIDATED` → import second assessment → dashboard
   shows new/recurring/resolved + risk reduction %.
4. Fix whatever breaks (likely candidates: CORS if `VITE_API_BASE_URL`
   mismatches, date input formatting, Tailwind v4 class issues since this
   project uses the newer `@tailwindcss/vite` plugin rather than the classic
   `tailwind.config.js` setup most examples show).
5. Then: `docker compose up --build` smoke test, README polish, final
   commit.

Re-read `docs/ARCHITECTURE.md`'s "Frontend layout" section and
`frontend/src/api/client.ts` before making changes — the API surface is
already complete and tested; this phase is about wiring/UI verification, not
new backend design.
