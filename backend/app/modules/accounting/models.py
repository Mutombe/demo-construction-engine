import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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

from app.common.enums import AccountType, JournalSource, JournalStatus
from app.common.models import AuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base

ZERO = Decimal("0")


class Account(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A line in the chart of accounts.

    `balance` is a cached running total maintained by posting, not a source of
    truth — the general_ledger rows are. It exists so a trial balance is one
    read rather than an aggregate over every row ever written.
    """

    __tablename__ = "accounts"

    code: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, name="account_type", native_enum=True)
    )
    description: Mapped[str | None] = mapped_column(Text)
    # System accounts are the ones automatic posting depends on finding, so
    # they cannot be deleted or retyped out from under it.
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=ZERO)

    @property
    def normal_balance(self) -> str:
        """Derived, never stored: an asset that credits normally is a bug, not
        a configuration choice."""
        return (
            "debit"
            if self.account_type in (AccountType.asset, AccountType.expense)
            else "credit"
        )


class Journal(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """A balanced set of entries, posted as one atomic act."""

    __tablename__ = "journals"
    __table_args__ = (
        Index("ix_journals_source", "source", "source_id"),
        Index("ix_journals_date", "journal_date"),
    )

    doc_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    journal_date: Mapped[date] = mapped_column(Date)
    memo: Mapped[str] = mapped_column(Text)
    status: Mapped[JournalStatus] = mapped_column(
        Enum(JournalStatus, name="journal_status", native_enum=True),
        default=JournalStatus.draft,
    )
    source: Mapped[JournalSource] = mapped_column(
        Enum(JournalSource, name="journal_source", native_enum=True),
        default=JournalSource.manual,
    )
    # What in the rest of the system caused this, so a journal can always be
    # traced back to the delivery note or payslip behind it.
    source_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    # The only analysis dimension this business needs: everything is a job.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    total: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=ZERO)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", use_alter=True)
    )
    reversal_of: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("journals.id", ondelete="SET NULL")
    )

    lines: Mapped[list["JournalLine"]] = relationship(
        back_populates="journal", cascade="all, delete-orphan", order_by="JournalLine.sort_order"
    )


class JournalLine(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One side of one entry. Exactly one of debit/credit carries a value."""

    __tablename__ = "journal_lines"
    __table_args__ = (
        CheckConstraint(
            "(debit = 0 AND credit > 0) OR (debit > 0 AND credit = 0)",
            name="ck_journal_lines_one_sided",
        ),
    )

    journal_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("journals.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), index=True
    )
    debit: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=ZERO)
    credit: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=ZERO)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    journal: Mapped[Journal] = relationship(back_populates="lines")
    account: Mapped[Account] = relationship()


class GeneralLedger(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """The book itself: append-only, one row per posted line.

    Carries the account balance as at that row so an account statement reads
    without re-summing history, and so a mismatch between this and the cached
    account balance is detectable rather than invisible.
    """

    __tablename__ = "general_ledger"
    __table_args__ = (
        UniqueConstraint("journal_line_id", name="uq_general_ledger_line"),
        Index("ix_general_ledger_account_date", "account_id", "entry_date"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), index=True
    )
    journal_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("journals.id", ondelete="CASCADE"), index=True
    )
    journal_line_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("journal_lines.id", ondelete="CASCADE")
    )
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    doc_number: Mapped[str] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(Text)
    debit: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=ZERO)
    credit: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=ZERO)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    project_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), index=True)


class SupplierPayment(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """Money going out to a supplier.

    Exists because payables cannot age without something that settles them:
    before this, a received purchase order sat in Accounts Payable forever and
    an ageing report would have shown every order ever placed as overdue.
    """

    __tablename__ = "supplier_payments"

    doc_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True
    )
    payment_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    method: Mapped[str | None] = mapped_column(String(40))
    reference: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)
    journal_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("journals.id", ondelete="SET NULL")
    )

    allocations: Mapped[list["PaymentAllocation"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )
    supplier = relationship("Supplier")


class PaymentAllocation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Which order a slice of a payment settles.

    A payment is rarely one invoice: a supplier is paid a round figure against
    several orders, so the allocation is its own row rather than a column on
    the payment.
    """

    __tablename__ = "payment_allocations"
    __table_args__ = (UniqueConstraint("payment_id", "purchase_order_id"),)

    payment_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("supplier_payments.id", ondelete="CASCADE"), index=True
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="RESTRICT"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))

    payment: Mapped[SupplierPayment] = relationship(back_populates="allocations")
