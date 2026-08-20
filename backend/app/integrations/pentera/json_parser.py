"""Defensive Pentera JSON parser.

STATUS: Pentera JSON support is structurally defensive but requires
validation against a real sanitized Pentera export. This parser has never
been run against an actual Pentera JSON export in this project — see
docs/PENTERA_IMPORT.md for the full disclaimer and what to send us to
validate/adjust it.

Because the real structure is unknown, this parser is written defensively
rather than against a fixed schema:
  - Accepts a bare top-level array of finding objects, OR an object with a
    findings array nested under a common key name ("findings", "results",
    "vulnerabilities", etc.), OR (as a last resort) the largest array of
    dict-shaped objects found anywhere in the structure.
  - Handles a nested "asset"/"target"/"host" sub-object for asset fields,
    since structured exports commonly represent the affected asset as its
    own object rather than flat columns.
  - Never hard-fails on an individual finding it doesn't fully understand —
    only raises (ParseError) when the file can't be parsed as JSON at all,
    or no plausible finding collection can be found anywhere in it.
  - Preserves the complete original object for every finding (redacted, see
    services/redaction.py) so nothing is ever silently discarded, and warns
    when structure had to be guessed or when sibling data wasn't consumed.

Produces the exact same RawPenteraRow objects parser.py (CSV) produces, so
mapper.py's map_rows() — and everything downstream: risk scoring, dedup,
remediation workflow, trend tracking — is fully shared and unmodified
between the CSV and JSON import paths.
"""
import json
import re
from typing import Any

from app.integrations.pentera.parser import ParseError
from app.integrations.pentera.schemas import RawPenteraRow
from app.services.redaction import redact_json

# normalized field -> accepted JSON key aliases. Matched after normalizing
# both the alias and the actual key the same way (lowercase, strip
# non-alphanumeric) so "Finding Name", "finding_name", "findingName" all
# match identically — same philosophy as parser.py's CSV header aliasing.
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
# when a field isn't found at the finding object's own top level.
ASSET_CONTAINER_KEYS = {"asset", "target", "host", "object", "entity", "affected asset", "affectedasset"}

# Top-level object keys commonly used to hold a findings/results array.
# Preferred over an unnamed largest-array guess when present.
KNOWN_COLLECTION_KEYS = {
    "findings", "results", "vulnerabilities", "issues", "items", "records",
    "data", "assessment_results", "assessmentresults", "modules", "checks",
    "detections", "risks",
}

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


def _select_findings_array(data: Any) -> tuple[str, list[dict], list[str]]:
    """Returns (path_used, findings_list, warnings). Raises ParseError only
    when nothing remotely plausible can be found."""
    warnings: list[str] = []

    if isinstance(data, list):
        if not data:
            raise ParseError("JSON top-level array is empty — no findings found.")
        if not all(isinstance(el, dict) for el in data):
            raise ParseError(
                "JSON top-level array does not contain finding objects "
                f"(found element types: {sorted({type(el).__name__ for el in data})})."
            )
        return "$ (top-level array)", data, warnings

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

    named = [c for c in candidates if _normalize_key(c[0].split(".")[-1]) in {_normalize_key(k) for k in KNOWN_COLLECTION_KEYS}]
    if named:
        chosen = max(named, key=lambda c: len(c[1]))
    else:
        chosen = max(candidates, key=lambda c: len(c[1]))
        warnings.append(
            f"No standard findings key (e.g. 'findings', 'results', 'vulnerabilities') "
            f"was found; used the largest array of objects found at '{chosen[0]}' "
            f"({len(chosen[1])} items) as the findings collection. Review this import "
            "carefully and tell us the real key name if this guessed wrong."
        )

    # Never silently drop other substantial sibling collections — warn so a
    # human can check whether they matter (e.g. a separate "assets" or
    # "modules" array that legitimately isn't findings, vs. one that is).
    threshold = max(3, len(chosen[1]) // 10)
    for path, arr in candidates:
        if path != chosen[0] and len(arr) >= threshold:
            warnings.append(
                f"Also found {len(arr)} object(s) at '{path}' that were NOT treated "
                "as findings and were not imported — review if this is expected."
            )

    return chosen[0], chosen[1], warnings


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


def _map_finding_object(obj: dict, row_number: int) -> tuple[RawPenteraRow, list[str]]:
    warnings: list[str] = []
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

    def _bare_fallback(normalized: dict[str, tuple[str, Any]], bare_key: str) -> str | None:
        """Inside an asset-container sub-object, a bare "name"/"type" key is
        a very common shape (e.g. `asset.name`, `asset.type`) that wouldn't
        otherwise match the full-phrase aliases ("asset name", "object
        type") meant for flat top-level columns."""
        nk = _normalize_key(bare_key)
        if nk in normalized and not isinstance(normalized[nk][1], (dict, list)):
            value = normalized[nk][1]
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

    row = RawPenteraRow(
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
    return row, warnings


def parse_json(content: bytes) -> tuple[list[RawPenteraRow], list[str]]:
    """Parse raw JSON bytes into RawPenteraRow objects.

    Mirrors parser.parse_csv's contract exactly: returns (rows, warnings),
    raises ParseError only when the file can't be parsed as JSON at all, or
    no plausible finding collection exists anywhere in it. Never raises for
    an individual finding it doesn't fully understand — that becomes a
    warning + best-effort partial mapping instead (handled by mapper.py,
    unchanged, same as the CSV path).
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

    path_used, finding_objects, selection_warnings = _select_findings_array(data)
    warnings.extend(selection_warnings)
    warnings.append(f"Findings collection identified at: {path_used} ({len(finding_objects)} item(s)).")

    rows: list[RawPenteraRow] = []
    for i, obj in enumerate(finding_objects, start=1):
        if not isinstance(obj, dict):
            warnings.append(f"Finding {i}: not a JSON object (got {type(obj).__name__}), skipped.")
            continue
        row, row_warnings = _map_finding_object(obj, i)
        warnings.extend(row_warnings)
        rows.append(row)

    return rows, warnings
