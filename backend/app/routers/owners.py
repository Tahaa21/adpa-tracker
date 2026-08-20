from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.owner import Owner
from app.schemas.owner import OwnerCreate, OwnerOut

router = APIRouter(prefix="/owners", tags=["owners"])


@router.get("", response_model=list[OwnerOut])
def list_owners(db: Session = Depends(get_db)):
    return db.query(Owner).order_by(Owner.name).all()


@router.post("", response_model=OwnerOut, status_code=201)
def create_owner(payload: OwnerCreate, db: Session = Depends(get_db)):
    owner = Owner(**payload.model_dump())
    db.add(owner)
    db.commit()
    db.refresh(owner)
    return owner
