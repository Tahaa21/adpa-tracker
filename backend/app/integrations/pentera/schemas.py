"""Typed shapes for Pentera raw and normalized findings.

These are internal to the pentera adapter — the rest of the application only
ever sees the internal Finding/FindingInstance models built from
NormalizedFinding by services/import_service.py.
"""
from typing import Any

from pydantic import BaseModel, Field


class RawPenteraRow(BaseModel):
    """A single parsed finding, aliases already resolved where possible.

    Produced by either parser.py (CSV) or json_parser.py (JSON) — both
    produce this exact same shape so mapper.py's map_rows() is shared,
    unmodified, between formats. `unmapped_fields`/`raw` are `dict[str, Any]`
    (not `dict[str, str]`) specifically so the JSON parser can preserve
    nested objects/arrays verbatim rather than flattening them to strings;
    the CSV parser's plain string values are equally valid under this wider
    type, so this is backward compatible.
    """

    row_number: int
    title: str | None = None
    severity: str | None = None
    asset_name: str | None = None
    asset_type: str | None = None
    domain: str | None = None
    description: str | None = None
    recommendation: str | None = None
    category: str | None = None
    identifier: str | None = None
    exploitable: str | None = None
    unmapped_fields: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class NormalizedFinding(BaseModel):
    """Output of the mapper: ready to be persisted as Finding/FindingInstance."""

    row_number: int
    normalized_type: str
    category: str
    title: str
    source_title: str
    # Canonicalized (lowercased, hyphen/underscore-normalized,
    # whitespace-collapsed) form of source_title -- used as the
    # fingerprinting discriminator so distinct Pentera finding/Achievement
    # names never collide just because normalized_type/domain/asset happen
    # to match (see services/fingerprint.py and mapper.py's
    # _canonicalize_title()). Always non-empty when title is non-empty.
    canonical_title: str
    severity: str
    description: str | None = None
    remediation_guidance: str | None = None

    asset_name: str
    asset_type: str
    asset_external_identifier: str
    domain: str

    exploitable: bool = False
    privileged: bool = False
    tier_zero: bool = False
    credential_exposure: bool = False

    source_metadata: dict = Field(default_factory=dict)
    raw_row: dict = Field(default_factory=dict)


class ParseResult(BaseModel):
    rows_processed: int = 0
    findings: list[NormalizedFinding] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rows_skipped: int = 0
