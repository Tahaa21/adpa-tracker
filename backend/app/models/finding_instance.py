from datetime import date

from sqlalchemy import JSON, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class FindingInstance(Base):
    """One observation of a Finding within one Assessment."""

    __tablename__ = "finding_instances"
    __table_args__ = (UniqueConstraint("finding_id", "assessment_id", name="uq_finding_assessment"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"), nullable=False)
    finding: Mapped["Finding"] = relationship(back_populates="instances")  # noqa: F821

    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), nullable=False)
    assessment: Mapped["Assessment"] = relationship(back_populates="instances")  # noqa: F821

    source_severity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_row: Mapped[dict] = mapped_column(JSON, default=dict)
    observed_at: Mapped[date] = mapped_column(Date, nullable=False)
