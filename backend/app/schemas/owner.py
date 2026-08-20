from pydantic import BaseModel, ConfigDict


class OwnerCreate(BaseModel):
    name: str
    team: str | None = None
    email: str | None = None


class OwnerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    team: str | None = None
    email: str | None = None
