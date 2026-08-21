from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source: str
    assessment_date: date
    imported_at: datetime
    environment: str | None = None
    source_filename: str | None = None
    notes: str | None = None
    risk_score: float | None = None
    rows_processed: int
    rows_imported: int
    rows_skipped: int
    import_warnings: list[str] = []


class ImportSummaryOut(BaseModel):
    assessment_id: int
    rows_processed: int
    rows_imported: int
    rows_skipped: int
    warnings: list[str]
    unknown_mappings: int = 0
    new_findings: int
    recurring_findings: int
    resolved_findings: int
    duplicate_observations_coalesced: int = 0


class PriorityDistribution(BaseModel):
    P1: int = 0
    P2: int = 0
    P3: int = 0


class AssessmentDetailOut(BaseModel):
    assessment: AssessmentOut
    priority_distribution: PriorityDistribution
    findings_observed: int
    previous_assessment_id: int | None = None
    previous_risk_score: float | None = None
    risk_reduction_pct: float | None = None
    new_findings: int = 0
    recurring_findings: int = 0
    resolved_findings: int = 0
