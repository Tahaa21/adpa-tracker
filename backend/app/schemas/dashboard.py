from pydantic import BaseModel


class TopMetrics(BaseModel):
    total_findings: int = 0
    open_findings: int = 0
    p1_findings: int = 0
    validated_findings: int = 0
    overall_risk_score: float = 0


class RemediationMetrics(BaseModel):
    assigned: int = 0
    in_remediation: int = 0
    ready_for_validation: int = 0
    validated: int = 0


class PriorityDistribution(BaseModel):
    P1: int = 0
    P2: int = 0
    P3: int = 0
    P4: int = 0


class SeverityDistribution(BaseModel):
    """Pentera severity band distribution — kept separate from
    PriorityDistribution so the dashboard can show whether risk is coming
    from Pentera's own severity rating or from the Tracker's contextual
    prioritization (see docs/PENTERA_IMPORT.md "Pentera severity bands")."""

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class AssessmentComparison(BaseModel):
    previous_assessment_id: int | None = None
    previous_assessment_name: str | None = None
    previous_risk_score: float | None = None
    current_assessment_id: int | None = None
    current_assessment_name: str | None = None
    current_risk_score: float | None = None
    risk_reduction_pct: float | None = None
    new_findings: int = 0
    recurring_findings: int = 0
    resolved_findings: int = 0


class DashboardOut(BaseModel):
    top_metrics: TopMetrics
    remediation_metrics: RemediationMetrics
    priority_distribution: PriorityDistribution
    severity_distribution: SeverityDistribution
    category_distribution: dict[str, int]
    comparison: AssessmentComparison | None = None
    assessment_count: int = 0
