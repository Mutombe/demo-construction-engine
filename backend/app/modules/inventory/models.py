import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import StockMovementType
from app.common.models import AuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class StockItem(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """unit_cost is the weighted-average cost, updated only by goods-in movements;
    qty_on_hand is maintained only by movements. Neither is settable via the API."""

    __tablename__ = "stock_items"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100))
    unit: Mapped[str] = mapped_column(String(20))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    qty_on_hand: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    reorder_level: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)


class StockMovement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable stock ledger. quantity is SIGNED (goods_in +, issue -, adjustment
    either), so SUM(quantity) per item reconciles with qty_on_hand. PO deliveries
    into the store are recorded as goods_in with the PO number in `reference`;
    full GRN<->PO integration is future work.
    """

    __tablename__ = "stock_movements"
    __table_args__ = (Index("ix_stock_movements_item_date", "stock_item_id", "movement_date"),)

    stock_item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stock_items.id", ondelete="RESTRICT"), index=True
    )
    doc_number: Mapped[str] = mapped_column(String(20), unique=True)
    movement_type: Mapped[StockMovementType] = mapped_column(
        Enum(StockMovementType, name="stock_movement_type", native_enum=True)
    )
    movement_date: Mapped[date] = mapped_column(Date, default=date.today)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    boq_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("boq_items.id", ondelete="SET NULL")
    )
    cost_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("cost_entries.id", ondelete="SET NULL")
    )
    reference: Mapped[str | None] = mapped_column(String(60))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", use_alter=True)
    )

    stock_item: Mapped[StockItem] = relationship()
    project = relationship("Project")
