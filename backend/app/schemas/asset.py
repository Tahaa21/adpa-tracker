from pydantic import BaseModel, ConfigDict


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_identifier: str
    name: str
    asset_type: str
    domain: str
    criticality: str
    tier: str | None = None
