"""Per-party ledgers under a control account.

The general ledger says the company is owed 558,000. This says which client
owes which part, and lets you hand one of them a statement.

The whole thing rests on one invariant: **the sum of the pockets under a
control equals the control's balance**. It holds because a pocket never moves
on its own — every movement is mirrored from a journal line that moved the
control in the same journal, in the same transaction. `reconcile` exists to
prove it rather than to assume it.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.modules.accounting import service as ledger
from app.modules.accounting.models import (
    Account,
    SubsidiaryAccount,
    SubsidiaryEntry,
)

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

# Which control account each kind of party rolls into.
CONTROL_BY_ENTITY = {
    "client": ledger.ACCOUNTS_RECEIVABLE,
    "supplier": ledger.ACCOUNTS_PAYABLE,
}

_PREFIX = {"client": "CL", "supplier": "SU"}


def pocket_for(
    db: Session, entity_type: str, entity_id: uuid.UUID, currency: str | None = None
) -> SubsidiaryAccount:
    """The party's ledger, created on first use.

    Created lazily rather than up front: a supplier who has never been
    transacted with does not need a ledger, and one that exists but has never
    moved is noise on every report that lists them.
    """
    if entity_type not in CONTROL_BY_ENTITY:
        raise ValidationFailedError(f"There is no subsidiary ledger for '{entity_type}'")

    control = ledger.account_by_code(db, CONTROL_BY_ENTITY[entity_type])
    currency = currency or control.currency

    existing = db.scalar(
        select(SubsidiaryAccount).where(
            SubsidiaryAccount.entity_type == entity_type,
            SubsidiaryAccount.entity_id == entity_id,
            SubsidiaryAccount.currency == currency,
        )
    )
    if existing is not None:
        return existing

    name = _party_name(db, entity_type, entity_id)
    count = (
        db.scalar(
            select(func.count()).select_from(SubsidiaryAccount).where(
                SubsidiaryAccount.entity_type == entity_type
            )
        )
        or 0
    )
    pocket = SubsidiaryAccount(
        code=f"{_PREFIX[entity_type]}/{count + 1:05d}",
        name=name,
        entity_type=entity_type,
        entity_id=entity_id,
        currency=currency,
        control_account_id=control.id,
    )
    db.add(pocket)
    db.flush()
    return pocket


def _party_name(db: Session, entity_type: str, entity_id: uuid.UUID) -> str:
    if entity_type == "client":
        from app.modules.clients.models import Client

        party = db.get(Client, entity_id)
    else:
        from app.modules.procurement.models import Supplier

        party = db.get(Supplier, entity_id)
    if party is None:
        raise NotFoundError(f"That {entity_type} does not exist")
    return party.name


def mirror(db: Session, journal, lines, accounts: dict) -> None:
    """Writes each pocket's side of a posted journal.

    Called from inside post(), after the control account has moved and in the
    same transaction, which is what keeps the two in step. A line with no
    pocket is ordinary and simply has no mirror.
    """
    for line in lines:
        if line.subsidiary_id is None:
            continue
        pocket = db.get(SubsidiaryAccount, line.subsidiary_id)
        if pocket is None:
            raise NotFoundError("Subsidiary account not found")
        if pocket.control_account_id != line.account_id:
            # Otherwise the pocket and its control would drift apart silently,
            # which is precisely the failure this design exists to prevent.
            raise ValidationFailedError(
                f"{pocket.code} sits under {accounts[pocket.control_account_id].code if pocket.control_account_id in accounts else 'another account'}, "
                f"so it cannot carry a line posted to {accounts[line.account_id].code}"
            )

        control = accounts[line.account_id]
        movement = (
            line.debit - line.credit
            if control.normal_balance == "debit"
            else line.credit - line.debit
        )
        pocket.balance = (Decimal(pocket.balance) + movement).quantize(CENT)
        db.add(
            SubsidiaryEntry(
                subsidiary_id=pocket.id,
                journal_id=journal.id,
                journal_line_id=line.id,
                entry_date=journal.journal_date,
                doc_number=journal.doc_number,
                description=line.description or journal.memo,
                debit=line.debit,
                credit=line.credit,
                balance_after=pocket.balance,
                project_id=journal.project_id,
            )
        )


def statement(
    db: Session,
    subsidiary_id: uuid.UUID,
    start: date | None = None,
    end: date | None = None,
) -> dict:
    """One party's account, as you would send it to them.

    Carries the opening balance so the running total on the page is the real
    one rather than starting from zero mid-relationship.
    """
    pocket = db.get(SubsidiaryAccount, subsidiary_id)
    if pocket is None:
        raise NotFoundError("Subsidiary account not found")

    opening = ZERO
    if start is not None:
        rows = db.execute(
            select(
                func.coalesce(func.sum(SubsidiaryEntry.debit), 0),
                func.coalesce(func.sum(SubsidiaryEntry.credit), 0),
            ).where(
                SubsidiaryEntry.subsidiary_id == subsidiary_id,
                SubsidiaryEntry.entry_date < start,
            )
        ).one()
        control = db.get(Account, pocket.control_account_id)
        opening = (
            Decimal(rows[0]) - Decimal(rows[1])
            if control.normal_balance == "debit"
            else Decimal(rows[1]) - Decimal(rows[0])
        ).quantize(CENT)

    stmt = select(SubsidiaryEntry).where(SubsidiaryEntry.subsidiary_id == subsidiary_id)
    if start is not None:
        stmt = stmt.where(SubsidiaryEntry.entry_date >= start)
    if end is not None:
        stmt = stmt.where(SubsidiaryEntry.entry_date <= end)
    entries = list(db.scalars(stmt.order_by(SubsidiaryEntry.entry_date, SubsidiaryEntry.created_at)))

    return {
        "subsidiary_id": pocket.id,
        "code": pocket.code,
        "name": pocket.name,
        "entity_type": pocket.entity_type,
        "currency": pocket.currency,
        "opening_balance": opening,
        "closing_balance": Decimal(pocket.balance).quantize(CENT),
        "entries": entries,
    }


def list_pockets(db: Session, entity_type: str | None = None) -> list[SubsidiaryAccount]:
    stmt = select(SubsidiaryAccount).order_by(SubsidiaryAccount.code)
    if entity_type:
        stmt = stmt.where(SubsidiaryAccount.entity_type == entity_type)
    return list(db.scalars(stmt))


def reconcile(db: Session) -> list[dict]:
    """Proves the invariant instead of assuming it.

    For each control account, the sum of its pockets against its own balance.
    A difference means posting has written one without the other, and every
    ageing built on the subsidiary ledger is wrong until it is explained.
    """
    out: list[dict] = []
    control_ids = set(
        db.scalars(select(SubsidiaryAccount.control_account_id).distinct())
    )
    for control_id in control_ids:
        control = db.get(Account, control_id)
        total = db.scalar(
            select(func.coalesce(func.sum(SubsidiaryAccount.balance), 0)).where(
                SubsidiaryAccount.control_account_id == control_id
            )
        ) or ZERO
        control_balance = Decimal(control.balance).quantize(CENT)
        pockets_total = Decimal(total).quantize(CENT)
        out.append(
            {
                "control_code": control.code,
                "control_name": control.name,
                "control_balance": control_balance,
                "subsidiary_total": pockets_total,
                "difference": (control_balance - pockets_total).quantize(CENT),
                "in_agreement": control_balance == pockets_total,
            }
        )
    return sorted(out, key=lambda row: row["control_code"])
