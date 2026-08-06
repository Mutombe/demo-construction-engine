"""Settling what is owed, and seeing how old it is.

Ageing is only meaningful if something clears the balance. Before this,
receivables cleared on the valuation's own status but never in the ledger, and
payables never cleared at all — a received purchase order sat in Accounts
Payable forever, so an ageing report would have shown every order ever placed
as permanently overdue.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.doc_numbers import next_doc_number
from app.common.enums import JournalSource, PoStatus, ValuationStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.accounting import service as ledger
from app.modules.accounting import subsidiary
from app.modules.accounting.models import PaymentAllocation, SupplierPayment

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

# The buckets a credit controller actually chases in. 30 days is the usual
# term, so anything past it is a conversation and past 90 is a problem.
BUCKETS = ((0, 30, "Current"), (31, 60, "31 to 60 days"), (61, 90, "61 to 90 days"))
OVERDUE_LABEL = "Over 90 days"


def _bucket(days: int) -> str:
    for low, high, label in BUCKETS:
        if low <= days <= high:
            return label
    return OVERDUE_LABEL


def _empty_buckets() -> dict[str, Decimal]:
    return {label: ZERO for *_, label in BUCKETS} | {OVERDUE_LABEL: ZERO}


# --- Payables ----------------------------------------------------------------


def po_outstanding(db: Session, po_ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    """How much of each order is still unpaid, in one query."""
    if not po_ids:
        return {}
    rows = db.execute(
        select(PaymentAllocation.purchase_order_id, func.coalesce(func.sum(PaymentAllocation.amount), 0))
        .where(PaymentAllocation.purchase_order_id.in_(po_ids))
        .group_by(PaymentAllocation.purchase_order_id)
    ).all()
    return {row[0]: Decimal(row[1]) for row in rows}


def create_payment(db: Session, data, user=None) -> SupplierPayment:
    """Pays one or more received orders.

    Allocations must add up to the payment: money that arrives with no invoice
    attached to it is a real thing, but it is a credit on account rather than a
    payment, and pretending otherwise makes both the ageing and the ledger
    wrong.
    """
    from app.modules.procurement.models import PurchaseOrder, Supplier

    supplier = db.get(Supplier, data.supplier_id)
    if supplier is None:
        raise NotFoundError("Supplier not found")

    amount = Decimal(data.amount).quantize(CENT)
    if amount <= 0:
        raise ValidationFailedError("A payment has to be for something")

    allocated = sum((Decimal(line.amount) for line in data.allocations), ZERO).quantize(CENT)
    if allocated != amount:
        raise ValidationFailedError(
            f"Allocations come to {allocated} but the payment is {amount}"
        )

    payment = SupplierPayment(
        doc_number=next_doc_number(db, SupplierPayment, "PAY"),
        supplier_id=data.supplier_id,
        payment_date=data.payment_date or date.today(),
        amount=amount,
        method=data.method,
        reference=data.reference,
        notes=data.notes,
        created_by=getattr(user, "id", None),
    )
    db.add(payment)
    db.flush()

    already = po_outstanding(db, [line.purchase_order_id for line in data.allocations])
    for line in data.allocations:
        po = db.get(PurchaseOrder, line.purchase_order_id)
        if po is None:
            raise NotFoundError("Purchase order not found")
        if po.supplier_id != data.supplier_id:
            raise ValidationFailedError(f"{po.doc_number} belongs to a different supplier")
        if po.status is not PoStatus.received:
            raise ConflictError(
                f"{po.doc_number} has not been received, so there is nothing to pay yet"
            )
        line_amount = Decimal(line.amount).quantize(CENT)
        if line_amount <= 0:
            raise ValidationFailedError("An allocation has to be for something")
        remaining = (Decimal(po.total_amount) - already.get(po.id, ZERO)).quantize(CENT)
        if line_amount > remaining:
            raise ValidationFailedError(
                f"{po.doc_number} has {remaining} outstanding, cannot allocate {line_amount}"
            )
        db.add(
            PaymentAllocation(
                payment_id=payment.id, purchase_order_id=po.id, amount=line_amount
            )
        )
    db.flush()

    journal = ledger.create_journal(
        db,
        journal_date=payment.payment_date,
        memo=f"{payment.doc_number} paid to {supplier.name}",
        source=JournalSource.manual,
        source_id=payment.id,
        created_by=getattr(user, "id", None),
        lines=[
            {
                "account_code": ledger.ACCOUNTS_PAYABLE,
                "debit": amount,
                "subsidiary_id": subsidiary.pocket_for(db, "supplier", data.supplier_id).id,
            },
            {"account_code": ledger.BANK, "credit": amount},
        ],
    )
    ledger.post(db, journal.id, user)
    payment.journal_id = journal.id
    db.flush()
    return payment


def list_payments(db: Session, supplier_id: uuid.UUID | None = None) -> list[SupplierPayment]:
    stmt = select(SupplierPayment).order_by(SupplierPayment.payment_date.desc())
    if supplier_id:
        stmt = stmt.where(SupplierPayment.supplier_id == supplier_id)
    return list(db.scalars(stmt))


def payables_ageing(db: Session, as_at: date | None = None) -> dict:
    """What is owed to each supplier, by how long it has been owed.

    Aged from the date the goods were received, which is when the debt became
    real — the order date would age something that has not been delivered.
    """
    from app.modules.procurement.models import PurchaseOrder, Supplier

    as_at = as_at or date.today()
    rows = db.execute(
        select(PurchaseOrder, Supplier.name)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .where(PurchaseOrder.status == PoStatus.received)
        .order_by(PurchaseOrder.received_date)
    ).all()
    paid = po_outstanding(db, [po.id for po, _ in rows])

    by_supplier: dict[uuid.UUID, dict] = {}
    totals = _empty_buckets()
    grand = ZERO
    for po, supplier_name in rows:
        outstanding = (Decimal(po.total_amount) - paid.get(po.id, ZERO)).quantize(CENT)
        if outstanding <= 0:
            continue
        since = po.received_date or po.order_date
        days = (as_at - since).days
        bucket = _bucket(days)
        entry = by_supplier.setdefault(
            po.supplier_id,
            {
                # Same keys as the receivables side: one shape, one component,
                # one schema for both halves of the ageing screen.
                "party_id": po.supplier_id,
                "party_name": supplier_name,
                "total": ZERO,
                "buckets": _empty_buckets(),
                "documents": [],
            },
        )
        entry["total"] += outstanding
        entry["buckets"][bucket] += outstanding
        entry["documents"].append(
            {
                "id": po.id,
                "doc_number": po.doc_number,
                "dated": since,
                "days": days,
                "bucket": bucket,
                "amount": Decimal(po.total_amount).quantize(CENT),
                "outstanding": outstanding,
            }
        )
        totals[bucket] += outstanding
        grand += outstanding

    parties = sorted(by_supplier.values(), key=lambda p: -p["total"])
    return {
        "as_at": as_at,
        "parties": parties,
        "buckets": totals,
        "total": grand,
    }


# --- Receivables -------------------------------------------------------------


def receivables_ageing(db: Session, as_at: date | None = None) -> dict:
    """What clients owe, aged from the date the certificate was issued.

    Retention is excluded on purpose: it is not overdue, it is withheld by
    agreement until the defects period ends, and ageing it would show every
    finished job as a debt problem.
    """
    from app.modules.clients.models import Client
    from app.modules.projects.models import Project
    from app.modules.valuations.models import Valuation

    as_at = as_at or date.today()
    rows = db.execute(
        select(Valuation, Client.id, Client.name)
        .join(Project, Project.id == Valuation.project_id)
        .join(Client, Client.id == Project.client_id)
        .where(Valuation.status == ValuationStatus.issued)
        .order_by(Valuation.issued_date)
    ).all()

    by_client: dict[uuid.UUID, dict] = {}
    totals = _empty_buckets()
    grand = ZERO
    for valuation, client_id, client_name in rows:
        outstanding = Decimal(valuation.net_certified).quantize(CENT)
        if outstanding <= 0:
            continue
        since = valuation.issued_date or valuation.period_end
        days = (as_at - since).days
        bucket = _bucket(days)
        entry = by_client.setdefault(
            client_id,
            {
                "party_id": client_id,
                "party_name": client_name,
                "total": ZERO,
                "buckets": _empty_buckets(),
                "documents": [],
            },
        )
        entry["total"] += outstanding
        entry["buckets"][bucket] += outstanding
        entry["documents"].append(
            {
                "id": valuation.id,
                "doc_number": valuation.doc_number,
                "dated": since,
                "days": days,
                "bucket": bucket,
                "amount": outstanding,
                "outstanding": outstanding,
            }
        )
        totals[bucket] += outstanding
        grand += outstanding

    parties = sorted(by_client.values(), key=lambda p: -p["total"])
    return {"as_at": as_at, "parties": parties, "buckets": totals, "total": grand}


def post_valuation_receipt(db: Session, valuation, user=None):
    """Marking a certificate paid has to move the money in the books too.

    Without this the receivable balance only ever grew: the certificate debited
    Accounts Receivable when issued and nothing ever credited it back.
    """
    try:
        ledger.ensure_chart(db)
        amount = Decimal(valuation.net_certified).quantize(CENT)
        if amount <= 0:
            return None
        journal = ledger.create_journal(
            db,
            journal_date=valuation.paid_date or date.today(),
            memo=f"{valuation.doc_number} received from client",
            source=JournalSource.valuation,
            source_id=valuation.id,
            project_id=valuation.project_id,
            created_by=getattr(user, "id", None),
            lines=[
                {"account_code": ledger.BANK, "debit": amount},
                {
                    "account_code": ledger.ACCOUNTS_RECEIVABLE,
                    "credit": amount,
                    "subsidiary_id": _client_pocket(db, valuation),
                },
            ],
        )
        return ledger.post(db, journal.id, user)
    except Exception:
        ledger.logger.exception(
            "Could not post the receipt for valuation %s", valuation.id
        )
        return None


def _client_pocket(db: Session, valuation):
    """The pocket for whoever the certificate was issued to."""
    from app.modules.accounting import subsidiary
    from app.modules.projects.models import Project

    project = db.get(Project, valuation.project_id)
    if project is None or project.client_id is None:
        return None
    return subsidiary.pocket_for(db, "client", project.client_id).id
