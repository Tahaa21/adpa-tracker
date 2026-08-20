from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Finding(Base):
    """A persistent logical security issue (NOT one CSV row).

    May be observed across multiple assessments via FindingInstance rows.
    """

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    normalized_type: Mapped[str] = mapped_column(String(50), default="UNKNOWN")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="OTHER")

    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False)
    asset: Mapped["Asset"] = relationship(back_populates="findings")  # noqa: F821

    severity: Mapped[str] = mapped_column(String(20), default="medium")
    risk_score: Mapped[float] = mapped_column(default=0)
    priority: Mapped[str] = mapped_column(String(5), default="P3")
    risk_reasons: Mapped[list] = mapped_column(JSON, default=list)

    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("owners.id"), nullable=True)
    owner: Mapped["Owner | None"] = relationship(back_populates="findings")  # noqa: F821

    first_seen: Mapped[date] = mapped_column(Date, nullable=False)
    last_seen: Mapped[date] = mapped_column(Date, nullable=False)
    currently_present: Mapped[bool] = mapped_column(Boolean, default=True)

    remediation_guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    instances: Mapped[list["FindingInstance"]] = relationship(  # noqa: F821
        back_populates="finding", cascade="all, delete-orphan", order_by="FindingInstance.observed_at"
    )
    remediations: Mapped[list["Remediation"]] = relationship(  # noqa: F821
        back_populates="finding", cascade="all, delete-orphan", order_by="Remediation.created_at"
    )
    validations: Mapped[list["ValidationRecord"]] = relationship(  # noqa: F821
        back_populates="finding", cascade="all, delete-orphan", order_by="ValidationRecord.validation_date"
    )
