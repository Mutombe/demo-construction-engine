import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import StockMovementType, StocktakeStatus
from app.common.models import AuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class StockItem(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """unit_cost is the weighted-average cost, updated only by goods-in movements;
    qty_on_hand is maintained only by movements. Neither is settable via the API."""

    __tablename__ = "stock_items"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    barcode: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
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


class Stocktake(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """A counting session: snapshot expected quantities, enter counts, review
    the variance, then approve — which posts the adjustments in one go.

    Counting against a snapshot (rather than live qty_on_hand) means movements
    that happen mid-count do not silently change what the counter was told to
    expect; the variance stays honest about the moment of the count.
    """

    __tablename__ = "stocktakes"

    doc_number: Mapped[str] = mapped_column(String(20), unique=True)
    status: Mapped[StocktakeStatus] = mapped_column(
        Enum(StocktakeStatus, name="stocktake_status", native_enum=True),
        default=StocktakeStatus.counting,
    )
    count_date: Mapped[date] = mapped_column(Date, default=date.today)
    notes: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", use_alter=True)
    )

    lines: Mapped[list["StocktakeLine"]] = relationship(
        back_populates="stocktake", cascade="all, delete-orphan"
    )


class StocktakeLine(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "stocktake_lines"
    __table_args__ = (UniqueConstraint("stocktake_id", "stock_item_id"),)

    stocktake_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stocktakes.id", ondelete="CASCADE"), index=True
    )
    stock_item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stock_items.id", ondelete="RESTRICT"), index=True
    )
    expected_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    counted_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    notes: Mapped[str | None] = mapped_column(Text)

    stocktake: Mapped[Stocktake] = relationship(back_populates="lines")
    stock_item: Mapped[StockItem] = relationship()
