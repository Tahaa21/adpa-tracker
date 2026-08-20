# Data Model

## Entity overview

```
Assessment (one import event)
    │
    │  1:N
    ▼
FindingInstance ──────────▶ Finding (persistent logical issue)
    ▲                            │
    │ N:1                        │ N:1
    │                            ▼
Assessment                     Asset

Finding ──1:N──▶ Remediation (append-only history, latest = current state)
Finding ──1:N──▶ ValidationRecord

Owner ◀──assigned to── Finding.owner_id (also denormalized on Remediation)
```

`Finding` is the durable, cross-assessment concept ("Password Not Required on
svc_backup"). `FindingInstance` is "this Finding was observed in this
Assessment". Repeated imports create new `FindingInstance` rows against the
**same** `Finding` when the fingerprint matches, which is what enables trend
analysis (present/absent across assessments).

## Assessment

One row per import event.

| field | notes |
|---|---|
| id | PK |
| name | user-provided label, e.g. "Q3 AD Assessment" |
| source | `pentera` (free text, future sources add their own value) |
| assessment_date | date the assessment was performed (user-provided) |
| imported_at | server timestamp of the import |
| environment | optional domain/environment label |
| source_filename | sanitized original filename |
| notes | free text |
| risk_score | computed aggregate risk score for this assessment snapshot |
| rows_processed / rows_imported / rows_skipped | import summary counters |
| import_warnings | JSON list of parse/mapping warnings |

## Asset

The AD object or system affected by a finding.

| field | notes |
|---|---|
| id | PK |
| external_identifier | best available stable identifier from the source (SAM account name, SID, hostname, DN...) |
| name | display name |
| asset_type | `user \| group \| computer \| domain \| policy \| service_account \| unknown` |
| domain | domain/environment the asset belongs to |
| criticality | `low \| medium \| high \| critical` (defaults to `medium`; `critical` implies Tier 0) |
| tier | optional explicit tier label, e.g. `0` |
| asset_metadata | JSON — anything else the source provided |

Assets are deduplicated on `(external_identifier, domain, asset_type)`.

## Finding

The persistent logical issue.

| field | notes |
|---|---|
| id | PK |
| fingerprint | deterministic dedup key, unique — see [PENTERA_IMPORT.md](PENTERA_IMPORT.md) |
| normalized_type | e.g. `PASSWORD_NOT_REQUIRED`, `UNKNOWN` |
| title | normalized, human-readable title |
| category | e.g. `TIER_0`, `IDENTITY_EXPOSURE` |
| asset_id | FK → Asset |
| severity | normalized `low \| medium \| high \| critical`, derived from source severity |
| risk_score | 0-100, from the risk engine |
| priority | `P1 \| P2 \| P3`, from risk score bands |
| risk_reasons | JSON list of strings explaining the score (the risk engine's output) |
| status | see workflow below |
| owner_id | FK → Owner, nullable |
| first_seen | earliest Assessment date this fingerprint was observed |
| last_seen | latest Assessment date this fingerprint was observed |
| currently_present | true if the most recent assessment still observed it |
| remediation_guidance | normalized guidance text (from mapper defaults, editable) |
| description | normalized description |
| source_metadata | JSON — original source title + any unmapped raw fields, for traceability |

## FindingInstance

One observation of a Finding within one Assessment.

| field | notes |
|---|---|
| id | PK |
| finding_id | FK → Finding |
| assessment_id | FK → Assessment |
| source_severity | raw severity string as given by the source |
| source_title | raw finding title as given by the source |
| raw_row | JSON — the full raw parsed row, for audit/debugging |
| observed_at | = assessment_date, denormalized for easy trend queries |

Unique on `(finding_id, assessment_id)`.

## Owner

Lightweight — no auth, no RBAC.

| field | notes |
|---|---|
| id | PK |
| name | e.g. "Identity Team" or a person's name |
| team | optional team label |
| email | optional |

## Remediation

Append-only actions taken against a Finding; the Finding's own `status`/`owner_id`
reflect the *current* state, Remediation rows are the history/notes trail.

| field | notes |
|---|---|
| id | PK |
| finding_id | FK → Finding |
| owner_id | FK → Owner, nullable |
| status | snapshot of Finding.status at the time of this entry |
| recommended_action | free text |
| remediation_notes | free text |
| due_date | optional |
| created_at / updated_at | timestamps |

## ValidationRecord

| field | notes |
|---|---|
| id | PK |
| finding_id | FK → Finding |
| validation_method | free text, e.g. "Manual AD query", "Pentera re-scan" |
| evidence | free text / short description (no file storage in MVP) |
| validation_date | date |
| result | `PASS \| FAIL \| INCONCLUSIVE` |
| validated_by | free text name |
| notes | free text |

## Finding status workflow

```
OPEN → TRIAGED → ASSIGNED → IN_REMEDIATION → READY_FOR_VALIDATION → VALIDATED → CLOSED
```

Side statuses reachable at any point prior to `CLOSED`:
`RISK_ACCEPTED`, `FALSE_POSITIVE`, `DEFERRED`, `REOPENED`.

Rules enforced by the API (see `services/`):
- A remediation action can move a Finding to `READY_FOR_VALIDATION` at most —
  **never directly to `VALIDATED`**.
- Only adding a `ValidationRecord` with `result = PASS` can move a Finding to
  `VALIDATED`. A `FAIL` validation moves it back to `IN_REMEDIATION` (reopened).
- `REOPENED` is used when a previously `VALIDATED`/`CLOSED` finding reappears in
  a later assessment (fingerprint match on a finding that had been resolved).

## Fingerprinting / dedup (summary)

See [PENTERA_IMPORT.md](PENTERA_IMPORT.md) for the exact algorithm. In short:
`sha256(normalized_type + affected asset external_identifier + domain + a
source-provided discriminator)`, so the same logical issue on the same asset in
the same domain reuses the same `Finding` across assessments.
