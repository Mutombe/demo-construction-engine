"""Double-entry posting.

Every rule here is enforced at write time, not report time: a general ledger
that only balances when you run the report is not a ledger.

The relationship with `cost_entries` is deliberate. That table stays exactly
what it was — the operational cost ledger every existing report reads — and
the general ledger is posted *from* it. Replacing it would have meant
rewriting project cost, committed cost, valuations and six exports to gain
nothing a second view could not give.
"""

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.common.doc_numbers import next_doc_number
from app.common.enums import (
    AccountType,
    CostCategory,
    CostSource,
    JournalSource,
    JournalStatus,
)
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.accounting.models import Account, GeneralLedger, Journal, JournalLine

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")
CENT = Decimal("0.01")

# --- Chart of accounts -------------------------------------------------------
#
# Ranges are conventional so a bookkeeper can read a code and know what it is:
# 1xxx assets, 2xxx liabilities, 3xxx equity, 4xxx revenue, 5xxx cost of works,
# 6xxx overheads.

BANK = "1000"
ACCOUNTS_RECEIVABLE = "1100"
RETENTION_RECEIVABLE = "1200"
INVENTORY = "1300"
ACCOUNTS_PAYABLE = "2000"
ACCRUED_COSTS = "2100"
PAYROLL_PAYABLE = "2200"
RETAINED_EARNINGS = "3000"
CONTRACT_REVENUE = "4000"

DEFAULT_CHART: list[tuple[str, str, AccountType, str]] = [
    (BANK, "Cash and Bank", AccountType.asset, "Money actually held"),
    (ACCOUNTS_RECEIVABLE, "Accounts Receivable", AccountType.asset, "Certified and unpaid"),
    (
        RETENTION_RECEIVABLE,
        "Retention Receivable",
        AccountType.asset,
        "Held by the client until the defects period ends",
    ),
    (INVENTORY, "Inventory", AccountType.asset, "Materials in store, at weighted average cost"),
    (ACCOUNTS_PAYABLE, "Accounts Payable", AccountType.liability, "Owed to suppliers"),
    (ACCRUED_COSTS, "Accrued Costs", AccountType.liability, "Incurred, not yet invoiced"),
    (PAYROLL_PAYABLE, "Payroll Payable", AccountType.liability, "Approved pay runs not yet paid"),
    (RETAINED_EARNINGS, "Retained Earnings", AccountType.equity, "Accumulated result"),
    (CONTRACT_REVENUE, "Contract Revenue", AccountType.revenue, "Certified work"),
    ("5000", "Cost of Works — Materials", AccountType.expense, ""),
    ("5100", "Cost of Works — Labour", AccountType.expense, ""),
    ("5200", "Cost of Works — Plant", AccountType.expense, ""),
    ("5300", "Cost of Works — Subcontract", AccountType.expense, ""),
    ("5400", "Cost of Works — Preliminaries", AccountType.expense, ""),
    ("5900", "Cost of Works — Other", AccountType.expense, ""),
]

COST_ACCOUNT_BY_CATEGORY = {
    CostCategory.material: "5000",
    CostCategory.labour: "5100",
    CostCategory.plant: "5200",
    CostCategory.subcontract: "5300",
    CostCategory.preliminaries: "5400",
    CostCategory.other: "5900",
}

# What the other side of a cost is depends on how the cost arose.
CREDIT_ACCOUNT_BY_SOURCE = {
    CostSource.purchase_order: ACCOUNTS_PAYABLE,
    CostSource.invoice: ACCOUNTS_PAYABLE,
    CostSource.inventory_issue: INVENTORY,
    CostSource.payroll: PAYROLL_PAYABLE,
    CostSource.expense: ACCRUED_COSTS,
    CostSource.manual: ACCRUED_COSTS,
}


def ensure_chart(db: Session) -> list[Account]:
    """Idempotent. Safe to call on every startup and from every test."""
    existing = {a.code: a for a in db.scalars(select(Account))}
    created = []
    for code, name, kind, description in DEFAULT_CHART:
        if code in existing:
            continue
        account = Account(
            code=code,
            name=name,
            account_type=kind,
            description=description or None,
            is_system=True,
        )
        db.add(account)
        created.append(account)
    if created:
        db.flush()
    return created


def account_by_code(db: Session, code: str) -> Account:
    account = db.scalar(select(Account).where(Account.code == code))
    if account is None:
        # Only reachable if someone deleted a system account out from under
        # posting, which the delete guard prevents.
        raise NotFoundError(f"Account {code} is missing from the chart of accounts")
    return account


# --- Posting -----------------------------------------------------------------


def create_journal(
    db: Session,
    *,
    journal_date: date,
    memo: str,
    lines: list[dict],
    source: JournalSource = JournalSource.manual,
    source_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
) -> Journal:
    """Builds a draft. Nothing hits the ledger until post()."""
    if len(lines) < 2:
        raise ValidationFailedError("A journal needs at least two lines")

    journal = Journal(
        doc_number=next_doc_number(db, Journal, "JRN"),
        journal_date=journal_date,
        memo=memo,
        source=source,
        source_id=source_id,
        project_id=project_id,
        created_by=created_by,
        status=JournalStatus.draft,
    )
    db.add(journal)
    db.flush()

    for index, raw in enumerate(lines):
        debit = Decimal(str(raw.get("debit") or 0)).quantize(CENT)
        credit = Decimal(str(raw.get("credit") or 0)).quantize(CENT)
        if debit < 0 or credit < 0:
            raise ValidationFailedError("A journal line cannot be negative")
        if (debit > 0) == (credit > 0):
            raise ValidationFailedError(
                "Each line is either a debit or a credit, never both or neither"
            )
        account_id = raw.get("account_id")
        if raw.get("account_code"):
            account_id = account_by_code(db, raw["account_code"]).id
        if db.get(Account, account_id) is None:
            raise NotFoundError("Account not found")
        db.add(
            JournalLine(
                journal_id=journal.id,
                account_id=account_id,
                debit=debit,
                credit=credit,
                description=raw.get("description"),
                sort_order=index,
            )
        )
    db.flush()
    _validate_balanced(db, journal)
    return journal


def _validate_balanced(db: Session, journal: Journal) -> Decimal:
    totals = db.execute(
        select(func.coalesce(func.sum(JournalLine.debit), 0), func.coalesce(func.sum(JournalLine.credit), 0))
        .where(JournalLine.journal_id == journal.id)
    ).one()
    debits, credits = Decimal(totals[0]).quantize(CENT), Decimal(totals[1]).quantize(CENT)
    if debits != credits:
        raise ValidationFailedError(
            f"Journal does not balance: debits {debits} against credits {credits}"
        )
    if debits == 0:
        raise ValidationFailedError("A journal of zero moves nothing")
    journal.total = debits
    return debits


def post(db: Session, journal_id: uuid.UUID, user=None) -> Journal:
    """Writes the ledger rows and moves the account balances, atomically.

    Accounts are locked in id order so two journals touching the same pair of
    accounts can never deadlock against each other.
    """
    journal = get_journal(db, journal_id)
    if journal.status is JournalStatus.posted:
        raise ConflictError("This journal has already been posted")
    if journal.status is JournalStatus.reversed:
        raise ConflictError("A reversed journal cannot be posted again")

    _validate_balanced(db, journal)
    lines = list(
        db.scalars(
            select(JournalLine)
            .where(JournalLine.journal_id == journal.id)
            .order_by(JournalLine.sort_order, JournalLine.id)
        )
    )

    account_ids = sorted({line.account_id for line in lines})
    accounts = {
        account.id: account
        for account in db.scalars(
            select(Account).where(Account.id.in_(account_ids)).order_by(Account.id).with_for_update()
        )
    }
    for account in accounts.values():
        if not account.is_active:
            raise ValidationFailedError(f"Account {account.code} is not active")

    for line in lines:
        account = accounts[line.account_id]
        # Balance moves in the account's own direction, so an asset grows on a
        # debit and a liability grows on a credit. Reading a raw signed number
        # otherwise means knowing the type to interpret it.
        movement = (
            line.debit - line.credit
            if account.normal_balance == "debit"
            else line.credit - line.debit
        )
        account.balance = (Decimal(account.balance) + movement).quantize(CENT)
        db.add(
            GeneralLedger(
                account_id=account.id,
                journal_id=journal.id,
                journal_line_id=line.id,
                entry_date=journal.journal_date,
                doc_number=journal.doc_number,
                description=line.description or journal.memo,
                debit=line.debit,
                credit=line.credit,
                balance_after=account.balance,
                project_id=journal.project_id,
            )
        )

    journal.status = JournalStatus.posted
    journal.posted_at = datetime.now(timezone.utc)
    journal.posted_by = getattr(user, "id", None)
    db.flush()
    return journal


def reverse(db: Session, journal_id: uuid.UUID, user=None) -> Journal:
    """Posts the mirror image rather than deleting anything.

    A ledger you can edit is not evidence of anything, so a mistake is
    corrected by a second entry that is also permanent.
    """
    original = get_journal(db, journal_id)
    if original.status is not JournalStatus.posted:
        raise ConflictError("Only a posted journal can be reversed")
    if db.scalar(select(Journal).where(Journal.reversal_of == original.id)):
        raise ConflictError("This journal has already been reversed")

    mirrored = [
        {
            "account_id": line.account_id,
            "debit": line.credit,
            "credit": line.debit,
            "description": line.description,
        }
        for line in original.lines
    ]
    reversal = create_journal(
        db,
        journal_date=date.today(),
        memo=f"Reversal of {original.doc_number}: {original.memo}",
        lines=mirrored,
        source=JournalSource.reversal,
        source_id=original.id,
        project_id=original.project_id,
        created_by=getattr(user, "id", None),
    )
    reversal.reversal_of = original.id
    post(db, reversal.id, user)
    original.status = JournalStatus.reversed
    db.flush()
    return reversal


def get_journal(db: Session, journal_id: uuid.UUID) -> Journal:
    journal = db.scalar(
        select(Journal).options(selectinload(Journal.lines)).where(Journal.id == journal_id)
    )
    if journal is None:
        raise NotFoundError("Journal not found")
    return journal


# --- Automatic posting -------------------------------------------------------


def _category_of(db: Session, entry) -> CostCategory | None:
    """Cost entries carry no category of their own — it lives on the BOQ item
    the cost was booked against. Unbooked costs land in Other, which is honest
    rather than guessed."""
    if entry.boq_item_id is None:
        return None
    from app.modules.boq.models import BoqItem

    item = db.get(BoqItem, entry.boq_item_id)
    return item.cost_category if item else None


def post_cost_entry(db: Session, entry, user=None) -> Journal | None:
    """One cost, one journal: debit the works account, credit whatever the
    cost came from.

    Never raises into the caller. A ledger problem must not roll back the
    delivery that was being received — the journal can be written later, the
    goods cannot be un-received.
    """
    try:
        ensure_chart(db)
        debit_code = COST_ACCOUNT_BY_CATEGORY.get(_category_of(db, entry), "5900")
        credit_code = CREDIT_ACCOUNT_BY_SOURCE.get(entry.source, ACCRUED_COSTS)
        amount = Decimal(entry.amount).quantize(CENT)
        if amount == 0:
            return None
        journal = create_journal(
            db,
            journal_date=entry.entry_date,
            memo=entry.description or "Project cost",
            source=JournalSource.cost_entry,
            source_id=entry.id,
            project_id=entry.project_id,
            created_by=getattr(user, "id", None),
            lines=[
                {"account_code": debit_code, "debit": amount, "description": entry.description},
                {"account_code": credit_code, "credit": amount, "description": entry.description},
            ],
        )
        return post(db, journal.id, user)
    except Exception:
        logger.exception("Could not post cost entry %s to the ledger", entry.id)
        return None


def post_valuation(db: Session, valuation, user=None) -> Journal | None:
    """Certifying work is what turns it into revenue.

    Retention is cumulative on this model, so the amount withheld *this period*
    is the difference against the previous certificate — posting the cumulative
    figure would re-recognise retention every month.
    """
    try:
        from app.modules.valuations.models import Valuation

        ensure_chart(db)
        previous_retention = db.scalar(
            select(func.coalesce(func.max(Valuation.retention_amount), 0)).where(
                Valuation.project_id == valuation.project_id,
                Valuation.valuation_number < valuation.valuation_number,
                Valuation.status.in_(("issued", "paid")),
            )
        ) or ZERO
        retention_delta = (
            Decimal(valuation.retention_amount) - Decimal(previous_retention)
        ).quantize(CENT)
        receivable = Decimal(valuation.net_certified).quantize(CENT)
        revenue = (receivable + retention_delta).quantize(CENT)
        if revenue == 0:
            return None

        lines = [{"account_code": ACCOUNTS_RECEIVABLE, "debit": receivable}]
        if retention_delta > 0:
            lines.append({"account_code": RETENTION_RECEIVABLE, "debit": retention_delta})
        lines.append({"account_code": CONTRACT_REVENUE, "credit": revenue})

        journal = create_journal(
            db,
            journal_date=valuation.period_end,
            memo=f"{valuation.doc_number} certified",
            source=JournalSource.valuation,
            source_id=valuation.id,
            project_id=valuation.project_id,
            created_by=getattr(user, "id", None),
            lines=lines,
        )
        return post(db, journal.id, user)
    except Exception:
        logger.exception("Could not post valuation %s to the ledger", valuation.id)
        return None


def post_goods_in(db: Session, *, amount, reference: str, when: date, user=None) -> Journal | None:
    """Stock arriving is an asset swap, not a cost: the project is not charged
    until the material is issued to it."""
    try:
        ensure_chart(db)
        value = Decimal(amount).quantize(CENT)
        if value <= 0:
            logger.warning("Goods-in for %s valued at %s, nothing posted", reference, value)
            return None
        journal = create_journal(
            db,
            journal_date=when,
            memo=f"Goods received on {reference}",
            source=JournalSource.goods_in,
            created_by=getattr(user, "id", None),
            lines=[
                {"account_code": INVENTORY, "debit": value},
                {"account_code": ACCOUNTS_PAYABLE, "credit": value},
            ],
        )
        return post(db, journal.id, user)
    except Exception:
        logger.exception("Could not post goods-in for %s to the ledger", reference)
        return None


# --- Reporting ---------------------------------------------------------------


def unposted_cost_entries(db: Session) -> list:
    """Cost entries with no journal behind them.

    The automatic posters deliberately never raise into the business action
    that triggered them — a ledger problem must not roll back a delivery that
    physically arrived. The cost of that choice is that a failure would be
    invisible, so this is the control that makes it visible instead. It should
    always be empty.
    """
    from app.modules.costs.models import CostEntry

    posted = select(Journal.source_id).where(
        Journal.source == JournalSource.cost_entry, Journal.source_id.is_not(None)
    )
    return list(
        db.scalars(
            select(CostEntry)
            .where(CostEntry.id.notin_(posted), CostEntry.amount != 0)
            .order_by(CostEntry.entry_date.desc())
        )
    )


def post_missing(db: Session, user=None) -> int:
    """Catch up anything the control above found. Idempotent by construction:
    an entry that now has a journal is no longer in the list."""
    entries = unposted_cost_entries(db)
    posted = 0
    for entry in entries:
        if post_cost_entry(db, entry, user) is not None:
            posted += 1
    return posted


def trial_balance(db: Session, as_at: date | None = None) -> dict:
    """Debits and credits by account. The totals must agree; if they ever do
    not, posting is broken and the number on screen says so."""
    stmt = (
        select(
            Account.id,
            Account.code,
            Account.name,
            Account.account_type,
            func.coalesce(func.sum(GeneralLedger.debit), 0),
            func.coalesce(func.sum(GeneralLedger.credit), 0),
        )
        .join(GeneralLedger, GeneralLedger.account_id == Account.id, isouter=True)
        .group_by(Account.id, Account.code, Account.name, Account.account_type)
        .order_by(Account.code)
    )
    if as_at is not None:
        stmt = stmt.where((GeneralLedger.entry_date <= as_at) | (GeneralLedger.id.is_(None)))

    rows = []
    total_debit = total_credit = ZERO
    for account_id, code, name, kind, debits, credits in db.execute(stmt).all():
        debits = Decimal(debits).quantize(CENT)
        credits = Decimal(credits).quantize(CENT)
        if debits == 0 and credits == 0:
            continue
        net = debits - credits
        rows.append(
            {
                "account_id": account_id,
                "code": code,
                "name": name,
                "account_type": kind.value,
                "debit": debits,
                "credit": credits,
                "balance": net if kind in (AccountType.asset, AccountType.expense) else -net,
            }
        )
        total_debit += debits
        total_credit += credits
    return {
        "as_at": as_at or date.today(),
        "rows": rows,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "balanced": total_debit == total_credit,
    }


def income_statement(db: Session, start: date, end: date, project_id=None) -> dict:
    stmt = (
        select(
            Account.code,
            Account.name,
            Account.account_type,
            func.coalesce(func.sum(GeneralLedger.credit - GeneralLedger.debit), 0),
        )
        .join(GeneralLedger, GeneralLedger.account_id == Account.id)
        .where(
            Account.account_type.in_((AccountType.revenue, AccountType.expense)),
            GeneralLedger.entry_date >= start,
            GeneralLedger.entry_date <= end,
        )
        .group_by(Account.code, Account.name, Account.account_type)
        .order_by(Account.code)
    )
    if project_id is not None:
        stmt = stmt.where(GeneralLedger.project_id == project_id)

    revenue, expenses = [], []
    revenue_total = expense_total = ZERO
    for code, name, kind, net in db.execute(stmt).all():
        value = Decimal(net).quantize(CENT)
        if kind is AccountType.revenue:
            revenue.append({"code": code, "name": name, "amount": value})
            revenue_total += value
        else:
            # Expenses accumulate on the debit side, so flip the sign back.
            amount = -value
            expenses.append({"code": code, "name": name, "amount": amount})
            expense_total += amount
    return {
        "start": start,
        "end": end,
        "revenue": revenue,
        "expenses": expenses,
        "revenue_total": revenue_total,
        "expense_total": expense_total,
        "net_result": revenue_total - expense_total,
    }


def balance_sheet(db: Session, as_at: date) -> dict:
    stmt = (
        select(
            Account.code,
            Account.name,
            Account.account_type,
            func.coalesce(func.sum(GeneralLedger.debit - GeneralLedger.credit), 0),
        )
        .join(GeneralLedger, GeneralLedger.account_id == Account.id)
        .where(GeneralLedger.entry_date <= as_at)
        .group_by(Account.code, Account.name, Account.account_type)
        .order_by(Account.code)
    )
    assets, liabilities, equity = [], [], []
    asset_total = liability_total = equity_total = ZERO
    retained = ZERO
    for code, name, kind, net in db.execute(stmt).all():
        value = Decimal(net).quantize(CENT)
        if kind is AccountType.asset:
            assets.append({"code": code, "name": name, "amount": value})
            asset_total += value
        elif kind is AccountType.liability:
            liabilities.append({"code": code, "name": name, "amount": -value})
            liability_total += -value
        elif kind is AccountType.equity:
            equity.append({"code": code, "name": name, "amount": -value})
            equity_total += -value
        else:
            # Revenue and expenses roll into the result for the period, which
            # is what makes the sheet balance before any year-end close.
            retained += -value
    return {
        "as_at": as_at,
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "asset_total": asset_total,
        "liability_total": liability_total,
        "equity_total": equity_total,
        "result_for_period": retained,
        "balanced": asset_total == (liability_total + equity_total + retained),
    }


def account_ledger(
    db: Session, account_id: uuid.UUID, start: date | None = None, end: date | None = None
) -> list[GeneralLedger]:
    stmt = select(GeneralLedger).where(GeneralLedger.account_id == account_id)
    if start:
        stmt = stmt.where(GeneralLedger.entry_date >= start)
    if end:
        stmt = stmt.where(GeneralLedger.entry_date <= end)
    return list(db.scalars(stmt.order_by(GeneralLedger.entry_date, GeneralLedger.created_at)))
