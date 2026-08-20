"""Tolerant Pentera CSV parser.

Reads a CSV export whose exact column headers may vary between Pentera
versions/exports, resolves known header aliases, and produces RawPenteraRow
objects plus a list of human-readable warnings. Never raises on a single bad
row — only raises (ParseError) when the file is unreadable or no recognizable
title/asset column exists at all.
"""
import csv
import io
import re

from app.integrations.pentera.schemas import RawPenteraRow

# normalized field -> accepted header aliases (case/space/punct-insensitive)
FIELD_ALIASES: dict[str, list[str]] = {
    "title": ["finding", "finding name", "vulnerability", "title", "issue", "issue name"],
    "severity": ["severity", "risk severity", "risk level", "criticality"],
    "asset_name": ["asset", "target", "host", "affected asset", "object name", "entity"],
    "asset_type": ["asset type", "object type", "entity type"],
    "domain": ["domain", "environment"],
    "description": ["description", "details", "summary"],
    "recommendation": ["recommendation", "remediation", "mitigation", "guidance"],
    "category": ["category", "attack category", "module"],
    "identifier": [
        "object sid",
        "sid",
        "sam account name",
        "samaccountname",
        "identifier",
        "dn",
        "distinguished name",
    ],
    "exploitable": ["exploitable", "confirmed", "verified"],
}


class ParseError(Exception):
    """Raised when the file cannot be parsed at all (not for per-row issues)."""


def _normalize_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", header.lower().strip())


def _build_header_map(fieldnames: list[str]) -> dict[str, str]:
    """Map normalized_field -> actual CSV header, for whichever aliases matched."""
    normalized_lookup = {_normalize_header(h): h for h in fieldnames}
    header_map: dict[str, str] = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            key = _normalize_header(alias)
            if key in normalized_lookup:
                header_map[field] = normalized_lookup[key]
                break
    return header_map


def parse_csv(content: bytes) -> tuple[list[RawPenteraRow], list[str]]:
    """Parse raw CSV bytes into RawPenteraRow objects.

    Returns (rows, warnings). Raises ParseError if the file has no usable
    title/asset columns at all, or cannot be decoded/parsed as CSV.
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
        reader = csv.DictReader(io.StringIO(text))
        fieldnames = reader.fieldnames
    except csv.Error as exc:
        raise ParseError(f"Could not parse file as CSV: {exc}") from exc

    if not fieldnames:
        raise ParseError("CSV file has no header row / no columns.")

    header_map = _build_header_map(fieldnames)

    if "title" not in header_map and "asset_name" not in header_map:
        raise ParseError(
            "Could not find a recognizable finding title or asset column in "
            f"the CSV headers: {fieldnames}"
        )

    rows: list[RawPenteraRow] = []
    for i, raw in enumerate(reader, start=2):  # row 1 is the header
        # csv.DictReader can leave None keys for ragged rows; drop them.
        raw = {k: v for k, v in raw.items() if k is not None}

        mapped: dict[str, str | None] = {}
        used_headers: set[str] = set()
        for field, header in header_map.items():
            value = raw.get(header)
            mapped[field] = value.strip() if isinstance(value, str) else value
            used_headers.add(header)

        unmapped = {
            k: v for k, v in raw.items() if k not in used_headers and v not in (None, "")
        }

        rows.append(
            RawPenteraRow(
                row_number=i,
                title=mapped.get("title") or None,
                severity=mapped.get("severity") or None,
                asset_name=mapped.get("asset_name") or None,
                asset_type=mapped.get("asset_type") or None,
                domain=mapped.get("domain") or None,
                description=mapped.get("description") or None,
                recommendation=mapped.get("recommendation") or None,
                category=mapped.get("category") or None,
                identifier=mapped.get("identifier") or None,
                exploitable=mapped.get("exploitable") or None,
                unmapped_fields=unmapped,
                raw=raw,
            )
        )

    return rows, warnings
