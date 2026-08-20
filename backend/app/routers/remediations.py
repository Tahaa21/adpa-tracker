from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.finding import Finding
from app.schemas.remediation import RemediationCreate, RemediationOut
from app.services.workflow import record_remediation

router = APIRouter(prefix="/remediations", tags=["remediations"])


@router.post("", response_model=RemediationOut, status_code=201)
def create_remediation(payload: RemediationCreate, db: Session = Depends(get_db)):
    finding = db.get(Finding, payload.finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    return record_remediation(
        db,
        finding,
        owner_id=payload.owner_id,
        status=payload.status,
        recommended_action=payload.recommended_action,
        remediation_notes=payload.remediation_notes,
        due_date=payload.due_date,
    )


@router.get("", response_model=list[RemediationOut])
def list_remediations(finding_id: int | None = None, db: Session = Depends(get_db)):
    from app.models.remediation import Remediation

    query = db.query(Remediation)
    if finding_id is not None:
        query = query.filter(Remediation.finding_id == finding_id)
    return query.order_by(Remediation.created_at.desc()).all()
