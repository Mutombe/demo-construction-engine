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
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import (
    ComplianceDocType,
    MilestoneStatus,
    SubcontractStatus,
)
from app.common.models import AuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base

ZERO = Decimal("0")


class ComplianceDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """A certificate a supplier has to keep in date.

    Expiry is the whole point. A tax clearance that was valid when the vendor
    was approved and lapsed six months later is exactly what an audit finds,
    so the record carries the date rather than a "verified" tick.
    """

    __tablename__ = "compliance_documents"
    __table_args__ = (
        Index("ix_compliance_supplier_type", "supplier_id", "doc_type"),
        Index("ix_compliance_expiry", "expires_on"),
    )

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), index=True
    )
    doc_type: Mapped[ComplianceDocType] = mapped_column(
        Enum(ComplianceDocType, name="compliance_doc_type", native_enum=True)
    )
    reference: Mapped[str | None] = mapped_column(String(80))
    issued_on: Mapped[date | None] = mapped_column(Date)
    # Null means it does not expire — a company registration, typically.
    expires_on: Mapped[date | None] = mapped_column(Date)
    # The scan itself, in the media library like every other document.
    media_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("media_files.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)


class ComplianceRequirement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """What this company insists on before it will trade with someone.

    Configurable rather than hard-coded: what a contractor demands of a
    scaffolder is not what it demands of a stationery supplier, and the list
    changes when the law does.
    """

    __tablename__ = "compliance_requirements"
    __table_args__ = (UniqueConstraint("doc_type", name="uq_compliance_requirement_type"),)

    doc_type: Mapped[ComplianceDocType] = mapped_column(
        Enum(ComplianceDocType, name="compliance_doc_type", native_enum=True)
    )
    # False for documents that are nice to hold but should not stop a job.
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    # How long before expiry it starts warning.
    warn_days: Mapped[int] = mapped_column(Integer, default=30)
    applies_to: Mapped[str | None] = mapped_column(String(255))


class Subcontract(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """A package of work let to a subcontractor, paid against milestones.

    Separate from a purchase order because the shape is different: an order is
    goods on a date, a subcontract is work in stages with retention held back
    until the defects period ends.
    """

    __tablename__ = "subcontracts"

    doc_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    scope: Mapped[str | None] = mapped_column(Text)
    value: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=ZERO)
    # Held back from every certificate until the defects period ends. The
    # mirror of the retention our own client holds from us.
    retention_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=ZERO)
    status: Mapped[SubcontractStatus] = mapped_column(
        Enum(SubcontractStatus, name="subcontract_status", native_enum=True),
        default=SubcontractStatus.draft,
        index=True,
    )
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    awarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    awarded_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", use_alter=True)
    )
    notes: Mapped[str | None] = mapped_column(Text)

    milestones: Mapped[list["SubcontractMilestone"]] = relationship(
        back_populates="subcontract",
        cascade="all, delete-orphan",
        order_by="SubcontractMilestone.sort_order",
    )
    supplier = relationship("Supplier")
    project = relationship("Project")


class SubcontractMilestone(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """A stage of the work, and the money that turns on it.

    `certified_amount` is separate from `value` on purpose: a stage is often
    signed off at less than it was priced, and overwriting the price would
    lose what was agreed.
    """

    __tablename__ = "subcontract_milestones"

    subcontract_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("subcontracts.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    value: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    due_date: Mapped[date | None] = mapped_column(Date)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[MilestoneStatus] = mapped_column(
        Enum(MilestoneStatus, name="milestone_status", native_enum=True),
        default=MilestoneStatus.pending,
        index=True,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    certified_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    retention_held: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    certified_on: Mapped[date | None] = mapped_column(Date)
    certified_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", use_alter=True)
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    cost_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("cost_entries.id", ondelete="SET NULL")
    )

    subcontract: Mapped[Subcontract] = relationship(back_populates="milestones")
