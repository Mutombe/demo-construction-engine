import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import ValuationStatus
from app.common.models import AuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class Valuation(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """Cumulative progress valuation / payment certificate.

    gross_valuation is the cumulative work done to date; retention_amount,
    previous_certified and net_certified are snapshotted at write time so
    later retention_pct edits on the project cannot rewrite history.
    """

    __tablename__ = "valuations"
    __table_args__ = (
        UniqueConstraint("project_id", "valuation_number"),
        Index(
            "uq_valuations_project_draft",
            "project_id",
            unique=True,
            postgresql_where=text("status = 'draft'"),
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    doc_number: Mapped[str] = mapped_column(String(20), unique=True)
    valuation_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[ValuationStatus] = mapped_column(
        Enum(ValuationStatus, name="valuation_status", native_enum=True),
        default=ValuationStatus.draft,
    )
    period_end: Mapped[date] = mapped_column(Date)
    gross_valuation: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    retention_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    previous_certified: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    net_certified: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    issued_date: Mapped[date | None] = mapped_column(Date)
    paid_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    project = relationship("Project")
