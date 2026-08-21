# Pentera Import

This is the most important feature of the MVP. It must tolerate real-world
variance in Pentera exports without crashing, and it must recognize the same
logical issue across repeated monthly assessments.

**JSON is the preferred Pentera format** (matches what Pentera actually
exports in practice for this deployment). **CSV remains fully supported.**
**PDF is not yet supported** — do not upload a PDF; the upload control only
accepts `.json`/`.csv`.

> ⚠️ **Pentera JSON compatibility has now been informed by a sanitized
> sample of the actual Pentera ADPA export structure, but has NOT been
> validated comprehensively against every Pentera version/schema.** A real
> local import surfaced the true top-level shape — two large collections,
> `achievements` and `vulnerabilities` — and one sanitized real
> `achievements` object (values replaced by placeholders) was used to build
> achievement-specific field mapping (see "Architecture: achievements vs.
> vulnerabilities" below). The rest of the structure (exact `vulnerabilities`
> object shape, any other top-level collections, alternate Pentera export
> modes/versions) remains unconfirmed and defensively guessed, same as
> before. Every import's warnings say exactly what was guessed — always
> visible, never silent.

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

## Architecture: achievements vs. vulnerabilities

A real Pentera ADPA JSON export contains (at least) two large top-level
collections, confirmed via a real local import and one sanitized sample
`achievements` object:

- **`achievements`** — Pentera's own remediation/finding conditions (e.g.
  *"Password(s) stored in reversible encryption"*). This is what an
  operations team actually wants to track and fix, and is **the primary
  remediation-finding source whenever present** in a Pentera JSON export.
- **`vulnerabilities`** — a much larger collection of individual low-level
  observations. In the real import that prompted this design, ~15k
  `vulnerabilities` objects existed alongside ~16k `achievements` objects.
  Importing `vulnerabilities` one-object-per-Finding was the actual bug
  this design fixes: it buried ~23 real logical issues under thousands of
  near-duplicate rows, most unrecognized and mapped to `UNKNOWN`.
  `vulnerabilities` is **not imported as individual Findings** in this
  MVP — it's recognized and its count reported (`vulnerabilities_discovered`
  in the import summary), but not persisted as Finding rows. If Pentera
  documentation/evidence later shows a different collection relationship,
  or a real export has `vulnerabilities` but no `achievements` at all
  (see below), this can be revisited.

**Selection is by explicit known-collection identity, never by array
size.** `json_parser.py`'s `_select_findings_array()` looks for an
`achievements` collection anywhere in the structure first — if found, it
is chosen as the findings source unconditionally, even if a sibling
`vulnerabilities` (or anything else) is far larger. Only when no
`achievements` collection exists at all does the parser fall back to its
pre-existing named-collection logic (which does include `vulnerabilities`
as a recognized key — a **vulnerabilities-only** export, with no
`achievements` collection present, still imports via the generic path
exactly as before this change) or, as a last resort, the largest
array-of-objects anywhere (with a warning).

**Achievement field mapping.** A dedicated `_map_achievement_object()`
function (not the generic alias-based `_map_finding_object()`) maps the
confirmed real shape:

| achievement field | maps to | notes |
|---|---|---|
| `name` | `title` | finding title/type, fed into the same `TYPE_RULES` classifier as CSV/generic-JSON titles |
| `severity` (numeric, e.g. `8.3`) | `severity` | see "Numeric severity mapping" below — passed through as a string, bucketed by `mapper.py` |
| `parameters.Domain` | `domain` | affected domain |
| `parameters.<Account\|User\|Computer\|...>` | `asset_name`/`asset_type` | best-effort scope detection beyond `Domain` alone (see `ACHIEVEMENT_SCOPE_PARAMETER_KEYS` in `json_parser.py`); falls back to a domain-level finding (`asset_name = domain`, `asset_type = "domain"`) when no specific scope parameter is found — same convention CSV already uses for domain-scoped findings like Password Policy Weakness |
| `summary` | `description` | list-of-strings (or list-of-small-dicts) handled defensively; redacted the same as any free text |
| `parameters` (whole object) | `source_metadata.parameters` | preserved, recursively redacted — affected scope/context, never discarded |
| `id` | `source_metadata.pentera_id` | Pentera's own per-observation identifier — **metadata only** |
| `creation_time` | `source_metadata.pentera_creation_time` | observation timestamp — metadata only |

`id` is deliberately **never** used as the fingerprinting/asset identifier.
The generic JSON path's `FIELD_ALIASES["identifier"]` list includes a bare
`"id"` (correct for a nested asset sub-object's own id, e.g. `asset.id`),
but an achievement's top-level `id` is Pentera's per-observation UUID —
treating it as an asset identifier would give every achievement object a
distinct fingerprint and defeat deduplication entirely. This is why
achievements get their own dedicated mapping function instead of reusing
the generic one.

### Numeric severity mapping

An achievement's `severity` is a plain number (e.g. `8.3`), not a
low/medium/high/critical label. `mapper.py` buckets it deterministically:

| numeric severity | bucket |
|---|---|
| ≥ 9.0 | `critical` |
| 7.0 – 8.9 | `high` |
| 4.0 – 6.9 | `medium` |
| < 4.0 | `low` |

**This is not a claim that Pentera's numeric scale is CVSS.** We have no
Pentera documentation or code evidence confirming that. These thresholds
simply reuse the same numeric band boundaries CVSS v3.x happens to use,
because absent better information they're a well-known, reasonable default
for a 0–10 scale. If real Pentera documentation establishes a different
scale, only `NUMERIC_SEVERITY_THRESHOLDS` in `mapper.py` needs to change.
The original numeric value is never discarded — it's preserved separately
in `source_metadata.pentera_numeric_severity` on every finding, alongside
the bucketed value used everywhere else in the app. It's also surfaced as
its own field in the API (`Finding.pentera_numeric_severity`,
`FindingListItem`/`FindingDetail`) and shown in the UI next to — not
instead of — the tracker's own `risk_score`, so the source score and the
tracker's prioritization stay visibly distinct (Findings table: a small
"Pentera: 7.4" line under the severity badge; Finding detail: separate
"Pentera Severity (source)" and "Tracker Risk Score" fields).

### Deduplication and occurrence counts

Achievement objects are **not** assumed to be independent tickets.
Fingerprinting (see "Fingerprinting / deduplication" and "Achievement
identity" below) applies identically to achievement-derived findings:
`(normalized_type, canonical_title, domain, asset_external_identifier)` —
note this now includes the canonicalized title, not just normalized_type;
see "Achievement identity" for why that matters. Multiple achievement
observations that normalize to the same fingerprint **within one import**
coalesce into a single `FindingInstance` — exactly the existing
"Intra-assessment duplicates" behavior — but now that instance also
carries an `occurrence_count` (new `FindingInstance.occurrence_count`
column, default `1`) recording exactly how many source records coalesced
into it, so the repetition is visible rather than silently collapsed to "1
of something." `ImportSummary.duplicate_observations_coalesced` still
reports the aggregate count across the whole import, same as before.
`occurrence_count` is surfaced in the API/UI too: `FindingListItem`/
`FindingDetail.occurrence_count` reflects the *latest* assessment's count
(a "×239" badge next to the finding title/in Assessment History), while
each individual `FindingInstanceOut.occurrence_count` in Assessment History
preserves every prior assessment's own count.

### Future: associating an achievement with its evidence

Nothing in this MVP links an `achievements` Finding to the specific
`vulnerabilities` observations that produced it — building that
relationship (without a graph database) is deliberately out of scope for
now. The architecture doesn't preclude it later: `vulnerabilities` objects
are already structurally parseable (same `RawPenteraRow`/mapper pipeline
as everything else, see `_map_finding_object()`), so a future pass could,
for example, persist a subset of `vulnerabilities` linked by a shared
`parameters.Domain`/scope to an achievement, or by a Pentera-side
relationship field if one is confirmed to exist. Not built now because
it isn't trivial and wasn't required for the MVP's core loop (prioritize →
assign → remediate → validate).

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
under a common key; or something else entirely. The parser tries, in
order:
1. Top-level array → treated as the findings directly.
2. An `achievements` collection, anywhere in the structure → **always**
   chosen as the findings source when present, regardless of the size of
   any sibling collection (including a larger `vulnerabilities`). See
   "Architecture: achievements vs. vulnerabilities" above — this is the
   one case that is no longer a size-based heuristic.
3. Otherwise, an object with one of the other known key names (`findings`,
   `results`, `vulnerabilities`, `issues`, `items`, `records`, `data`,
   `modules`, `checks`, `detections`, `risks`), at any nesting depth,
   holding an array of objects → the **largest** among those named
   candidates is used (unchanged pre-existing behavior; this is what
   makes a vulnerabilities-only export, with no `achievements` collection
   at all, still work).
4. If none of the above matches: the **largest** array-of-objects found
   anywhere in the structure is used as a last resort, **with a warning**
   telling you exactly which key path was chosen and how many items it
   had — so this guess is always visible, never silent.
5. If nothing even remotely plausible exists anywhere in the structure →
   the whole import is rejected (`ParseError`), same as CSV's "no
   recognizable title/asset column" case.

When `achievements` is chosen and a `vulnerabilities` collection also
exists, its object count is reported as `vulnerabilities_discovered` in
the import summary and named in a warning — never silently dropped, and
never imported as individual Findings (see "Architecture" above).

**Never silently drops a section.** If another substantial array-of-objects
exists in the JSON alongside the one chosen as findings (e.g. a separate
`assets` or `modules` collection), a warning names it and its size so you
can check whether it should have been included instead/also.

**Field aliasing.** Same alias-table philosophy as CSV (see above), adapted
for JSON key naming — `"Finding Name"`, `finding_name`, and `findingName`
all normalize identically. See `FIELD_ALIASES` in `json_parser.py` for the
exact list. This alias-based path is used for the generic/vulnerabilities
case; `achievements` objects use the dedicated explicit mapping described
in "Architecture: achievements vs. vulnerabilities" above instead, because
the generic alias table is a poor (and in one case actively wrong — see
the `id` field note above) fit for the confirmed achievement shape.

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
finding/achievement objects with real values replaced by placeholders, and
(c) any field-naming differences from the alias table or the achievement
field mapping above. That's a targeted, low-risk change to
`FIELD_ALIASES`/`KNOWN_COLLECTION_KEYS`/`ASSET_CONTAINER_KEYS`/
`ACHIEVEMENT_SCOPE_PARAMETER_KEYS` in `json_parser.py` — not a redesign.

## Warning aggregation

A real Pentera export can have thousands of rows sharing the same
structural cause (e.g. an unrecognized finding name repeated across many
accounts, or the same unrecognized asset type). Emitting one warning per
row would flood the import summary — a real import that produced ~11,600
near-identical warnings from ~15,000 rows is what prompted this. Both
`mapper.py` and the achievement path aggregate per-row warnings into one
summary line per **distinct cause**, using a count, e.g.:

```
Using empty password(s): 1,284 observation(s) imported as UNKNOWN.
2 row(s) had unrecognized asset type 'container', defaulted to 'unknown'.
```

rather than 1,284 (or 2) separate lines. This applies to: unrecognized
finding type/title (grouped by title), unrecognized asset type (grouped by
the raw value), missing title/missing asset/missing-both (grouped by
cause, already a single count each). The original title and a stable
`"imported as UNKNOWN"` marker are always present in the aggregated line,
so nothing about *what* was unrecognized is lost — only the per-row
repetition is collapsed.

## Normalization mapping (`mapper.py`)

`normalized_type` is chosen by matching a **canonicalized** title (see
`_canonicalize_title()`: lowercased, `-`/`_` collapsed to spaces, whitespace
collapsed — so `"Password-Not-Required"` and `"password_not_required"` match
the same keyword phrases as `"Password Not Required"`) against a keyword
table, first match wins, e.g.:

| canonicalized title contains | normalized_type | category |
|---|---|---|
| "password" + "not required" | `PASSWORD_NOT_REQUIRED` | `ACCOUNT_HYGIENE` |
| "password" + "never expire" | `PASSWORD_NEVER_EXPIRES` | `ACCOUNT_HYGIENE` |
| "reversible encryption" | `REVERSIBLE_ENCRYPTION` | `CREDENTIAL_EXPOSURE` |
| "empty password" | `EMPTY_PASSWORD` | `CREDENTIAL_EXPOSURE` |
| "domain admin" | `DOMAIN_ADMIN_MEMBERSHIP` | `TIER_0` |
| "security account manager" / "samr" | `SAMR_EXPOSURE` | `PRIVILEGE` |
| "privileged group" / "admin group" | `PRIVILEGED_GROUP_MEMBERSHIP` | `PRIVILEGE` |
| "dcsync" / "dc sync" | `DCSYNC_EXPOSURE` | `TIER_0` |
| "password reuse" / "reused password" / "identical" + "password" | `PASSWORD_REUSE` | `CREDENTIAL_EXPOSURE` |
| "leaked credential" / "breached password" / "leaked cleartext password" / "leaked username" | `LEAKED_CREDENTIAL` | `CREDENTIAL_EXPOSURE` |
| "weak password" / "cracked password" / "password can be cracked" / "crackable password" | `WEAK_PASSWORD` | `CREDENTIAL_EXPOSURE` |
| "password policy" | `PASSWORD_POLICY_WEAKNESS` | `POLICY_CONFIGURATION` |
| "password" + "complexity" | `PASSWORD_COMPLEXITY_WEAKNESS` | `ACCOUNT_HYGIENE` |
| "password" + "age" | `PASSWORD_AGE_WEAKNESS` | `POLICY_CONFIGURATION` |
| "dormant" + "privileged" | `DORMANT_PRIVILEGED_ACCOUNT` | `PRIVILEGE` |
| "delegation" | `DELEGATION_RISK` | `DELEGATION` |
| "acl" / "dacl" + "abuse" | `ACL_ABUSE` | `PRIVILEGE` |
| "service account" | `SERVICE_ACCOUNT_RISK` | `PRIVILEGE` |
| "trust" | `TRUST_RISK` | `TRUST` |
| *(no match)* | `UNKNOWN` | `OTHER` |

This table lives as data in `mapper.py` (`TYPE_RULES`) — extending it is a
one-line addition, not a structural change. `asset_type` is normalized
similarly from the source's asset-type column, defaulting to `unknown`.

**A shared normalized_type is a classification, not an identity merge.**
Several distinct Pentera Achievement names deliberately share one
normalized_type/category above (e.g. "Password can be cracked using low GPU
effort" and "...using high GPU effort" are both `WEAK_PASSWORD`) — they
still become separate Findings. See "Achievement identity" below for why
that's safe and how it's enforced.

Severity is normalized to `low|medium|high|critical` via a small alias map
(`critical/severe→critical`, `high→high`, `medium/moderate→medium`,
`low/informational→low`, default `medium`) for text severities, and via
`NUMERIC_SEVERITY_THRESHOLDS` (see "Numeric severity mapping" above) for
numeric ones.

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
- `discriminator` is `NormalizedFinding.canonical_title` — a canonicalized
  form of the finding's own source title/name (see `_canonicalize_title()`
  above). **This changed from an earlier version of this doc/design that
  defaulted the discriminator to `normalized_type` again** — see
  "Achievement identity" immediately below for why that was wrong and what
  broke because of it.

### Achievement identity: why the title is part of the fingerprint

A second real Pentera ADPA import (16k+ `achievements` objects spanning many
distinct Achievement types) surfaced that the tracker had collapsed
everything down to **7 logical Findings**, most attached to a generic
`Unknown Asset`. Root cause: the fingerprint discriminator defaulted to
`normalized_type`, so identity was effectively just
`(normalized_type, domain, asset)`. Two things made that collapse
catastrophic in practice:

1. **Most real Achievement names don't match any `TYPE_RULES` keyword
   pattern** — they land on `normalized_type = UNKNOWN` (by design; see
   "Mapping behavior" below — that's correct and intentional). But
   `UNKNOWN` is itself just one value. Every unrecognized Achievement name,
   regardless of what it actually says, produced the same `normalized_type`
   component.
2. **Most achievements have no specific affected-object parameter** — only
   `parameters.Domain`, no `Account`/`User`/`Computer`/etc. — so `asset_name`
   fell back to the domain itself (a deliberate, documented choice; see
   "Affected Asset" mapping above). Every such achievement, again regardless
   of its actual name, produced the same `asset` component too.

Combined: `UNKNOWN | domain | domain | UNKNOWN` was the fingerprint for
*any* unrecognized, domain-scoped Achievement — "Using empty password(s)",
"Password age permitted is too long", "Security Account Manager Remote
Protocol exposure", all of them, one fingerprint. Every subsequent
achievement of that shape was treated as an intra-assessment duplicate of
the first one seen and silently coalesced away.

**Fix:** the fingerprint discriminator is now `canonical_title` — a
canonicalized (lowercased, hyphen/underscore-normalized, whitespace-
collapsed) copy of the finding's own source title/name — instead of
`normalized_type`. This applies uniformly, not just to `UNKNOWN` findings:
even two *classified* Achievement names that share a normalized_type (e.g.
two different `WEAK_PASSWORD` cracking-effort variants) stay separately
identified, because the category was never meant to be identity — see
"Normalization mapping" above. Since `title` is always non-empty for any
row that survives mapping (rows missing both title and asset are skipped
before this point), `canonical_title` is always a meaningful discriminator.

**Known tradeoff, stated explicitly:** identity now depends on the
Achievement name staying textually stable between assessment runs. If a
future Pentera version rephrases an Achievement's `name` for the exact same
underlying condition, it will import as a **new** Finding rather than a
recurrence of the old one, until `TYPE_RULES`/fingerprinting is revisited
with evidence of that happening. This is a deliberate, documented tradeoff
in exchange for fixing the far worse collapse-to-7 bug — see
docs/PENTERA_IMPORT.md history / CLAUDE.md checkpoint log for the incident
this fixed.

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
not repeats within one file. The coalesced-into `FindingInstance` itself
carries an `occurrence_count` (default `1`) recording exactly how many
source records — the first plus every coalesced duplicate — resolved to
it, so the repetition is visible on the record itself, not just in the
aggregate summary count.

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
  "rows_processed": 15982,
  "rows_imported": 15982,
  "rows_skipped": 0,
  "warnings": [
    "Vulnerabilities collection found (15259 items) — not imported as individual findings in this MVP; 'achievements' is used as the primary remediation-finding source instead. See docs/PENTERA_IMPORT.md 'Architecture: achievements vs. vulnerabilities'.",
    "Achievements collection identified at: achievements (15982 item(s)).",
    "Using empty password(s): 1284 observation(s) imported as UNKNOWN.",
    "312 source record(s) were duplicate observations of an already-imported finding within this same assessment and were coalesced into a single record (not counted as new or recurring)."
  ],
  "unknown_mappings": 1284,
  "new_findings": 41,
  "recurring_findings": 38,
  "resolved_findings": 6,
  "duplicate_observations_coalesced": 312,
  "achievements_discovered": 15982,
  "vulnerabilities_discovered": 15259,
  "remediation_findings_created": 79
}
```

`unknown_mappings` is the count of findings imported with
`normalized_type = UNKNOWN` — i.e. the classifier didn't recognize the
finding title/type, but it was imported anyway (never discarded solely for
being unfamiliar), with the original title and severity preserved.

`duplicate_observations_coalesced` is the count of source records that
resolved to a logical Finding already seen earlier in this same import —
see "Intra-assessment duplicates" above. `rows_imported` still counts every
source record processed (including duplicates); the duplicate count is how
many of those `rows_imported` did not get their own FindingInstance (they
instead incremented that FindingInstance's `occurrence_count`).

`achievements_discovered`/`vulnerabilities_discovered` are JSON-only (0 for
a CSV import, or a JSON export that didn't contain that collection) —
object counts found in that collection, regardless of whether it was
imported as Findings. See "Architecture: achievements vs. vulnerabilities"
above.

`remediation_findings_created` is the number of distinct logical Findings
(new + recurring) this import actually created or touched — the real
number of remediation items a user needs to act on for this assessment,
after intra-assessment duplicate coalescing. This is the number to look at
instead of `rows_imported` when the source format (like `achievements`)
can report the same logical condition many times.
