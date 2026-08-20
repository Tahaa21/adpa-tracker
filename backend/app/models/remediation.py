from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Remediation(Base):
    """Append-only remediation action/history entry against a Finding."""

    __tablename__ = "remediations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"), nullable=False)
    finding: Mapped["Finding"] = relationship(back_populates="remediations")  # noqa: F821

    owner_id: Mapped[int | None] = mapped_column(ForeignKey("owners.id"), nullable=True)
    owner: Mapped["Owner | None"] = relationship()  # noqa: F821

    status: Mapped[str] = mapped_column(String(30), nullable=False)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
