import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import RequisitionStatus
from app.common.models import AuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class Requisition(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """A site material request: the pipeline stage BEFORE the RFQ.

    Site raises it, procurement actions it by converting to a draft RFQ or a
    draft PO in one click; both links are kept so the chain is auditable.
    Age (today - created_at) of open requisitions is the procurement-delay KPI.
    """

    __tablename__ = "requisitions"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    doc_number: Mapped[str] = mapped_column(String(20), unique=True)
    status: Mapped[RequisitionStatus] = mapped_column(
        Enum(RequisitionStatus, name="requisition_status", native_enum=True),
        default=RequisitionStatus.open,
    )
    needed_by: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    actioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actioned_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", use_alter=True)
    )
    rfq_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("rfqs.id", ondelete="SET NULL")
    )
    po_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="SET NULL")
    )

    project = relationship("Project")
    items: Mapped[list["RequisitionItem"]] = relationship(
        back_populates="requisition",
        cascade="all, delete-orphan",
        order_by="RequisitionItem.sort_order",
    )


class RequisitionItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "requisition_items"

    requisition_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("requisitions.id", ondelete="CASCADE"), index=True
    )
    # SET NULL + snapshot: the request history survives BOQ edits
    boq_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("boq_items.id", ondelete="SET NULL"), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    requisition: Mapped[Requisition] = relationship(back_populates="items")
