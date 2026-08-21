# Pentera Import

This is the most important feature of the MVP. It must tolerate real-world
variance in Pentera exports without crashing, and it must recognize the same
logical issue across repeated monthly assessments.

**JSON is the preferred Pentera format** (matches what Pentera actually
exports in practice for this deployment). **CSV remains fully supported.**
**PDF is not yet supported** — do not upload a PDF; the upload control only
accepts `.json`/`.csv`.

> ⚠️ **Pentera JSON support is structurally defensive but requires
> validation against a real sanitized Pentera export.** The JSON parser
> (`json_parser.py`) was built without access to an actual Pentera JSON
> export — see "JSON format handling" below for exactly what that means in
> practice and what to do if it guesses wrong on your real export.

## Pipeline

```
Pentera CSV                      Pentera JSON
    ↓ parser.py                      ↓ json_parser.py
    (read file, sniff dialect,       (parse JSON, locate the findings
     produce raw row dicts +          collection defensively, flatten
     warnings)                        nested asset objects, produce raw
                                       row dicts + warnings)
    ↓                                 ↓
    └──────────────┬──────────────────┘
                    ↓
              mapper.py        — alias-map fields → NormalizedFinding,
                                  classify type/category/severity
                    ↓
              schemas.py        — Pydantic shape for the raw + normalized finding
                    ↓
              import_service    — fingerprint, upsert Asset/Finding,
                                  create FindingInstance, score risk
                    ↓
     Application (Finding / FindingInstance)
```

Both formats produce the exact same `RawPenteraRow` shape and are fed into
the exact same `mapper.map_rows()` and `import_service._import_parsed_rows()`
— risk scoring, deduplication/fingerprinting, the remediation workflow, and
trend tracking are **entirely shared** and unmodified between CSV and JSON.
Only the parsing step (`parser.py` vs `json_parser.py`) differs. The
`POST /imports/pentera` endpoint dispatches between them by file extension
automatically — the frontend upload control is a single "Pentera JSON or
CSV" field, not two separate ones.

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
`unknown_mappings`, and a `warnings: string[]` list.

## JSON format handling (`json_parser.py`)

Real Pentera JSON structure is not something we've had access to validate
against — this parser is written defensively rather than against a known
schema, and is honest about that in its own module docstring, in every
import's warnings when it has to guess, and here.

**Finding-collection detection.** A Pentera JSON export could plausibly be:
a bare top-level array of finding objects; an object with the findings
under a common key (`findings`, `results`, `vulnerabilities`, `issues`,
`items`, `records`, `data`, `modules`, `checks`, `detections`, `risks`); or
something else entirely. The parser tries, in order:
1. Top-level array → treated as the findings directly.
2. An object with one of the known key names above, at any nesting depth,
   holding an array of objects → that array is used.
3. If neither matches: the **largest** array-of-objects found anywhere in
   the structure is used as a last resort, **with a warning** telling you
   exactly which key path was chosen and how many items it had — so this
   guess is always visible, never silent.
4. If nothing even remotely plausible exists anywhere in the structure →
   the whole import is rejected (`ParseError`), same as CSV's "no
   recognizable title/asset column" case.

**Never silently drops a section.** If another substantial array-of-objects
exists in the JSON alongside the one chosen as findings (e.g. a separate
`assets` or `modules` collection), a warning names it and its size so you
can check whether it should have been included instead/also.

**Field aliasing.** Same alias-table philosophy as CSV (see above), adapted
for JSON key naming — `"Finding Name"`, `finding_name`, and `findingName`
all normalize identically. See `FIELD_ALIASES` in `json_parser.py` for the
exact list.

**Nested asset objects.** Structured exports commonly represent the
affected asset as its own nested object rather than flat fields, e.g.
`{"finding": "...", "asset": {"name": "DC01", "type": "computer"}}`. The
parser looks for a sub-object under a container-like key (`asset`,
`target`, `host`, `object`, `entity`, `affected_asset`) and prefers its
`name`/`type`/`domain`/identifier-shaped fields over anything at the
finding's own top level.

**Unknown/unmapped fields are never discarded.** Every finding's complete
original JSON object is preserved (redacted, see below) as the audit-trail
raw copy, and any top-level key not consumed by field mapping is preserved
separately in `source_metadata.unmapped_fields` — exactly like CSV's
unmapped columns.

**Credential redaction, recursively.** `services/redaction.py`'s
`redact_json()` walks the entire nested structure — dicts, lists, any
depth — redacting any key that looks like a credential/secret (`password`,
`passwd`, `pwd`, `secret`, `credential`/`credentials`, `token`, `hash`,
`ntlm`, `nt_hash`, `lm_hash`, `cracked_password`, `cleartext`, `plaintext`,
`evidence`, etc. — matched via the same normalized-key comparison as CSV
headers) before anything is persisted, and additionally scans surviving
string values for inline `key: value`/`key=value` patterns. This applies
uniformly regardless of where in the structure a credential-shaped key
appears, not just at the top level of a finding object.

**If your real Pentera JSON export doesn't match these assumptions:** tell
us (a) the real top-level structure/key names, (b) a couple of full sample
finding objects with real values replaced by placeholders, and (c) any
field-naming differences from the alias table above. That's a targeted,
low-risk change to `FIELD_ALIASES`/`KNOWN_COLLECTION_KEYS`/
`ASSET_CONTAINER_KEYS` in `json_parser.py` — not a redesign.

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

### Intra-assessment duplicates

`FindingInstance` has `UNIQUE(finding_id, assessment_id)` — one logical
Finding gets at most one FindingInstance per Assessment, by design. A real
Pentera export can legitimately contain more than one source record that
resolves to the same logical Finding within a single file (exact duplicate
records, multiple evidence/attack-path records for one issue, or the same
affected object reported under more than one module). `import_service.py`
tracks fingerprints already seen **within the current import batch**
(an in-memory set, checked before any Asset/Finding/FindingInstance work
happens for a row) and coalesces any further match into the existing
FindingInstance rather than attempting a second insert. These are counted
separately as `duplicate_observations_coalesced` in the import summary —
**not** as `new_findings` or `recurring_findings`, which describe
cross-assessment history (did this logical issue exist before this file?),
not repeats within one file.

The whole per-assessment import (from creating the `Assessment` row through
the final `db.commit()`) is one explicit atomic transaction — any exception
anywhere in that span triggers an explicit `db.rollback()` before
re-raising, so a failed import never leaves a partial Assessment/Finding/
FindingInstance/Asset behind. An unexpected database error surfaces to the
API caller as a generic `500` with no exception detail or assessment
content — never a raw traceback.

## Import summary contract

`POST /imports/pentera` accepts a `.json` or `.csv` file (dispatched by
extension) and returns, identically for either format:

```json
{
  "assessment_id": 3,
  "rows_processed": 52,
  "rows_imported": 50,
  "rows_skipped": 2,
  "warnings": [
    "Row 14: missing finding title, skipped",
    "Row 37: unrecognized asset type 'container', defaulted to 'unknown'",
    "Findings collection identified at: findings (52 item(s))."
  ],
  "unknown_mappings": 4,
  "new_findings": 12,
  "recurring_findings": 38,
  "resolved_findings": 6,
  "duplicate_observations_coalesced": 2
}
```

`unknown_mappings` is the count of findings imported with
`normalized_type = UNKNOWN` — i.e. the classifier didn't recognize the
finding title/type, but it was imported anyway (never discarded solely for
being unfamiliar), with the original title preserved.

`duplicate_observations_coalesced` is the count of source records that
resolved to a logical Finding already seen earlier in this same import —
see "Intra-assessment duplicates" above. `rows_imported` still counts every
source record processed (including duplicates); the duplicate count is how
many of those `rows_imported` did not get their own FindingInstance.
