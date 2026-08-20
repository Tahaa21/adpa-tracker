"""Typed shapes for Pentera raw and normalized findings.

These are internal to the pentera adapter — the rest of the application only
ever sees the internal Finding/FindingInstance models built from
NormalizedFinding by services/import_service.py.
"""
from pydantic import BaseModel, Field


class RawPenteraRow(BaseModel):
    """A single parsed CSV row, aliases already resolved where possible."""

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
    unmapped_fields: dict[str, str] = Field(default_factory=dict)
    raw: dict[str, str] = Field(default_factory=dict)


class NormalizedFinding(BaseModel):
    """Output of the mapper: ready to be persisted as Finding/FindingInstance."""

    row_number: int
    normalized_type: str
    category: str
    title: str
    source_title: str
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
