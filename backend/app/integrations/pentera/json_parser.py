"""Defensive Pentera JSON parser.

STATUS: JSON compatibility has now been informed by a sanitized sample of
an actual Pentera ADPA export's structure (a real `achievements` object,
with values replaced by placeholders — see docs/PENTERA_IMPORT.md and the
commit that added achievement-specific handling), but has NOT been
comprehensively validated against every Pentera version/schema. Treat this
as informed-but-partial, not authoritative for every possible export.

## Two known Pentera collections, two different roles

A real Pentera ADPA JSON export was found to contain (at least) two large
top-level collections:

- `achievements` — Pentera's own remediation/finding conditions (e.g.
  "Password(s) stored in reversible encryption"). This is what an
  operations team actually wants to track and fix. **Treated as the
  primary remediation-finding source when present.**
- `vulnerabilities` — a much larger, lower-level collection of individual
  observations (in the sample that prompted this: ~15k objects mapping to
  only ~23 distinct logical issues when naively imported one-row-per-
  observation). Recognized and counted, but NOT imported as individual
  Findings in this MVP — importing every vulnerability row as its own
  Finding was exactly the bug this parser used to have (thousands of
  near-duplicate rows burying the real remediation items). See
  "Architecture: achievements vs. vulnerabilities" in
  docs/PENTERA_IMPORT.md for why, and for the (not yet built) plan to
  later associate an achievement with its underlying vulnerability
  evidence.

An explicit KNOWN collection ("achievements" first, then the other named
keys) always takes precedence over heuristic largest-array selection —
this parser no longer picks whichever array happens to be biggest.

## General defensive parsing strategy (unchanged)

Because the real structure is only partially confirmed, this parser
remains defensive rather than schema-locked:
  - Accepts a bare top-level array of finding objects, OR an object with a
    findings array nested under a common key name, OR (as a last resort,
    only when no known key matches) the largest array of dict-shaped
    objects found anywhere in the structure.
  - Handles a nested "asset"/"target"/"host" sub-object for asset fields
    (generic path) or Pentera's `parameters` object (achievement path).
  - Never hard-fails on an individual finding it doesn't fully understand —
    only raises (ParseError) when the file can't be parsed as JSON at all,
    or no plausible finding collection can be found anywhere in it.
  - Preserves the complete original object for every finding (redacted, see
    services/redaction.py) so nothing is ever silently discarded, and warns
    when structure had to be guessed or when sibling data wasn't consumed.

Both the achievement path and the generic path produce the exact same
RawPenteraRow objects parser.py (CSV) produces, so mapper.py's
map_rows() — and everything downstream: severity bucketing, risk scoring,
dedup, remediation workflow, trend tracking — is fully shared and
unmodified between the CSV path, the generic JSON path, and the
achievement JSON path.
"""
import json
import re
from typing import Any

from app.integrations.pentera.parser import ParseError
from app.integrations.pentera.schemas import RawPenteraRow
from app.services.redaction import redact_inline_credentials, redact_json

# normalized field -> accepted JSON key aliases. Matched after normalizing
# both the alias and the actual key the same way (lowercase, strip
# non-alphanumeric) so "Finding Name", "finding_name", "findingName" all
# match identically — same philosophy as parser.py's CSV header aliasing.
# Used for the GENERIC (non-achievement) path only.
FIELD_ALIASES: dict[str, list[str]] = {
    "title": [
        "finding", "finding name", "findingtype", "finding_type", "vulnerability",
        "vulnerability name", "title", "issue", "issue name", "name", "check name",
        "checkname",
    ],
    "severity": ["severity", "risk severity", "risk", "risk level", "criticality"],
    "asset_name": [
        "asset", "target", "host", "hostname", "affected asset", "object name",
        "entity", "asset name",
    ],
    "asset_type": ["asset type", "object type", "entity type"],
    "domain": ["domain", "environment", "realm"],
    "description": ["description", "details", "summary", "desc"],
    "recommendation": ["recommendation", "remediation", "mitigation", "guidance", "fix"],
    "category": ["category", "attack category", "module", "class"],
    "identifier": [
        "object sid", "sid", "sam account name", "samaccountname", "identifier",
        "dn", "distinguished name", "id",
    ],
    "exploitable": ["exploitable", "confirmed", "verified", "exploited"],
}

# Sub-object keys that plausibly represent "the affected asset", checked
# when a field isn't found at the finding object's own top level. Generic
# path only.
ASSET_CONTAINER_KEYS = {"asset", "target", "host", "object", "entity", "affected asset", "affectedasset"}

# Collection key(s) known to be Pentera's own primary remediation-finding
# source, checked FIRST and preferred over every other named collection or
# size-based heuristic when present anywhere in the structure.
ACHIEVEMENTS_COLLECTION_KEY = "achievements"

# Collection key recognized as Pentera's lower-level observation set.
# Never chosen as the primary findings source (even if "achievements" is
# absent, this is intentionally NOT auto-promoted -- see
# docs/PENTERA_IMPORT.md); its count is still reported, and if
# "achievements" is absent it DOES fall through to the generic
# named-collection logic below like any other recognized key, preserving
# the pre-existing "vulnerabilities-only export" behavior.
VULNERABILITIES_COLLECTION_KEY = "vulnerabilities"

# Other top-level object keys commonly used to hold a findings/results
# array in a non-Pentera-shaped or older-format JSON export. Preferred
# over an unnamed largest-array guess when present. Deliberately does NOT
# include "achievements" (handled with unconditional priority above) —
# "vulnerabilities" stays here so a vulnerabilities-only export (no
# achievements collection at all) still works exactly as before.
KNOWN_COLLECTION_KEYS = {
    "findings", "results", "vulnerabilities", "issues", "items", "records",
    "data", "assessment_results", "assessmentresults", "modules", "checks",
    "detections", "risks",
}

# Achievement `parameters` keys that plausibly identify the affected scope
# (asset/account/domain), checked in this order. Real Pentera parameter
# names beyond "Domain" are not confirmed from the one sanitized sample we
# have — this list is a best-effort, defensive guess for common AD-related
# parameter names; anything not matched here still survives in the
# preserved (redacted) `parameters` metadata, nothing is lost.
ACHIEVEMENT_SCOPE_PARAMETER_KEYS: list[tuple[str, str]] = [
    # (normalized parameter key, inferred asset_type)
    ("account", "user"), ("user", "user"), ("username", "user"),
    ("samaccountname", "user"), ("object", "unknown"), ("objectname", "unknown"),
    ("computer", "computer"), ("host", "computer"), ("hostname", "computer"),
    ("target", "unknown"), ("entity", "unknown"), ("group", "group"),
]

TRUTHY = {"true", "yes", "1", "y", "confirmed", "verified"}


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", key.lower().strip())


def _find_object_arrays(obj: Any, path: str = "") -> list[tuple[str, list[dict]]]:
    """Recursively find every (path, list) pair anywhere in `obj` where the
    list is non-empty and every element is a dict — i.e. every plausible
    "array of records" in the structure, at any depth."""
    found: list[tuple[str, list[dict]]] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            sub_path = f"{path}.{key}" if path else str(key)
            if isinstance(value, list) and value and all(isinstance(el, dict) for el in value):
                found.append((sub_path, value))
            elif isinstance(value, dict):
                found.extend(_find_object_arrays(value, sub_path))
    return found


def _collection_key_name(path: str) -> str:
    return _normalize_key(path.split(".")[-1])


def _select_findings_array(data: Any) -> tuple[str, list[dict], bool, int, list[str]]:
    """Returns (path_used, findings_list, is_achievements, vulnerabilities_count, warnings).

    Selection order:
    1. A top-level bare array (unchanged from before -- no "achievements
       vs vulnerabilities" question applies to that shape).
    2. An "achievements" collection, if present anywhere -- ALWAYS chosen
       as primary regardless of its size relative to any sibling
       collection (including a larger "vulnerabilities").
    3. Otherwise, the largest collection among the other known keys
       (unchanged pre-existing behavior -- covers a vulnerabilities-only
       export, or any other recognized shape, with no achievements
       collection at all).
    4. Otherwise, the largest array of objects anywhere, with a warning
       that this was a guess.

    Raises ParseError only when nothing remotely plausible exists.
    """
    warnings: list[str] = []

    if isinstance(data, list):
        if not data:
            raise ParseError("JSON top-level array is empty — no findings found.")
        if not all(isinstance(el, dict) for el in data):
            raise ParseError(
                "JSON top-level array does not contain finding objects "
                f"(found element types: {sorted({type(el).__name__ for el in data})})."
            )
        return "$ (top-level array)", data, False, 0, warnings

    if not isinstance(data, dict):
        raise ParseError(f"Unsupported JSON top-level type: {type(data).__name__}.")

    if not data:
        raise ParseError("JSON object is empty — no findings found.")

    candidates = _find_object_arrays(data)
    if not candidates:
        raise ParseError(
            "Could not find any array of finding-like objects anywhere in the JSON "
            "structure. Expected either a top-level array of findings, or an object "
            "with a nested array (e.g. under a 'findings'/'results' key)."
        )

    achievement_candidates = [
        c for c in candidates if _collection_key_name(c[0]) == _normalize_key(ACHIEVEMENTS_COLLECTION_KEY)
    ]
    if achievement_candidates:
        # Explicit known collection takes precedence over everything else,
        # including a larger sibling collection like vulnerabilities —
        # never chosen by size here.
        chosen = max(achievement_candidates, key=lambda c: len(c[1]))
        is_achievements = True
    else:
        named = [c for c in candidates if _collection_key_name(c[0]) in {_normalize_key(k) for k in KNOWN_COLLECTION_KEYS}]
        if named:
            chosen = max(named, key=lambda c: len(c[1]))
        else:
            chosen = max(candidates, key=lambda c: len(c[1]))
            warnings.append(
                f"No standard findings key (e.g. 'achievements', 'findings', 'results') "
                f"was found; used the largest array of objects found at '{chosen[0]}' "
                f"({len(chosen[1])} items) as the findings collection. Review this import "
                "carefully and tell us the real key name if this guessed wrong."
            )
        is_achievements = False

    # Count a sibling "vulnerabilities" collection only when it was NOT
    # itself the chosen findings source — if vulnerabilities was selected
    # (e.g. no achievements collection present at all), it already IS the
    # findings collection and is reflected via rows_processed/rows_imported;
    # reporting it again here would double-count the same objects.
    vulnerabilities_count = sum(
        len(arr) for path, arr in candidates
        if path != chosen[0] and _collection_key_name(path) == _normalize_key(VULNERABILITIES_COLLECTION_KEY)
    )

    if is_achievements and vulnerabilities_count:
        warnings.append(
            f"Vulnerabilities collection found ({vulnerabilities_count} items) — not "
            "imported as individual findings in this MVP; 'achievements' is used as the "
            "primary remediation-finding source instead. See docs/PENTERA_IMPORT.md "
            "'Architecture: achievements vs. vulnerabilities'."
        )

    # Never silently drop other substantial sibling collections we haven't
    # already explained above — warn so a human can check whether they
    # matter (e.g. a separate "assets" or "modules" array).
    threshold = max(3, len(chosen[1]) // 10)
    for path, arr in candidates:
        if path == chosen[0]:
            continue
        if is_achievements and _collection_key_name(path) == _normalize_key(VULNERABILITIES_COLLECTION_KEY):
            continue  # already explained above, don't also emit the generic warning
        if len(arr) >= threshold:
            warnings.append(
                f"Also found {len(arr)} object(s) at '{path}' that were NOT treated "
                "as findings and were not imported — review if this is expected."
            )

    return chosen[0], chosen[1], is_achievements, vulnerabilities_count, warnings


def _get_top_level(normalized: dict[str, tuple[str, Any]], field: str) -> tuple[str | None, str | None]:
    """Look up `field`'s value among a finding object's own top-level keys.
    Returns (value_as_str, original_key) or (None, None)."""
    for alias in FIELD_ALIASES[field]:
        norm_alias = _normalize_key(alias)
        if norm_alias in normalized:
            orig_key, value = normalized[norm_alias]
            if isinstance(value, (dict, list)):
                continue  # not usable as a scalar for this field
            if isinstance(value, bool):
                return ("true" if value else "false"), orig_key
            if value is None:
                continue
            return str(value), orig_key
    return None, None


def _map_finding_object(obj: dict, row_number: int) -> RawPenteraRow:
    """Generic path: heuristic field-alias mapping. Used for
    vulnerabilities-only exports, or any non-achievement-shaped JSON."""
    normalized: dict[str, tuple[str, Any]] = {}
    for key, value in obj.items():
        if isinstance(key, str):
            normalized[_normalize_key(key)] = (key, value)

    consumed_keys: set[str] = set()

    def get(field: str) -> str | None:
        value, orig_key = _get_top_level(normalized, field)
        if orig_key:
            consumed_keys.add(orig_key)
        return value

    title = get("title")
    severity = get("severity")
    description = get("description")
    recommendation = get("recommendation")
    category = get("category")
    exploitable = get("exploitable")

    # Asset fields: prefer a nested asset-like sub-object if present (common
    # in structured exports), fall back to the finding object's own
    # top-level keys otherwise.
    asset_container_key = None
    asset_obj: dict | None = None
    for key, value in obj.items():
        if isinstance(value, dict) and isinstance(key, str) and _normalize_key(key) in {_normalize_key(k) for k in ASSET_CONTAINER_KEYS}:
            asset_container_key = key
            asset_obj = value
            break

    def _bare_fallback(normalized_map: dict[str, tuple[str, Any]], bare_key: str) -> str | None:
        """Inside an asset-container sub-object, a bare "name"/"type" key is
        a very common shape (e.g. `asset.name`, `asset.type`) that wouldn't
        otherwise match the full-phrase aliases ("asset name", "object
        type") meant for flat top-level columns."""
        nk = _normalize_key(bare_key)
        if nk in normalized_map and not isinstance(normalized_map[nk][1], (dict, list)):
            value = normalized_map[nk][1]
            return ("true" if value else "false") if isinstance(value, bool) else str(value)
        return None

    asset_name = asset_type = domain = identifier = None
    if asset_obj is not None:
        asset_normalized: dict[str, tuple[str, Any]] = {}
        for key, value in asset_obj.items():
            if isinstance(key, str):
                asset_normalized[_normalize_key(key)] = (key, value)
        asset_name, _ = _get_top_level(asset_normalized, "asset_name")
        if asset_name is None:
            asset_name = _bare_fallback(asset_normalized, "name")
        asset_type, _ = _get_top_level(asset_normalized, "asset_type")
        if asset_type is None:
            asset_type = _bare_fallback(asset_normalized, "type")
        domain, _ = _get_top_level(asset_normalized, "domain")
        identifier, _ = _get_top_level(asset_normalized, "identifier")
        consumed_keys.add(asset_container_key)

    if asset_name is None:
        asset_name = get("asset_name")
    if asset_type is None:
        asset_type = get("asset_type")
    if domain is None:
        domain = get("domain")
    if identifier is None:
        identifier = get("identifier")

    unmapped = {k: v for k, v in obj.items() if k not in consumed_keys and v not in (None, "", {}, [])}

    # Redact before persistence — recursively, so a secret nested at any
    # depth inside the full raw object or the unmapped-fields subset is
    # caught. Functional fields extracted above are taken from the
    # ORIGINAL (unredacted) object, same as the CSV path, so parsing/dedup
    # correctness is unaffected by redaction.
    safe_raw = redact_json(obj)
    safe_unmapped = redact_json(unmapped)

    return RawPenteraRow(
        row_number=row_number,
        title=title,
        severity=severity,
        asset_name=asset_name,
        asset_type=asset_type,
        domain=domain,
        description=description,
        recommendation=recommendation,
        category=category,
        identifier=identifier,
        exploitable=exploitable,
        unmapped_fields=safe_unmapped,
        raw=safe_raw,
    )


def _summary_to_description(summary: Any) -> str | None:
    """Achievement `summary` is a list in the one sanitized sample we have
    (empty in that sample). Defensively handle it being a list of strings,
    a list of small dicts, or absent — never assume its exact shape.
    Redacted the same way any other free text is (inline key:value
    credential patterns)."""
    if not summary:
        return None
    parts: list[str] = []
    if isinstance(summary, list):
        for item in summary:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            elif isinstance(item, dict):
                for key in ("text", "message", "value", "description"):
                    if isinstance(item.get(key), str) and item[key].strip():
                        parts.append(item[key].strip())
                        break
    elif isinstance(summary, str):
        parts.append(summary.strip())
    if not parts:
        return None
    return redact_inline_credentials("; ".join(parts))


def _map_achievement_object(obj: dict, row_number: int) -> RawPenteraRow:
    """Pentera-`achievements`-specific path: explicit field mapping (not
    the generic heuristic aliasing) based on the one confirmed sanitized
    sample structure:

        {"id": ..., "creation_time": ..., "name": ...,
         "summary": [...], "severity": <number>, "parameters": {...}}

    Explicit rather than reusing the generic alias-based `get()` is
    deliberate: the generic path's "identifier" alias list includes a bare
    "id", which is correct for a NESTED asset object's own id (e.g.
    `asset.id`) but WRONG here — an achievement's top-level "id" is
    Pentera's own per-observation identifier, not an asset/account
    identifier. Using it as the fingerprinting identifier would give every
    achievement object a distinct fingerprint and defeat deduplication
    entirely. See docs/PENTERA_IMPORT.md "Achievement field mapping".
    """
    pentera_id = obj.get("id")
    title = obj.get("name")
    severity = obj.get("severity")
    creation_time = obj.get("creation_time")
    summary = obj.get("summary")
    parameters = obj.get("parameters")

    severity_str = None
    if isinstance(severity, bool):
        severity_str = "true" if severity else "false"
    elif isinstance(severity, (int, float)):
        severity_str = str(severity)
    elif isinstance(severity, str):
        severity_str = severity

    title_str = title if isinstance(title, str) else None
    description = _summary_to_description(summary)

    domain = None
    asset_name = None
    asset_type = None
    if isinstance(parameters, dict):
        param_normalized = {
            _normalize_key(k): (k, v) for k, v in parameters.items() if isinstance(k, str)
        }
        if "domain" in param_normalized:
            v = param_normalized["domain"][1]
            if isinstance(v, str):
                domain = v
        for norm_key, inferred_type in ACHIEVEMENT_SCOPE_PARAMETER_KEYS:
            if norm_key in param_normalized:
                v = param_normalized[norm_key][1]
                if isinstance(v, str) and v.strip():
                    asset_name = v
                    asset_type = inferred_type
                    break

    # No specific affected-object parameter found: this is a domain-level
    # condition (matches the sanitized sample, which only had "Domain") —
    # same convention already used for domain-scoped CSV findings like
    # "Password Policy Weakness" (asset_name = domain, asset_type =
    # "domain").
    if asset_name is None and domain:
        asset_name = domain
        asset_type = "domain"

    # `parameters` is the affected scope/context — preserved (redacted
    # recursively) rather than discarded, per the explicit requirement.
    # `id`/`creation_time` are Pentera's own observation metadata, kept for
    # audit/traceability but never used as the fingerprinting identifier.
    metadata: dict[str, Any] = {}
    if pentera_id is not None:
        metadata["pentera_id"] = pentera_id
    if creation_time is not None:
        metadata["pentera_creation_time"] = creation_time
    if parameters is not None:
        metadata["parameters"] = redact_json(parameters)

    safe_raw = redact_json(obj)

    return RawPenteraRow(
        row_number=row_number,
        title=title_str,
        severity=severity_str,
        asset_name=asset_name,
        asset_type=asset_type,
        domain=domain,
        description=description,
        recommendation=None,
        category=None,
        identifier=None,  # deliberately NOT obj["id"] -- see docstring
        exploitable=None,
        unmapped_fields=metadata,
        raw=safe_raw,
    )


def parse_json(content: bytes) -> tuple[list[RawPenteraRow], list[str], dict[str, int]]:
    """Parse raw JSON bytes into RawPenteraRow objects.

    Returns (rows, warnings, collection_counts). collection_counts has
    "achievements_discovered" and "vulnerabilities_discovered" (0 if that
    collection wasn't present in this export).

    Raises ParseError only when the file can't be parsed as JSON at all, or
    no plausible finding collection exists anywhere in it. Never raises for
    an individual finding it doesn't fully understand — that becomes a
    best-effort partial mapping instead (handled by mapper.py, unchanged,
    same as the CSV path).
    """
    warnings: list[str] = []

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
            warnings.append("File was not UTF-8; decoded as latin-1.")
        except Exception as exc:  # pragma: no cover - very unlikely
            raise ParseError(f"Could not decode file as text: {exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Could not parse file as JSON: {exc}") from exc

    path_used, finding_objects, is_achievements, vulnerabilities_count, selection_warnings = _select_findings_array(data)
    warnings.extend(selection_warnings)
    collection_label = "achievements" if is_achievements else "findings"
    warnings.append(f"{collection_label.capitalize()} collection identified at: {path_used} ({len(finding_objects)} item(s)).")

    map_fn = _map_achievement_object if is_achievements else _map_finding_object

    rows: list[RawPenteraRow] = []
    for i, obj in enumerate(finding_objects, start=1):
        if not isinstance(obj, dict):
            warnings.append(f"Finding {i}: not a JSON object (got {type(obj).__name__}), skipped.")
            continue
        rows.append(map_fn(obj, i))

    collection_counts = {
        "achievements_discovered": len(finding_objects) if is_achievements else 0,
        "vulnerabilities_discovered": vulnerabilities_count,
    }
    return rows, warnings, collection_counts
