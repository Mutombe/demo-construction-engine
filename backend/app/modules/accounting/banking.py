"""Bank reconciliation: explaining the difference rather than hiding it.

Two balances that legitimately disagree — the books and the statement — and
the work is accounting for every item in the gap. The arithmetic is the
classic one, written the way it is written on paper:

    statement balance
      + deposits in transit    (in our books, not yet on the statement)
      − unpresented payments   (paid by us, not yet cleared)
      = the books

A reconciliation that "balances" by adjusting the books to match the bank is
not a reconciliation, so nothing here writes to the ledger. It reports the
difference and leaves correcting it to a journal somebody posts on purpose.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.accounting.models import (
    BankAccount,
    BankReconciliation,
    BankTransaction,
    GeneralLedger,
    Journal,
)

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

# How far apart a statement line and a journal may be and still be the same
# event. Cheques and transfers routinely clear a few days after posting.
MATCH_WINDOW_DAYS = 5


def get_account(db: Session, bank_account_id: uuid.UUID) -> BankAccount:
    account = db.get(BankAccount, bank_account_id)
    if account is None:
        raise NotFoundError("Bank account not found")
    return account


def book_balance(db: Session, account: BankAccount, as_at: date) -> Decimal:
    """What the ledger says this account holds, from the ledger rows rather
    than the cached figure on the account."""
    row = db.execute(
        select(
            func.coalesce(func.sum(GeneralLedger.debit), 0),
            func.coalesce(func.sum(GeneralLedger.credit), 0),
        ).where(
            GeneralLedger.account_id == account.gl_account_id,
            GeneralLedger.entry_date <= as_at,
        )
    ).one()
    return (Decimal(account.opening_balance) + Decimal(row[0]) - Decimal(row[1])).quantize(CENT)


def unmatched_statement_lines(
    db: Session, bank_account_id: uuid.UUID, as_at: date | None = None
) -> list[BankTransaction]:
    """On the statement, not yet tied to anything in our books."""
    stmt = select(BankTransaction).where(
        BankTransaction.bank_account_id == bank_account_id,
        BankTransaction.matched_journal_id.is_(None),
    )
    if as_at:
        stmt = stmt.where(BankTransaction.transaction_date <= as_at)
    return list(db.scalars(stmt.order_by(BankTransaction.transaction_date)))


def unmatched_book_entries(
    db: Session, account: BankAccount, as_at: date | None = None
) -> list[GeneralLedger]:
    """In our books, not yet seen on a statement.

    These are the deposits in transit and the unpresented payments — the two
    halves of the gap, and the only legitimate reasons for one.
    """
    matched = select(BankTransaction.matched_journal_id).where(
        BankTransaction.bank_account_id == account.id,
        BankTransaction.matched_journal_id.is_not(None),
    )
    stmt = select(GeneralLedger).where(
        GeneralLedger.account_id == account.gl_account_id,
        GeneralLedger.journal_id.notin_(matched),
    )
    if as_at:
        stmt = stmt.where(GeneralLedger.entry_date <= as_at)
    return list(db.scalars(stmt.order_by(GeneralLedger.entry_date)))


def summary(
    db: Session,
    bank_account_id: uuid.UUID,
    as_at: date,
    statement_balance: Decimal | None = None,
) -> dict:
    """The reconciliation, laid out the way it is written on paper."""
    account = get_account(db, bank_account_id)
    books = book_balance(db, account, as_at)
    outstanding = unmatched_book_entries(db, account, as_at)

    deposits = sum(
        (Decimal(row.debit) for row in outstanding if row.debit), ZERO
    ).quantize(CENT)
    payments = sum(
        (Decimal(row.credit) for row in outstanding if row.credit), ZERO
    ).quantize(CENT)

    statement = (
        Decimal(statement_balance).quantize(CENT)
        if statement_balance is not None
        else _statement_balance(db, account, as_at)
    )
    # statement + in transit − unpresented should be the books. Whatever is
    # left over is the bit nobody has explained yet.
    expected_books = (statement + deposits - payments).quantize(CENT)
    difference = (books - expected_books).quantize(CENT)

    return {
        "bank_account_id": account.id,
        "name": account.name,
        "currency": account.currency,
        "as_at": as_at,
        "statement_balance": statement,
        "book_balance": books,
        "deposits_in_transit": deposits,
        "unpresented_payments": payments,
        "expected_book_balance": expected_books,
        "difference": difference,
        "reconciled": difference == 0,
        "unmatched_statement_lines": unmatched_statement_lines(db, account.id, as_at),
        "unmatched_book_entries": outstanding,
    }


def _statement_balance(db: Session, account: BankAccount, as_at: date) -> Decimal:
    """Falls back to the sum of the imported lines when no closing figure was
    typed in, so the screen is useful before anyone keys the statement total."""
    total = db.scalar(
        select(func.coalesce(func.sum(BankTransaction.amount), 0)).where(
            BankTransaction.bank_account_id == account.id,
            BankTransaction.transaction_date <= as_at,
        )
    ) or ZERO
    return (Decimal(account.opening_balance) + Decimal(total)).quantize(CENT)


def suggest_matches(db: Session, bank_account_id: uuid.UUID) -> list[dict]:
    """Statement lines paired with the journal that probably caused them.

    Suggests rather than decides: matching on amount and a few days' proximity
    is right often enough to save the work and wrong often enough that it must
    not post itself.
    """
    account = get_account(db, bank_account_id)
    lines = unmatched_statement_lines(db, bank_account_id)
    candidates = unmatched_book_entries(db, account)

    used: set[uuid.UUID] = set()
    out: list[dict] = []
    for line in lines:
        amount = Decimal(line.amount).quantize(CENT)
        for entry in candidates:
            if entry.journal_id in used:
                continue
            # A debit in the ledger is money in, which is a positive statement
            # line; a credit is money out.
            entry_amount = (Decimal(entry.debit) - Decimal(entry.credit)).quantize(CENT)
            if entry_amount != amount:
                continue
            if abs((entry.entry_date - line.transaction_date).days) > MATCH_WINDOW_DAYS:
                continue
            used.add(entry.journal_id)
            out.append(
                {
                    "bank_transaction_id": line.id,
                    "journal_id": entry.journal_id,
                    "doc_number": entry.doc_number,
                    "amount": amount,
                    "statement_date": line.transaction_date,
                    "book_date": entry.entry_date,
                    "days_apart": abs((entry.entry_date - line.transaction_date).days),
                    "description": entry.description,
                }
            )
            break
    return out


def match(db: Session, transaction_id: uuid.UUID, journal_id: uuid.UUID) -> BankTransaction:
    line = db.get(BankTransaction, transaction_id)
    if line is None:
        raise NotFoundError("Statement line not found")
    if line.matched_journal_id is not None:
        raise ConflictError("That statement line is already matched")
    journal = db.get(Journal, journal_id)
    if journal is None:
        raise NotFoundError("Journal not found")

    account = get_account(db, line.bank_account_id)
    touches_bank = db.scalar(
        select(GeneralLedger).where(
            GeneralLedger.journal_id == journal_id,
            GeneralLedger.account_id == account.gl_account_id,
        )
    )
    if touches_bank is None:
        # Matching a statement line to a journal that never touched this bank
        # account would explain nothing and quietly hide the real difference.
        raise ValidationFailedError(
            f"{journal.doc_number} does not move {account.name}"
        )
    line.matched_journal_id = journal_id
    line.matched_at = datetime.now(timezone.utc)
    db.flush()
    return line


def unmatch(db: Session, transaction_id: uuid.UUID) -> BankTransaction:
    line = db.get(BankTransaction, transaction_id)
    if line is None:
        raise NotFoundError("Statement line not found")
    line.matched_journal_id = None
    line.matched_at = None
    db.flush()
    return line


def complete(
    db: Session,
    bank_account_id: uuid.UUID,
    as_at: date,
    statement_balance: Decimal,
    user=None,
    notes: str | None = None,
) -> BankReconciliation:
    """Signs off the statement, and refuses to if it does not balance.

    A reconciliation you can complete while it is still out is a box-ticking
    exercise: the whole value is that finishing it means something.
    """
    result = summary(db, bank_account_id, as_at, statement_balance)
    if not result["reconciled"]:
        raise ConflictError(
            f"{result['difference']} is still unexplained; match the remaining items first"
        )

    existing = db.scalar(
        select(BankReconciliation).where(
            BankReconciliation.bank_account_id == bank_account_id,
            BankReconciliation.statement_date == as_at,
        )
    )
    if existing is not None and existing.is_complete:
        raise ConflictError("This statement date has already been reconciled")

    record = existing or BankReconciliation(
        bank_account_id=bank_account_id, statement_date=as_at
    )
    record.statement_balance = result["statement_balance"]
    record.book_balance = result["book_balance"]
    record.deposits_in_transit = result["deposits_in_transit"]
    record.unpresented_payments = result["unpresented_payments"]
    record.difference = result["difference"]
    record.is_complete = True
    record.completed_at = datetime.now(timezone.utc)
    record.notes = notes
    record.created_by = getattr(user, "id", None)
    db.add(record)
    db.flush()
    return record


def import_lines(db: Session, bank_account_id: uuid.UUID, rows: list) -> int:
    """Takes statement lines in, skipping ones already there.

    Re-importing an overlapping statement is normal, so a line that matches an
    existing date, amount and reference is treated as the same line rather
    than a second one.
    """
    get_account(db, bank_account_id)
    added = 0
    for row in rows:
        duplicate = db.scalar(
            select(BankTransaction).where(
                BankTransaction.bank_account_id == bank_account_id,
                BankTransaction.transaction_date == row.transaction_date,
                BankTransaction.amount == row.amount,
                BankTransaction.reference == row.reference,
            )
        )
        if duplicate is not None:
            continue
        db.add(
            BankTransaction(
                bank_account_id=bank_account_id,
                transaction_date=row.transaction_date,
                description=row.description,
                reference=row.reference,
                amount=row.amount,
            )
        )
        added += 1
    db.flush()
    return added


def recent_window(as_at: date) -> tuple[date, date]:
    return as_at - timedelta(days=90), as_at
