from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.assessment import Assessment
from app.models.finding import Finding
from app.models.finding_instance import FindingInstance
from app.schemas.dashboard import (
    AssessmentComparison,
    DashboardOut,
    PriorityDistribution,
    RemediationMetrics,
    SeverityDistribution,
    TopMetrics,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

CLOSED_LIKE = {"VALIDATED", "CLOSED", "FALSE_POSITIVE", "RISK_ACCEPTED"}


def _finding_ids_for_assessment(db: Session, assessment_id: int) -> set[int]:
    rows = (
        db.query(FindingInstance.finding_id)
        .filter(FindingInstance.assessment_id == assessment_id)
        .all()
    )
    return {r[0] for r in rows}


@router.get("", response_model=DashboardOut)
def get_dashboard(db: Session = Depends(get_db)):
    total_findings = db.query(func.count(Finding.id)).scalar() or 0

    present_findings = db.query(Finding).filter(Finding.currently_present.is_(True)).all()

    open_findings = sum(1 for f in present_findings if f.status not in CLOSED_LIKE)
    p1_findings = sum(1 for f in present_findings if f.priority == "P1")
    validated_findings = db.query(func.count(Finding.id)).filter(Finding.status == "VALIDATED").scalar() or 0
    overall_risk_score = (
        round(sum(f.risk_score for f in present_findings) / len(present_findings), 1)
        if present_findings
        else 0
    )

    top_metrics = TopMetrics(
        total_findings=total_findings,
        open_findings=open_findings,
        p1_findings=p1_findings,
        validated_findings=validated_findings,
        overall_risk_score=overall_risk_score,
    )

    status_counts = dict(db.query(Finding.status, func.count(Finding.id)).group_by(Finding.status).all())
    remediation_metrics = RemediationMetrics(
        assigned=status_counts.get("ASSIGNED", 0),
        in_remediation=status_counts.get("IN_REMEDIATION", 0),
        ready_for_validation=status_counts.get("READY_FOR_VALIDATION", 0),
        validated=status_counts.get("VALIDATED", 0),
    )

    priority_dist = PriorityDistribution()
    for f in present_findings:
        if hasattr(priority_dist, f.priority):
            setattr(priority_dist, f.priority, getattr(priority_dist, f.priority) + 1)

    severity_dist = SeverityDistribution()
    for f in present_findings:
        severity = (f.severity or "").lower()
        if hasattr(severity_dist, severity):
            setattr(severity_dist, severity, getattr(severity_dist, severity) + 1)

    category_distribution: dict[str, int] = {}
    for f in present_findings:
        category_distribution[f.category] = category_distribution.get(f.category, 0) + 1

    assessment_count = db.query(func.count(Assessment.id)).scalar() or 0

    comparison = None
    if assessment_count >= 2:
        recent = db.query(Assessment).order_by(Assessment.assessment_date.desc()).limit(2).all()
        current, previous = recent[0], recent[1]
        current_ids = _finding_ids_for_assessment(db, current.id)
        previous_ids = _finding_ids_for_assessment(db, previous.id)

        risk_reduction_pct = None
        if previous.risk_score:
            risk_reduction_pct = round(
                (previous.risk_score - (current.risk_score or 0)) / previous.risk_score * 100, 1
            )

        comparison = AssessmentComparison(
            previous_assessment_id=previous.id,
            previous_assessment_name=previous.name,
            previous_risk_score=previous.risk_score,
            current_assessment_id=current.id,
            current_assessment_name=current.name,
            current_risk_score=current.risk_score,
            risk_reduction_pct=risk_reduction_pct,
            new_findings=len(current_ids - previous_ids),
            recurring_findings=len(current_ids & previous_ids),
            resolved_findings=len(previous_ids - current_ids),
        )

    return DashboardOut(
        top_metrics=top_metrics,
        remediation_metrics=remediation_metrics,
        priority_distribution=priority_dist,
        severity_distribution=severity_dist,
        category_distribution=category_distribution,
        comparison=comparison,
        assessment_count=assessment_count,
    )
