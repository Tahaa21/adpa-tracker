# AD Security Remediation Tracker

A remediation operations platform that sits between AD security assessment
and measurable risk reduction:

```
Security Assessment → Risk Prioritization → Remediation → Validation → Risk Reduction
```

It ingests Pentera Active Directory assessment findings, normalizes them into
an internal data model, scores and prioritizes them (P1/P2/P3), and tracks
them through an owner/status remediation workflow and a manual validation
workflow — so you can answer: *what should we fix first, who owns it, has it
been fixed, and can we show risk was reduced?*

This is **not** an attack-path graphing tool and does not replace BloodHound.
See [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md) for exactly what is and isn't in
scope for this MVP.

## Stack

- **Frontend**: React + TypeScript + Vite + Tailwind CSS + Recharts
- **Backend**: Python + FastAPI + Pydantic + SQLAlchemy + Alembic
- **Database**: PostgreSQL (via Docker Compose) — SQLite supported as a
  zero-config local dev fallback
- **Local env**: Docker + Docker Compose

## Quick start (Docker Compose)

```bash
cp .env.example .env
docker compose up --build
```

- Backend API + docs: http://localhost:8000/docs
- Frontend: http://localhost:5173

Load the sanitized sample data (two Pentera-style assessments) once the
backend is up:

```bash
python3 scripts/load_sample_data.py http://localhost:8000
```

## Quick start (local, no Docker)

**Backend** (Python 3.12+, SQLite):

```bash
cd backend
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=sqlite:///./app.db
alembic upgrade head
uvicorn app.main:app --reload
```

**Frontend**:

```bash
cd frontend
npm install
npm run dev
```

**Tests**:

```bash
cd backend && source venv/bin/activate && pytest
```

## Documentation

- [CLAUDE.md](CLAUDE.md) — orientation for AI coding agents working in this
  repo: scope, architecture rules, conventions, implementation status
- [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md) — what's in/out of scope, definition
  of done
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system architecture, the
  Pentera adapter boundary rule
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md) — Assessment / Asset / Finding /
  FindingInstance / Owner / Remediation / ValidationRecord
- [docs/PENTERA_IMPORT.md](docs/PENTERA_IMPORT.md) — tolerant CSV parsing,
  normalization rules, fingerprinting/dedup algorithm

## Repository structure

```
ad-security-remediation-tracker/
├── frontend/          React app (Vite)
├── backend/           FastAPI app (models, schemas, services, routers,
│                       integrations/pentera adapter)
├── sample-data/       sanitized fake Pentera-style CSVs (2 assessments)
├── docs/              architecture/data model/import/scope docs
├── scripts/           sample data generation + loading helpers
├── docker-compose.yml
└── .env.example
```

## Security notes

- No real Pentera exports, credentials, domain names, or customer data are
  committed to this repo — `sample-data/` contains only fabricated data
  against the fictional `fabrikam.local` domain.
- `.env` is git-ignored; copy `.env.example` and fill in local values.
- Validation is manually recorded in this MVP — there is no remote
  PowerShell execution or live AD/LDAP connection.

## License

Not yet licensed for external use — internal/demo project.
