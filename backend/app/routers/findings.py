from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.db import get_db
from app.models.asset import Asset
from app.models.finding import Finding
from app.schemas.finding import FindingDetail, FindingListItem, FindingUpdate
from app.services.workflow import apply_finding_update

router = APIRouter(prefix="/findings", tags=["findings"])


@router.get("", response_model=list[FindingListItem])
def list_findings(
    db: Session = Depends(get_db),
    search: str | None = None,
    priority: str | None = None,
    status: str | None = None,
    category: str | None = None,
    severity: str | None = None,
    owner_id: int | None = None,
    currently_present: bool | None = None,
):
    query = db.query(Finding).options(
        joinedload(Finding.asset), joinedload(Finding.owner), joinedload(Finding.instances)
    )
    query = query.join(Asset, Finding.asset_id == Asset.id)

    if search:
        like = f"%{search.strip()}%"
        query = query.filter(
            or_(Finding.title.ilike(like), Asset.name.ilike(like), Asset.external_identifier.ilike(like))
        )
    if priority:
        query = query.filter(Finding.priority == priority)
    if status:
        query = query.filter(Finding.status == status)
    if category:
        query = query.filter(Finding.category == category)
    if severity:
        query = query.filter(Finding.severity == severity)
    if owner_id is not None:
        query = query.filter(Finding.owner_id == owner_id)
    if currently_present is not None:
        query = query.filter(Finding.currently_present == currently_present)

    return query.order_by(Finding.risk_score.desc()).all()


@router.get("/{finding_id}", response_model=FindingDetail)
def get_finding(finding_id: int, db: Session = Depends(get_db)):
    finding = (
        db.query(Finding)
        .options(
            joinedload(Finding.asset),
            joinedload(Finding.owner),
            joinedload(Finding.instances),
            joinedload(Finding.remediations),
            joinedload(Finding.validations),
        )
        .filter(Finding.id == finding_id)
        .first()
    )
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    return finding


@router.patch("/{finding_id}", response_model=FindingDetail)
def update_finding(finding_id: int, payload: FindingUpdate, db: Session = Depends(get_db)):
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    apply_finding_update(db, finding, owner_id=payload.owner_id, status=payload.status)
    db.commit()
    db.refresh(finding)
    return finding
