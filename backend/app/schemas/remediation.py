from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class RemediationCreate(BaseModel):
    finding_id: int
    owner_id: int | None = None
    status: str | None = None
    recommended_action: str | None = None
    remediation_notes: str | None = None
    due_date: date | None = None


class RemediationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    finding_id: int
    owner_id: int | None = None
    status: str
    recommended_action: str | None = None
    remediation_notes: str | None = None
    due_date: date | None = None
    created_at: datetime
    updated_at: datetime
