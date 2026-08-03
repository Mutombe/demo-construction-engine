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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import PayBasis, PayItemKind, PayRunStatus
from app.common.models import AuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class Worker(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """Site labour on the payroll — not system users."""

    __tablename__ = "workers"

    full_name: Mapped[str] = mapped_column(String(120))
    trade: Mapped[str] = mapped_column(String(60))
    national_id: Mapped[str | None] = mapped_column(String(30))
    phone: Mapped[str | None] = mapped_column(String(40))
    pay_basis: Mapped[PayBasis] = mapped_column(
        Enum(PayBasis, name="pay_basis", native_enum=True), default=PayBasis.daily
    )
    rate: Mapped[Decimal] = mapped_column(Numeric(14, 2))  # per hour or per day
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    pay_items: Mapped[list["WorkerPayItem"]] = relationship(
        back_populates="worker", cascade="all, delete-orphan"
    )


class WorkerPayItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Recurring flat allowance/deduction applied once per pay run."""

    __tablename__ = "worker_pay_items"

    worker_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("workers.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[PayItemKind] = mapped_column(
        Enum(PayItemKind, name="pay_item_kind", native_enum=True)
    )
    label: Mapped[str] = mapped_column(String(60))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    worker: Mapped[Worker] = relationship(back_populates="pay_items")


class Timesheet(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """One worker's time on one project on one day.

    quantity is hours (hourly basis) or days (daily basis). pay_run_id is
    stamped when a pay run is approved so the same time can never be paid twice.
    """

    __tablename__ = "timesheets"
    __table_args__ = (UniqueConstraint("worker_id", "project_id", "work_date"),)

    worker_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("workers.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    work_date: Mapped[date] = mapped_column(Date, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    overtime_quantity: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    notes: Mapped[str | None] = mapped_column(Text)
    pay_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pay_runs.id", ondelete="SET NULL"), index=True
    )

    worker: Mapped[Worker] = relationship()


class PayRun(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """A pay period. Approval locks the timesheets and posts one labour cost
    entry per project (source=payroll); totals are snapshotted at approval."""

    __tablename__ = "pay_runs"
    __table_args__ = (
        Index(
            "uq_pay_runs_single_draft",
            "status",
            unique=True,
            postgresql_where=text("status = 'draft'"),
        ),
    )

    doc_number: Mapped[str] = mapped_column(String(20), unique=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[PayRunStatus] = mapped_column(
        Enum(PayRunStatus, name="pay_run_status", native_enum=True),
        default=PayRunStatus.draft,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", use_alter=True)
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    base_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    overtime_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    allowance_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    deduction_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    gross_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    net_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))

    lines: Mapped[list["PayRunLine"]] = relationship(
        back_populates="pay_run", cascade="all, delete-orphan"
    )


class PayRunLine(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One worker's pay for the run. Worker details and money are snapshotted;
    project_allocation records how gross employer cost splits across projects."""

    __tablename__ = "pay_run_lines"
    __table_args__ = (UniqueConstraint("pay_run_id", "worker_id"),)

    pay_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pay_runs.id", ondelete="CASCADE"), index=True
    )
    worker_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("workers.id", ondelete="RESTRICT"), index=True
    )
    worker_name: Mapped[str] = mapped_column(String(120))
    trade: Mapped[str] = mapped_column(String(60))
    pay_basis: Mapped[PayBasis] = mapped_column(
        Enum(PayBasis, name="pay_basis", native_enum=True, create_type=False)
    )
    rate: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    quantity: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=Decimal("0"))
    overtime_quantity: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=Decimal("0"))
    base_pay: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    overtime_pay: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    allowance_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    deduction_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    gross_pay: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    net_pay: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    pay_items: Mapped[list | None] = mapped_column(JSONB)  # [{kind,label,amount}]
    project_allocation: Mapped[list | None] = mapped_column(
        JSONB
    )  # [{project_id,project_code,amount}]

    pay_run: Mapped[PayRun] = relationship(back_populates="lines")
    worker: Mapped[Worker] = relationship()
