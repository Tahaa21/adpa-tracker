# Architecture

## Overview

```
┌─────────────┐      REST/JSON      ┌──────────────────┐      SQLAlchemy      ┌────────────┐
│  React SPA  │  ─────────────────▶ │  FastAPI backend  │  ──────────────────▶ │ PostgreSQL │
│ (Vite + TS) │  ◀───────────────── │                    │  ◀────────────────── │ (or SQLite)│
└─────────────┘                     └──────────────────┘                       └────────────┘
```

- **Frontend**: React + TypeScript + Vite + Tailwind CSS + Recharts. Talks to the
  backend only through the REST API (`VITE_API_BASE_URL`). No direct DB access.
- **Backend**: Python + FastAPI + Pydantic (request/response schemas) + SQLAlchemy
  (ORM) + Alembic (migrations).
- **Database**: PostgreSQL via Docker Compose is the intended deployment database.
  SQLite is supported as a zero-config local dev fallback (`DATABASE_URL=sqlite:///./app.db`)
  because it removes the Docker dependency for fast iteration; schema is kept
  portable (no Postgres-only types in the core models) so both work from the same
  models/migrations story.

## Backend layout

```
backend/app/
├── main.py                # FastAPI app, router registration, CORS
├── core/
│   ├── config.py          # settings (env vars)
│   └── db.py              # SQLAlchemy engine/session
├── models/                # SQLAlchemy ORM models (the internal data model)
│   ├── assessment.py
│   ├── asset.py
│   ├── finding.py
│   ├── finding_instance.py
│   ├── owner.py
│   ├── remediation.py
│   └── validation.py
├── schemas/                # Pydantic request/response DTOs
├── services/                # business logic (risk engine, fingerprinting, import orchestration)
│   ├── risk_engine.py
│   ├── fingerprint.py
│   └── import_service.py
├── routers/                # FastAPI route modules (thin controllers)
│   ├── assessments.py
│   ├── findings.py
│   ├── remediations.py
│   ├── validations.py
│   ├── dashboard.py
│   └── imports.py
└── integrations/            # source-system adapters — see below
    └── pentera/
        ├── parser.py
        ├── mapper.py
        └── schemas.py
```

## The adapter/normalization rule

**A source system's data model must never become the application's data model.**

Every assessment source gets its own adapter package under `app/integrations/<source>/`:

```
Source export (e.g. Pentera CSV)
        ↓
<source>/parser.py   — reads the raw file, tolerant of column/format variance,
                        produces raw row dicts + parse warnings/errors
        ↓
<source>/schemas.py  — typed "raw finding" shape for that source
        ↓
<source>/mapper.py   — maps raw fields → normalized_type, category, severity,
                        asset info, preserves anything unmapped into source_metadata
        ↓
Normalized Finding / FindingInstance (internal model, source-agnostic)
        ↓
Application (risk engine, workflow, API, UI)
```

Routers and services never import from `integrations/pentera` directly except
through `import_service.py`, which calls the adapter and then writes normalized
`Finding`/`FindingInstance`/`Asset` rows. This is what makes it possible to add
`integrations/bloodhound/`, `integrations/pingcastle/`, `integrations/purpleknight/`,
`integrations/defender_identity/` later without touching the core model, risk
engine, workflow, or UI. **Those integrations are not implemented in this MVP** —
only the folder shape and the boundary rule are in place.

## Request flow example: Pentera import

1. `POST /imports/pentera` (multipart file + assessment metadata) hits
   `routers/imports.py`.
2. The router validates file type/size and delegates to
   `services/import_service.py`.
3. `import_service` calls `integrations/pentera/parser.py` to read the CSV into
   raw rows + warnings, then `integrations/pentera/mapper.py` to normalize each
   row into a `NormalizedFinding` (Pydantic, in `integrations/pentera/schemas.py`).
4. For each normalized finding, `import_service`:
   - resolves/creates the `Asset`,
   - computes a fingerprint (`services/fingerprint.py`) and finds-or-creates the
     logical `Finding`,
   - creates a `FindingInstance` linked to the current `Assessment`,
   - runs `services/risk_engine.py` to (re)compute `risk_score`/`priority` on the
     `Finding`,
   - updates `first_seen`/`last_seen`.
5. Returns an import summary (rows processed/imported/skipped, warnings).

## Frontend layout

```
frontend/src/
├── main.tsx / App.tsx        # router setup
├── api/                       # typed fetch client for the REST API
├── pages/
│   ├── Overview.tsx            # dashboard
│   ├── Assessments.tsx
│   ├── AssessmentDetail.tsx
│   ├── Findings.tsx
│   └── FindingDetail.tsx
├── components/                 # shared UI (badges, cards, tables, charts)
└── types/                      # TS types mirroring backend Pydantic schemas
```

The frontend is a thin presentation layer. All scoring, normalization, and
workflow-transition logic lives in the backend so the API is the single source
of truth (important since this will later grow CLI/automation clients).

## Why these boundaries

- Keeps the Pentera-specific quirks (inconsistent column names, per-export
  differences) contained to one small package instead of leaking into the schema,
  the risk engine, or the UI.
- Makes "add another assessment source" an additive change, not a rewrite.
- Keeps risk scoring and workflow state transitions testable independent of any
  particular source format.
