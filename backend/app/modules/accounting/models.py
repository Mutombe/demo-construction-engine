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

    # --- Six-level taxonomy -------------------------------------------------
    # Levels 1 and 2 are derived from account_type on save, so they can never
    # disagree with it. Levels 3 to 5 are chosen; level 6 is the code itself.
    report_type: Mapped[str] = mapped_column(String(20), default="balance_sheet")
    account_class: Mapped[str] = mapped_column(String(20), default="asset")
    account_subclass: Mapped[str] = mapped_column(String(30), default="current_assets", index=True)
    account_type_label: Mapped[str | None] = mapped_column(String(60))
    account_subtype: Mapped[str | None] = mapped_column(String(60))

    # A parent turns a flat chart into sub-accounts: 5000 Materials with
    # 5010 Cement and 5020 Steel underneath, each posting in its own right
    # while the parent reports the total.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), index=True
    )
    # Postable=False makes an account a heading: it groups, it does not receive
    # entries. Posting to a heading is how a chart quietly stops adding up.
    is_postable: Mapped[bool] = mapped_column(Boolean, default=True)

    # Every account holds exactly one currency. A USD account and a ZWL
    # account are different accounts, which is what keeps a trial balance
    # meaningful without a running conversion.
    currency: Mapped[str] = mapped_column(String(3), default="USD", index=True)

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
    # Set when this line moves a control account on behalf of one party, so
    # posting can mirror it into that party's own ledger.
    subsidiary_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("subsidiary_accounts.id", ondelete="RESTRICT"), index=True
    )

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


class ExchangeRate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A rate that applied on a date, kept rather than overwritten.

    History matters: a journal posted in March must keep translating at
    March's rate no matter what today's is, or last year's accounts change
    every time somebody updates a number.
    """

    __tablename__ = "exchange_rates"
    __table_args__ = (
        UniqueConstraint("from_currency", "to_currency", "effective_date"),
    )

    from_currency: Mapped[str] = mapped_column(String(3), index=True)
    to_currency: Mapped[str] = mapped_column(String(3), index=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    effective_date: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str | None] = mapped_column(String(100))


class FiscalPeriod(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A month you can shut.

    Closing is what stops last quarter's numbers moving after they have been
    reported. Posting into a closed period is refused rather than silently
    accepted and quietly changing a statement somebody has already read.
    """

    __tablename__ = "fiscal_periods"
    __table_args__ = (UniqueConstraint("year", "month"),)

    year: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[int] = mapped_column(Integer)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", use_alter=True)
    )


class BankAccount(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """A real account at a real bank, tied to the GL account that mirrors it.

    Two balances on purpose: `book_balance` is what the ledger says, the
    statement is what the bank says, and reconciliation is the work of
    explaining the difference. Collapsing them into one number removes the
    only thing that would have caught a missing entry.
    """

    __tablename__ = "bank_accounts"

    name: Mapped[str] = mapped_column(String(120))
    bank_name: Mapped[str | None] = mapped_column(String(120))
    account_number: Mapped[str | None] = mapped_column(String(50))
    branch: Mapped[str | None] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    kind: Mapped[str] = mapped_column(String(20), default="bank")  # bank | cash | mobile
    gl_account_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), unique=True
    )
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=ZERO)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    gl_account = relationship("Account")


class BankTransaction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A line off the bank statement, before anyone has decided what it is."""

    __tablename__ = "bank_transactions"

    bank_account_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("bank_accounts.id", ondelete="CASCADE"), index=True
    )
    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(String(80))
    # One signed column rather than two: a statement line is money in or money
    # out, and two nullable columns invite a row that is somehow both.
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    # Set when the line has been matched to a journal in our own books.
    matched_journal_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("journals.id", ondelete="SET NULL"), index=True
    )
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SubsidiaryAccount(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One party's own ledger, sitting under a GL control account.

    The general ledger says "you are owed 558,000". This says which client
    owes which part of it. Without the split, chasing a debt means reading
    every certificate ever issued.

    The invariant that makes it trustworthy: the sum of every pocket under a
    control equals that control's balance, because a pocket only ever moves
    as a mirror of a journal line that moved the control in the same journal.
    """

    __tablename__ = "subsidiary_accounts"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "currency", name="uq_subsidiary_party"),
    )

    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    # client | supplier — who the pocket belongs to
    entity_type: Mapped[str] = mapped_column(String(20), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), index=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    control_account_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), index=True
    )
    balance: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=ZERO)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    control_account = relationship("Account")


class SubsidiaryEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A movement on one party's ledger, mirrored from the journal line that
    caused it. Append-only, like the general ledger it shadows."""

    __tablename__ = "subsidiary_entries"
    __table_args__ = (
        UniqueConstraint("journal_line_id", name="uq_subsidiary_entry_line"),
        Index("ix_subsidiary_entries_account_date", "subsidiary_id", "entry_date"),
    )

    subsidiary_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("subsidiary_accounts.id", ondelete="CASCADE"), index=True
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
