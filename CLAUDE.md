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

_Last updated: 2026-08-20 (mid-implementation checkpoint)._

**Backend: fully working and tested. Frontend: not started yet (empty directory).**

- [x] Repo structure, git init, docs (CLAUDE.md, docs/ARCHITECTURE.md,
      docs/DATA_MODEL.md, docs/PENTERA_IMPORT.md, docs/MVP_SCOPE.md)
- [x] Docker Compose + env (`docker-compose.yml`, `.env.example`) — **not yet
      run end-to-end**; only the local Python/SQLite path has been verified
      so far. `docker compose up --build` should work but has not been tested
      in this session.
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
- [ ] **Frontend — NOT STARTED.** `frontend/` directory exists but is empty.
      This is the next and most important remaining piece.
- [ ] Assessment upload UI + import summary
- [ ] Findings table + detail drawer/page
- [ ] Dashboard UI (Recharts)
- [ ] End-to-end verified against the real UI, README polished
- [ ] Git: **not yet committed as of this checkpoint** — see below.

### Verified working (backend, via curl / TestClient, this session)

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

- Docker Compose stack has not been run in this session (only local SQLite +
  uvicorn was tested). Backend `Dockerfile` and `docker-compose.yml` exist but
  need a `docker compose up --build` smoke test.
- No Postgres run yet — only SQLite. Models avoid Postgres-only types so this
  should be low-risk, but has not been proven.
- Frontend does not exist yet — no `package.json`, no Vite config, nothing in
  `frontend/`.
- `backend/app.db` (SQLite dev DB) and `backend/venv/` are git-ignored and
  untracked, as intended — regenerate with the commands below.

## How to run the project right now (backend only, since frontend isn't built)

```bash
cd backend
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=sqlite:///./app.db
alembic upgrade head
uvicorn app.main:app --reload
# API docs: http://localhost:8000/docs

# in another terminal, from repo root:
python3 scripts/load_sample_data.py http://localhost:8000
```

## Git / GitHub status

- Local git repo initialized (`main` branch), but **had zero commits** until
  this checkpoint — see git log for the actual checkpoint commit.
- GitHub CLI (`gh`) is **not installed** in this environment, so no GitHub
  repo has been created and nothing has been pushed. To do so once `gh` is
  available and authenticated:

  ```bash
  gh repo create ad-security-remediation-tracker --private --source=. --remote=origin
  git push -u origin main
  ```

  Or without `gh`, create the repo manually on GitHub then:

  ```bash
  git remote add origin <repo-url>
  git push -u origin main
  ```

## Next recommended task (pick up here)

**Build the frontend.** In order:

1. `npm create vite@latest frontend -- --template react-ts`, add Tailwind CSS
   and Recharts, set up React Router with the sidebar nav
   (Overview/Assessments/Findings/Remediation/Validation).
2. A small typed `frontend/src/api/client.ts` wrapping `fetch` against
   `VITE_API_BASE_URL`, with types mirroring `backend/app/schemas/*.py`.
3. Assessments page: list + "New Assessment" form (name/date/environment/notes
   + CSV file) → POST `/imports/pentera` → show the `ImportSummaryOut` result.
4. Findings page: table bound to GET `/findings` with the filter params it
   already supports (`search`, `priority`, `status`, `category`, `severity`,
   `owner_id`), clicking a row opens a detail view (GET `/findings/{id}`) with
   owner/status editing (PATCH `/findings/{id}`), remediation notes (POST
   `/remediations`), and validation entry (POST `/validations`).
5. Overview/dashboard page bound to GET `/dashboard`, using Recharts for the
   priority/category distributions and the assessment comparison numbers.
6. Once the UI round-trips the full demo flow from `docs/MVP_SCOPE.md`
   ("Definition of done"), do the Docker Compose smoke test, then README
   polish and a final commit.

Everything the frontend needs already exists and is tested on the backend —
this is now a pure frontend-building task, not backend design work. Re-read
`docs/ARCHITECTURE.md`'s "Frontend layout" section before starting.
