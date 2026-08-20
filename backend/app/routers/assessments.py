from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.assessment import Assessment
from app.models.finding import Finding
from app.models.finding_instance import FindingInstance
from app.schemas.assessment import AssessmentDetailOut, AssessmentOut, PriorityDistribution

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.get("", response_model=list[AssessmentOut])
def list_assessments(db: Session = Depends(get_db)):
    return db.query(Assessment).order_by(Assessment.assessment_date.desc()).all()


def _finding_ids_for_assessment(db: Session, assessment_id: int) -> set[int]:
    rows = (
        db.query(FindingInstance.finding_id)
        .filter(FindingInstance.assessment_id == assessment_id)
        .all()
    )
    return {r[0] for r in rows}


@router.get("/{assessment_id}", response_model=AssessmentDetailOut)
def get_assessment(assessment_id: int, db: Session = Depends(get_db)):
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    current_ids = _finding_ids_for_assessment(db, assessment_id)

    dist_rows = (
        db.query(Finding.priority, func.count(Finding.id))
        .join(FindingInstance, FindingInstance.finding_id == Finding.id)
        .filter(FindingInstance.assessment_id == assessment_id)
        .group_by(Finding.priority)
        .all()
    )
    dist = PriorityDistribution()
    for priority, count in dist_rows:
        if hasattr(dist, priority):
            setattr(dist, priority, count)

    previous = (
        db.query(Assessment)
        .filter(Assessment.assessment_date < assessment.assessment_date)
        .order_by(Assessment.assessment_date.desc())
        .first()
    )

    previous_risk_score = None
    risk_reduction_pct = None
    new_findings = recurring_findings = resolved_findings = 0

    if previous is not None:
        previous_ids = _finding_ids_for_assessment(db, previous.id)
        new_findings = len(current_ids - previous_ids)
        recurring_findings = len(current_ids & previous_ids)
        resolved_findings = len(previous_ids - current_ids)
        previous_risk_score = previous.risk_score
        if previous.risk_score:
            risk_reduction_pct = round(
                (previous.risk_score - (assessment.risk_score or 0)) / previous.risk_score * 100, 1
            )

    return AssessmentDetailOut(
        assessment=assessment,
        priority_distribution=dist,
        findings_observed=len(current_ids),
        previous_assessment_id=previous.id if previous else None,
        previous_risk_score=previous_risk_score,
        risk_reduction_pct=risk_reduction_pct,
        new_findings=new_findings,
        recurring_findings=recurring_findings,
        resolved_findings=resolved_findings,
    )
