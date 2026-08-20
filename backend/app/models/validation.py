from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ValidationRecord(Base):
    """A manually recorded validation result/evidence for a Finding."""

    __tablename__ = "validation_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"), nullable=False)
    finding: Mapped["Finding"] = relationship(back_populates="validations")  # noqa: F821

    validation_method: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_date: Mapped[date] = mapped_column(Date, nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    validated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
