from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Asset(Base):
    """The AD object or system affected by a finding (user, computer, group...)."""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_identifier: Mapped[str] = mapped_column(String(500), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(50), default="unknown")
    domain: Mapped[str] = mapped_column(String(255), default="")
    criticality: Mapped[str] = mapped_column(String(20), default="medium")
    tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    asset_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    findings: Mapped[list["Finding"]] = relationship(back_populates="asset")  # noqa: F821
