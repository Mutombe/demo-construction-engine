import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Computed,
    Date,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import PoDestination, PoStatus, QuoteStatus, RfqStatus
from app.common.models import AuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class Supplier(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    __tablename__ = "suppliers"

    name: Mapped[str] = mapped_column(String(200), unique=True)
    contact_name: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40))
    address: Mapped[str | None] = mapped_column(Text)
    tax_id: Mapped[str | None] = mapped_column(String(60))
    categories: Mapped[str | None] = mapped_column(String(255))  # free-text tags
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Rfq(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    __tablename__ = "rfqs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    doc_number: Mapped[str] = mapped_column(String(20), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[RfqStatus] = mapped_column(
        Enum(RfqStatus, name="rfq_status", native_enum=True), default=RfqStatus.draft
    )
    body: Mapped[str | None] = mapped_column(Text)  # AI-drafted markdown, user-editable
    due_date: Mapped[date | None] = mapped_column(Date)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)

    items: Mapped[list["RfqItem"]] = relationship(
        back_populates="rfq", cascade="all, delete-orphan", order_by="RfqItem.sort_order"
    )
    quotes: Mapped[list["Quote"]] = relationship(back_populates="rfq", cascade="all, delete-orphan")
    project = relationship("Project")


class RfqItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "rfq_items"
    __table_args__ = (UniqueConstraint("rfq_id", "boq_item_id"),)

    rfq_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("rfqs.id", ondelete="CASCADE"), index=True
    )
    # SET NULL + denormalized snapshot: procurement history survives BOQ edits/deletes
    boq_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("boq_items.id", ondelete="SET NULL"), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    rfq: Mapped[Rfq] = relationship(back_populates="items")


class Quote(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    __tablename__ = "quotes"
    __table_args__ = (UniqueConstraint("rfq_id", "supplier_id"),)

    rfq_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("rfqs.id", ondelete="CASCADE"), index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[QuoteStatus] = mapped_column(
        Enum(QuoteStatus, name="quote_status", native_enum=True),
        default=QuoteStatus.received,
    )
    received_date: Mapped[date] = mapped_column(Date, default=date.today)
    valid_until: Mapped[date | None] = mapped_column(Date)
    payment_terms: Mapped[str | None] = mapped_column(String(255))
    delivery_terms: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)  # original pasted quote (audit)
    ai_extracted: Mapped[bool] = mapped_column(Boolean, default=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))

    rfq: Mapped[Rfq] = relationship(back_populates="quotes")
    supplier: Mapped[Supplier] = relationship()
    items: Mapped[list["QuoteItem"]] = relationship(
        back_populates="quote", cascade="all, delete-orphan"
    )


class QuoteItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "quote_items"
    __table_args__ = (UniqueConstraint("quote_id", "rfq_item_id"),)

    quote_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"), index=True
    )
    # Nullable: suppliers may quote lines we did not ask for
    rfq_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("rfq_items.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(20))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    amount: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), Computed("quantity * unit_price", persisted=True)
    )

    quote: Mapped[Quote] = relationship(back_populates="items")
    rfq_item: Mapped[RfqItem | None] = relationship()


class PurchaseOrder(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    __tablename__ = "purchase_orders"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True
    )
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="SET NULL")
    )
    doc_number: Mapped[str] = mapped_column(String(20), unique=True)
    status: Mapped[PoStatus] = mapped_column(
        Enum(PoStatus, name="po_status", native_enum=True), default=PoStatus.draft
    )
    order_date: Mapped[date] = mapped_column(Date, default=date.today)
    expected_delivery: Mapped[date | None] = mapped_column(Date)
    received_date: Mapped[date | None] = mapped_column(Date)
    received_to: Mapped[PoDestination | None] = mapped_column(
        Enum(PoDestination, name="po_destination", native_enum=True)
    )
    terms: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))

    supplier: Mapped[Supplier] = relationship()
    project = relationship("Project")
    items: Mapped[list["PoItem"]] = relationship(back_populates="po", cascade="all, delete-orphan")


class PoItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "po_items"

    po_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="CASCADE"), index=True
    )
    boq_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("boq_items.id", ondelete="SET NULL"), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(20))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    amount: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), Computed("quantity * unit_price", persisted=True)
    )

    po: Mapped[PurchaseOrder] = relationship(back_populates="items")
