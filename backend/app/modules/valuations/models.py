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

    @property
    def is_measured(self) -> bool:
        return len(self.lines) > 0

    project = relationship("Project")
    lines: Mapped[list["ValuationLine"]] = relationship(
        back_populates="valuation",
        cascade="all, delete-orphan",
        order_by="ValuationLine.item_code",
    )


class ValuationLine(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One measured BOQ line on a valuation's measurement sheet.

    BOQ details are snapshotted so a later rate edit on the BOQ cannot rewrite
    an issued certificate; amount = qty_to_date x rate is computed in the
    service, and the parent's gross_valuation is the sum of line amounts.
    """

    __tablename__ = "valuation_lines"
    __table_args__ = (UniqueConstraint("valuation_id", "boq_item_id"),)

    valuation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("valuations.id", ondelete="CASCADE"), index=True
    )
    boq_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("boq_items.id", ondelete="SET NULL"), index=True
    )
    item_code: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(10))
    rate: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    boq_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    qty_to_date: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    valuation: Mapped[Valuation] = relationship(back_populates="lines")
