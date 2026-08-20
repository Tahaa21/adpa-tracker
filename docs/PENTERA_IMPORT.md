# Pentera Import

This is the most important feature of the MVP. It must tolerate real-world
variance in Pentera CSV exports without crashing, and it must recognize the
same logical issue across repeated monthly assessments.

## Pipeline

```
Pentera CSV
    ↓ parser.py    — read file, sniff dialect, produce raw row dicts + warnings
    ↓ mapper.py     — alias-map columns → NormalizedFinding, classify type/category/severity
    ↓ schemas.py     — Pydantic shape for the raw + normalized finding
    ↓ import_service — fingerprint, upsert Asset/Finding, create FindingInstance, score risk
Application (Finding / FindingInstance)
```

## Column tolerance strategy (`parser.py` + `mapper.py`)

Pentera exports are not guaranteed to use identical headers between versions.
The mapper keeps an **alias table**: normalized field → list of accepted header
names (case-insensitive, whitespace/punctuation-normalized). Example:

| normalized field | accepted aliases |
|---|---|
| `title` | `Finding`, `Finding Name`, `Vulnerability`, `Title`, `Issue` |
| `severity` | `Severity`, `Risk Severity`, `Risk Level`, `Criticality` |
| `asset_name` | `Asset`, `Target`, `Host`, `Affected Asset`, `Object Name` |
| `asset_type` | `Asset Type`, `Object Type`, `Entity Type` |
| `domain` | `Domain`, `Environment` |
| `description` | `Description`, `Details`, `Summary` |
| `recommendation` | `Recommendation`, `Remediation`, `Mitigation`, `Guidance` |
| `category` | `Category`, `Attack Category`, `Module` |
| `identifier` | `Object SID`, `SID`, `SAM Account Name`, `Identifier`, `DN`, `Distinguished Name` |
| `exploitable` | `Exploitable`, `Confirmed`, `Verified` |

Matching is done by normalizing headers (`lower()`, strip, collapse
non-alphanumerics) and comparing against a normalized alias set, so
`"Risk Severity"`, `risk_severity`, and `RISK SEVERITY` all resolve the same way.

Any CSV column that does not match a known alias is **not discarded** — it is
kept verbatim in `source_metadata.unmapped_fields` on the `Finding`/`FindingInstance`,
so nothing is silently lost even if the parser doesn't understand it.

### Failure handling

- Missing required columns (no recognizable title/asset column at all) →
  the whole import is rejected with a clear error before any rows are written.
- A single bad row (e.g. empty title) → the row is skipped, counted in
  `rows_skipped`, and a warning is recorded with the row number and reason.
  The rest of the import continues.
- An unrecognized finding title/type → still imported, using
  `normalized_type = UNKNOWN`, `category = OTHER`, with the original title
  preserved in `source_metadata.source_title`. Unknown findings are never a
  hard failure.

Import always returns: `rows_processed`, `rows_imported`, `rows_skipped`,
and a `warnings: string[]` list.

## Normalization mapping (`mapper.py`)

`normalized_type` is chosen by matching the raw title against a keyword table,
first match wins, e.g.:

| raw title contains | normalized_type | category |
|---|---|---|
| "password" + "not required" | `PASSWORD_NOT_REQUIRED` | `ACCOUNT_HYGIENE` |
| "password" + "never expires" | `PASSWORD_NEVER_EXPIRES` | `ACCOUNT_HYGIENE` |
| "reversible encryption" | `REVERSIBLE_ENCRYPTION` | `CREDENTIAL_EXPOSURE` |
| "domain admin" | `DOMAIN_ADMIN_MEMBERSHIP` | `TIER_0` |
| "privileged group" | `PRIVILEGED_GROUP_MEMBERSHIP` | `PRIVILEGE` |
| "dcsync" / "dc sync" | `DCSYNC_EXPOSURE` | `TIER_0` |
| "password reuse" / "reused password" | `PASSWORD_REUSE` | `CREDENTIAL_EXPOSURE` |
| "leaked credential" / "breached password" | `LEAKED_CREDENTIAL` | `CREDENTIAL_EXPOSURE` |
| "weak password" / "cracked password" | `WEAK_PASSWORD` | `CREDENTIAL_EXPOSURE` |
| "dormant" + "privileged" | `DORMANT_PRIVILEGED_ACCOUNT` | `PRIVILEGE` |
| "delegation" | `DELEGATION_RISK` | `DELEGATION` |
| "acl" / "dacl" + "abuse" | `ACL_ABUSE` | `PRIVILEGE` |
| "password policy" | `PASSWORD_POLICY_WEAKNESS` | `POLICY_CONFIGURATION` |
| "service account" | `SERVICE_ACCOUNT_RISK` | `PRIVILEGE` |
| "trust" | `TRUST_RISK` | `TRUST` |
| *(no match)* | `UNKNOWN` | `OTHER` |

This table lives as data in `mapper.py` (`TYPE_RULES`) — extending it is a
one-line addition, not a structural change. `asset_type` is normalized
similarly from the source's asset-type column, defaulting to `unknown`.

Severity is normalized to `low|medium|high|critical` via a small alias map
(`critical/severe→critical`, `high→high`, `medium/moderate→medium`,
`low/informational→low`, default `medium`).

## Fingerprinting / deduplication (`services/fingerprint.py`)

Goal: importing next month's assessment recognizes the *same logical finding*
instead of creating a duplicate `Finding` row.

```
fingerprint = sha256(
    normalized_type
    + "|" + domain.lower().strip()
    + "|" + asset_external_identifier.lower().strip()
    + "|" + discriminator
).hexdigest()
```

- `asset_external_identifier` is the best available stable identifier for the
  asset (SID/SAM account name/DN/hostname — whatever the row provided; falls
  back to the normalized asset name if nothing else is present).
- `discriminator` is normalized_type-specific to avoid over-merging distinct
  issues on the same asset (e.g. two different weak-password findings on the
  same service account should usually still be the same logical issue, but a
  domain-level `PASSWORD_POLICY_WEAKNESS` finding shouldn't merge with an
  asset-level one). For MVP the discriminator is simply the normalized_type
  again (i.e. one Finding per `(normalized_type, domain, asset)` triple) — this
  is intentionally simple and documented here so it can be revisited if a real
  export shows it's too coarse or too fine.

On import, `import_service` looks up `Finding.fingerprint`:
- **match found** → reuse the `Finding`, create a new `FindingInstance` for the
  current `Assessment`, update `last_seen`, flip `currently_present = true`,
  and if the Finding had been `VALIDATED`/`CLOSED` move it to `REOPENED`.
- **no match** → create a new `Finding` (`first_seen = last_seen = assessment_date`,
  `status = OPEN`) plus its first `FindingInstance`.

After an import, any `Finding` that was `currently_present` before this
assessment but has **no** `FindingInstance` in the new assessment is marked
`currently_present = false` (still visible for history/trend purposes, just no
longer active) — this is how the dashboard shows "resolved / no longer
observed".

## Import summary contract

`POST /imports/pentera` returns:

```json
{
  "assessment_id": 3,
  "rows_processed": 52,
  "rows_imported": 50,
  "rows_skipped": 2,
  "warnings": [
    "Row 14: missing finding title, skipped",
    "Row 37: unrecognized asset type 'container', defaulted to 'unknown'"
  ],
  "new_findings": 12,
  "recurring_findings": 38,
  "resolved_findings": 6
}
```
