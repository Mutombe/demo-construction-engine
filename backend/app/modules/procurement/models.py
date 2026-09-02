import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
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

from app.common.enums import (
    PoDestination,
    PoStatus,
    QuoteStatus,
    RfqStatus,
    VendorStatus,
)
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
    # Where the vendor stands with us, separately from whether their papers are
    # in date: an approved vendor can still have lapsed insurance, and the two
    # need different answers.
    vendor_status: Mapped[VendorStatus] = mapped_column(
        Enum(VendorStatus, name="vendor_status", native_enum=True),
        default=VendorStatus.pending,
        server_default=VendorStatus.pending.value,
        index=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", use_alter=True)
    )
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


class RfqInvite(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """A link that lets one supplier price one RFQ.

    Same shape as the client portal token: only the sha256 hash is stored, the
    raw link is shown once. Scoped to a single (rfq, supplier) pair so a
    supplier can never reach another RFQ, and never sees a competitor's price.
    """

    __tablename__ = "rfq_invites"
    __table_args__ = (UniqueConstraint("rfq_id", "supplier_id"),)

    rfq_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("rfqs.id", ondelete="CASCADE"), index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    rfq: Mapped["Rfq"] = relationship()
    supplier: Mapped["Supplier"] = relationship()


class SupplierAccessToken(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """A link that lets one supplier see their own orders and nothing else.

    Only the hash is stored. A leaked database hands nobody a working link,
    and the raw token is shown once when it is issued.
    """

    __tablename__ = "supplier_access_tokens"

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str | None] = mapped_column(String(120))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupplierInvoice(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """A supplier's claim against an order.

    Deliberately not a posting. Receiving the order already created the
    payable, so booking this as well would owe them twice for one delivery.
    It exists to be matched: the variance against what was ordered is the
    figure that catches overbilling before anybody pays it.
    """

    __tablename__ = "supplier_invoices"
    __table_args__ = (
        UniqueConstraint("supplier_id", "reference", name="uq_supplier_invoice_reference"),
    )

    doc_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), index=True
    )
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="SET NULL"), index=True
    )
    # Their number for it, which is what they will quote when they ring.
    reference: Mapped[str | None] = mapped_column(String(60))
    invoice_date: Mapped[date] = mapped_column(Date, default=date.today)
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    # Positive means they are claiming more than the order was for.
    variance: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    # submitted | accepted | queried
    status: Mapped[str] = mapped_column(String(20), default="submitted", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    decision_note: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", use_alter=True)
    )


class SupplierAssessment(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """How a delivery actually went, judged by whoever took it in.

    Quality and professionalism are the two things about a supplier that no
    record anywhere implies. Whether they were late is in the dates; whether
    they charged what they quoted is in the numbers; whether the blocks were
    sound and whether their driver was a nuisance are known only to the person
    who signed for them, and are lost the moment that person moves on.

    One assessment per order, so a supplier cannot be marked twice for the same
    delivery and a scorecard cannot be padded.
    """

    __tablename__ = "supplier_assessments"
    __table_args__ = (
        UniqueConstraint("purchase_order_id", name="uq_assessment_per_order"),
    )

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), index=True
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="CASCADE")
    )
    assessed_on: Mapped[date] = mapped_column(Date, default=date.today)
    # One to five. Null where the person taking delivery had no view, which is
    # different from a middling score and is kept apart from it.
    quality: Mapped[int | None] = mapped_column(Integer)
    professionalism: Mapped[int | None] = mapped_column(Integer)
    would_use_again: Mapped[bool | None] = mapped_column(Boolean)
    notes: Mapped[str | None] = mapped_column(Text)
