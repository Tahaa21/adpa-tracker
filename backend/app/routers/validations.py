from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.finding import Finding
from app.schemas.validation import ValidationCreate, ValidationOut
from app.services.workflow import record_validation

router = APIRouter(prefix="/validations", tags=["validations"])


@router.post("", response_model=ValidationOut, status_code=201)
def create_validation(payload: ValidationCreate, db: Session = Depends(get_db)):
    finding = db.get(Finding, payload.finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    return record_validation(
        db,
        finding,
        validation_method=payload.validation_method,
        evidence=payload.evidence,
        validation_date=payload.validation_date,
        result=payload.result,
        validated_by=payload.validated_by,
        notes=payload.notes,
    )


@router.get("", response_model=list[ValidationOut])
def list_validations(finding_id: int | None = None, db: Session = Depends(get_db)):
    from app.models.validation import ValidationRecord

    query = db.query(ValidationRecord)
    if finding_id is not None:
        query = query.filter(ValidationRecord.finding_id == finding_id)
    return query.order_by(ValidationRecord.validation_date.desc()).all()
