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

All host port mappings in `docker-compose.yml` are bound to `127.0.0.1`
explicitly (not published to the LAN), and PostgreSQL publishes no host
port at all — the backend reaches it over the internal Compose network
only. See [docs/LOCAL_DATA_SECURITY.md](docs/LOCAL_DATA_SECURITY.md) for
the full network-exposure breakdown.

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
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

`--host 127.0.0.1` is explicit on purpose — it's uvicorn's default anyway,
but this app is written to be run with real, sensitive assessment data, so
the localhost binding is stated rather than left implicit. Never change
this to `--host 0.0.0.0` or omit `--host` when relying on documentation
that assumes localhost-only. See [docs/LOCAL_DATA_SECURITY.md](docs/LOCAL_DATA_SECURITY.md).

**Frontend**:

```bash
cd frontend
npm install
npm run dev
```

`vite.config.ts` has no `server.host` override, so this binds to localhost
only (Vite's default) — never add `host: true` or `host: '0.0.0.0'` there.

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
- [docs/LOCAL_DATA_SECURITY.md](docs/LOCAL_DATA_SECURITY.md) — **read this
  before importing real assessment data**: what's stored/where, network
  exposure, credential redaction, upload retention, logging, reset/reseed
  workflows, the exact "Work Laptop / Real Data" procedure, and honestly-
  stated limitations

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
- `LOCAL_ONLY=true` by default: CORS is force-restricted to localhost
  origins, and every service (Docker or not) binds to `127.0.0.1`/
  localhost only — see [docs/LOCAL_DATA_SECURITY.md](docs/LOCAL_DATA_SECURITY.md)
  for exactly what that does and does not guarantee (it's an application-
  level safeguard, not a network firewall).
- Before importing real assessment data: run
  `python3 scripts/local_security_preflight.py` and confirm it prints
  `PASS: Local-only security preflight`.
- Uploaded CSVs are parsed in memory and never written to disk. Columns
  that look like credentials/secrets are redacted before anything is
  persisted (both whole flagged columns and inline `key: value` patterns
  in free text) — see docs/LOCAL_DATA_SECURITY.md for the exact scope and
  known limitations.
- Reset all local assessment data anytime with
  `python3 scripts/reset_local_data.py --yes` (never touches source code
  or git history). Reseed sanitized demo data with
  `python3 scripts/load_sample_data.py`.
- Validation is manually recorded in this MVP — there is no remote
  PowerShell execution or live AD/LDAP connection.
- No authentication exists yet (by design, for this MVP) — localhost-only
  binding is the actual access control. Don't bind this app to anything
  other than localhost while real data is loaded.

## License

Not yet licensed for external use — internal/demo project.
