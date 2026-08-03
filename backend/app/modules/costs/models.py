import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Enum, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import CostSource
from app.common.models import AuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class CostEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """Actuals ledger. Future modules (expenses, POs, invoices, payroll) write here
    with their own `source`; M1 records `manual` entries only."""

    __tablename__ = "cost_entries"
    __table_args__ = (Index("ix_cost_entries_project_date", "project_id", "entry_date"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    # Nullable on purpose: unallocated site costs are real and must count against budget
    boq_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("boq_items.id", ondelete="SET NULL"), index=True
    )
    entry_date: Mapped[date] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    source: Mapped[CostSource] = mapped_column(
        Enum(CostSource, name="cost_source", native_enum=True), default=CostSource.manual
    )
    reference: Mapped[str | None] = mapped_column(String(60))
