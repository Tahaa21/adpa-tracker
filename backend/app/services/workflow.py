"""Finding status-transition rules and remediation/validation side effects.

Kept intentionally small: the one rule that matters for the MVP is that
"remediated" and "validated" are different things.
"""
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.finding import Finding
from app.models.owner import Owner
from app.models.remediation import Remediation
from app.models.validation import ValidationRecord

VALID_STATUSES = {
    "OPEN",
    "TRIAGED",
    "ASSIGNED",
    "IN_REMEDIATION",
    "READY_FOR_VALIDATION",
    "VALIDATED",
    "CLOSED",
    "RISK_ACCEPTED",
    "FALSE_POSITIVE",
    "DEFERRED",
    "REOPENED",
}

# A finding may only become VALIDATED through a validation record, never
# through a direct remediation/status update.
BLOCKED_DIRECT_STATUSES = {"VALIDATED"}


def apply_finding_update(
    db: Session, finding: Finding, owner_id: int | None, status: str | None
) -> Finding:
    if owner_id is not None:
        owner = db.get(Owner, owner_id)
        if owner is None:
            raise HTTPException(status_code=404, detail=f"Owner {owner_id} not found")
        finding.owner_id = owner_id
        if finding.status == "OPEN":
            finding.status = "ASSIGNED"

    if status is not None:
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status '{status}'")
        if status in BLOCKED_DIRECT_STATUSES:
            raise HTTPException(
                status_code=400,
                detail="A finding can only become VALIDATED by recording a passing "
                "validation (POST /validations), not by a direct status update.",
            )
        finding.status = status

    db.flush()
    return finding


def record_remediation(
    db: Session,
    finding: Finding,
    owner_id: int | None,
    status: str | None,
    recommended_action: str | None,
    remediation_notes: str | None,
    due_date: date | None,
) -> Remediation:
    apply_finding_update(db, finding, owner_id=owner_id, status=status)

    entry = Remediation(
        finding_id=finding.id,
        owner_id=finding.owner_id,
        status=finding.status,
        recommended_action=recommended_action,
        remediation_notes=remediation_notes,
        due_date=due_date,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def record_validation(
    db: Session,
    finding: Finding,
    validation_method: str | None,
    evidence: str | None,
    validation_date: date,
    result: str,
    validated_by: str | None,
    notes: str | None,
) -> ValidationRecord:
    if result not in {"PASS", "FAIL", "INCONCLUSIVE"}:
        raise HTTPException(status_code=400, detail=f"Invalid result '{result}'")

    record = ValidationRecord(
        finding_id=finding.id,
        validation_method=validation_method,
        evidence=evidence,
        validation_date=validation_date,
        result=result,
        validated_by=validated_by,
        notes=notes,
    )
    db.add(record)

    if result == "PASS":
        finding.status = "VALIDATED"
    elif result == "FAIL":
        finding.status = "IN_REMEDIATION"
    # INCONCLUSIVE leaves status untouched.

    db.commit()
    db.refresh(record)
    return record
