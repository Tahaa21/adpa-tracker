from datetime import date

from pydantic import BaseModel, ConfigDict


class ValidationCreate(BaseModel):
    finding_id: int
    validation_method: str | None = None
    evidence: str | None = None
    validation_date: date
    result: str  # PASS | FAIL | INCONCLUSIVE
    validated_by: str | None = None
    notes: str | None = None


class ValidationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    finding_id: int
    validation_method: str | None = None
    evidence: str | None = None
    validation_date: date
    result: str
    validated_by: str | None = None
    notes: str | None = None
