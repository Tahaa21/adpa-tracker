from datetime import date

from pydantic import BaseModel, ConfigDict

from app.schemas.asset import AssetOut
from app.schemas.owner import OwnerOut
from app.schemas.remediation import RemediationOut
from app.schemas.validation import ValidationOut


class FindingInstanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    assessment_id: int
    source_severity: str | None = None
    source_title: str | None = None
    observed_at: date


class FindingListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    normalized_type: str
    title: str
    category: str
    severity: str
    risk_score: float
    priority: str
    status: str
    first_seen: date
    last_seen: date
    currently_present: bool
    asset: AssetOut
    owner: OwnerOut | None = None


class FindingDetail(FindingListItem):
    risk_reasons: list[str] = []
    remediation_guidance: str | None = None
    description: str | None = None
    source_metadata: dict = {}
    fingerprint: str
    instances: list[FindingInstanceOut] = []
    remediations: list[RemediationOut] = []
    validations: list[ValidationOut] = []


class FindingUpdate(BaseModel):
    owner_id: int | None = None
    status: str | None = None
