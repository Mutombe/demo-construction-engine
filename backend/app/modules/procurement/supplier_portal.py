"""A door suppliers can use themselves.

Everything a supplier currently needs has to be asked for and typed in by
somebody here: where their order stands, what they have been paid, whether
their tax clearance is still on file. That work is real and it is all
avoidable, so this is the same idea as the client portal — a link, no
password, scoped to one supplier and revocable.

The load-bearing decision is what happens when they submit an invoice.
Receiving a purchase order **already** creates the payable, so an invoice must
never post again: it is a claim to be matched against what was actually
received. That is the third leg of a three-way match, and the variance it
exposes — invoiced against received — is the only thing that catches
overbilling before it is paid.
"""

import hashlib
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.doc_numbers import next_doc_number
from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.procurement.models import (
    PurchaseOrder,
    Supplier,
    SupplierAccessToken,
    SupplierInvoice,
)

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

# What counts as close enough. Suppliers round, freight gets added, and a
# system that queries three cents of difference is a system people stop
# reading.
MATCH_TOLERANCE = Decimal("1.00")


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def portal_url(raw_token: str) -> str:
    origin = settings.cors_origins[0] if settings.cors_origins else ""
    return f"{origin}/supplier/{raw_token}"


def issue_token(db: Session, supplier_id: uuid.UUID, label: str | None, days: int, user=None):
    """Mint a link for one supplier.

    The raw token is returned once and never stored: only its hash is kept, so
    a leaked database does not hand somebody every supplier's orders.
    """
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise NotFoundError("Supplier not found")

    raw = secrets.token_urlsafe(32)
    token = SupplierAccessToken(
        supplier_id=supplier_id,
        token_hash=_hash(raw),
        label=label or supplier.name,
        expires_at=datetime.now(timezone.utc) + timedelta(days=days),
        created_by=getattr(user, "id", None),
    )
    db.add(token)
    db.flush()
    return token, raw


def revoke_token(db: Session, token_id: uuid.UUID):
    token = db.get(SupplierAccessToken, token_id)
    if token is None:
        raise NotFoundError("Link not found")
    token.revoked_at = datetime.now(timezone.utc)
    db.flush()
    return token


def list_tokens(db: Session, supplier_id: uuid.UUID):
    return list(
        db.scalars(
            select(SupplierAccessToken)
            .where(SupplierAccessToken.supplier_id == supplier_id)
            .order_by(SupplierAccessToken.created_at.desc())
        )
    )


def resolve(db: Session, raw_token: str) -> SupplierAccessToken:
    """Find the supplier behind a link, or refuse in the same way for every
    reason it might fail.

    Expired, revoked and never-existed all answer the same, so the link cannot
    be used to work out which suppliers exist.
    """
    token = db.scalar(
        select(SupplierAccessToken).where(SupplierAccessToken.token_hash == _hash(raw_token))
    )
    now = datetime.now(timezone.utc)
    if (
        token is None
        or token.revoked_at is not None
        or (token.expires_at is not None and token.expires_at < now)
    ):
        raise NotFoundError("This link is not valid")
    token.last_used_at = now
    return token


# --- What the supplier sees --------------------------------------------------


def overview(db: Session, token: SupplierAccessToken) -> dict:
    from app.modules.subcontracts import service as subcontracts

    supplier = db.get(Supplier, token.supplier_id)
    orders = list(
        db.scalars(
            select(PurchaseOrder)
            .where(PurchaseOrder.supplier_id == token.supplier_id)
            .order_by(PurchaseOrder.order_date.desc())
            .limit(50)
        )
    )
    invoices = list(
        db.scalars(
            select(SupplierInvoice)
            .where(SupplierInvoice.supplier_id == token.supplier_id)
            .order_by(SupplierInvoice.invoice_date.desc())
            .limit(50)
        )
    )

    compliance = subcontracts.compliance_status(db, token.supplier_id)
    return {
        "supplier_name": supplier.name if supplier else "",
        "company_name": _company_name(db),
        "is_compliant": compliance["is_compliant"],
        # Named so they can fix it themselves, which is the entire point of
        # showing it to them rather than ringing them about it.
        "missing_documents": compliance["blocking"],
        "orders": [
            {
                "id": order.id,
                "doc_number": order.doc_number,
                "order_date": order.order_date,
                "status": order.status.value,
                "total_amount": Decimal(order.total_amount or 0),
            }
            for order in orders
        ],
        "invoices": [
            {
                "id": invoice.id,
                "doc_number": invoice.doc_number,
                "reference": invoice.reference,
                "invoice_date": invoice.invoice_date,
                "amount": Decimal(invoice.amount),
                "status": invoice.status,
                "variance": Decimal(invoice.variance or 0),
                "note": invoice.decision_note,
            }
            for invoice in invoices
        ],
    }


def _company_name(db: Session) -> str:
    from app.modules.company.models import CompanySettings

    company = db.scalar(select(CompanySettings).limit(1))
    return company.name if company else "Company Name Not Set"


def submit_invoice(db: Session, token: SupplierAccessToken, data) -> SupplierInvoice:
    """A supplier's claim against an order.

    Never posts. The payable was created when the goods were received, and
    booking the invoice as well would owe the supplier twice for one delivery.
    What this does is record the claim and measure it against what was
    actually received, so a difference is visible before anybody pays it.
    """
    amount = Decimal(data.amount)
    if amount <= 0:
        raise ValidationFailedError("An invoice has to be for something")

    order = None
    if data.purchase_order_id is not None:
        order = db.get(PurchaseOrder, data.purchase_order_id)
        if order is None or order.supplier_id != token.supplier_id:
            # Deliberately the same answer as an order that does not exist:
            # the portal must not confirm other people's order numbers.
            raise NotFoundError("That order is not on this account")

    reference = (data.reference or "").strip()
    if reference:
        clash = db.scalar(
            select(SupplierInvoice).where(
                SupplierInvoice.supplier_id == token.supplier_id,
                SupplierInvoice.reference == reference,
            )
        )
        if clash is not None:
            raise ConflictError(
                f"Invoice {reference} has already been submitted on this account"
            )

    variance = ZERO
    if order is not None:
        variance = (amount - Decimal(order.total_amount or 0)).quantize(CENT)

    invoice = SupplierInvoice(
        doc_number=next_doc_number(db, SupplierInvoice, "SINV"),
        supplier_id=token.supplier_id,
        purchase_order_id=order.id if order else None,
        reference=reference or None,
        invoice_date=data.invoice_date or date.today(),
        amount=amount,
        variance=variance,
        status="submitted",
        notes=data.notes,
    )
    db.add(invoice)
    db.flush()
    _notify_procurement(db, invoice, order)
    return invoice


def _notify_procurement(db: Session, invoice: SupplierInvoice, order) -> None:
    from app.common.enums import UserRole
    from app.modules.notifications import service as notifications
    from app.modules.users.models import User

    recipients = {
        user.id
        for user in db.scalars(
            select(User).where(
                User.role.in_([UserRole.procurement_officer, UserRole.admin]),
                User.is_active.is_(True),
            )
        )
    }
    if not recipients:
        return

    supplier = db.get(Supplier, invoice.supplier_id)
    title = f"{supplier.name if supplier else 'A supplier'} submitted an invoice"
    body = f"{invoice.doc_number} for {invoice.amount}"
    if order is not None and abs(Decimal(invoice.variance or 0)) > MATCH_TOLERANCE:
        body += f", which is {invoice.variance} against {order.doc_number}"
    notifications.notify(
        db,
        recipients,
        type="supplier_invoice",
        title=title,
        body=body,
        link="/procurement/invoices",
    )


# --- What procurement does with it -------------------------------------------


def list_invoices(db: Session, status: str | None = None, supplier_id=None):
    stmt = select(SupplierInvoice).order_by(SupplierInvoice.invoice_date.desc())
    if status:
        stmt = stmt.where(SupplierInvoice.status == status)
    if supplier_id:
        stmt = stmt.where(SupplierInvoice.supplier_id == supplier_id)
    return stmt


def decide_invoice(db: Session, invoice_id: uuid.UUID, accept: bool, note: str | None, user=None):
    """Accept or query a supplier's claim.

    Accepting records their reference against the order so a payment can be
    matched to it later. It posts nothing, because the receipt already did.
    """
    invoice = db.get(SupplierInvoice, invoice_id)
    if invoice is None:
        raise NotFoundError("Invoice not found")
    if invoice.status != "submitted":
        raise ConflictError(f"That invoice has already been {invoice.status}")
    if not accept and not (note or "").strip():
        raise ValidationFailedError(
            "Say what is wrong with it. A query with no reason gets resubmitted unchanged."
        )

    invoice.status = "accepted" if accept else "queried"
    invoice.decision_note = note
    invoice.decided_at = datetime.now(timezone.utc)
    invoice.decided_by = getattr(user, "id", None)
    db.flush()
    return invoice


def matching_report(db: Session):
    """Invoices whose value does not agree with the order they are against.

    The whole reason a supplier portal is worth having: a claim that does not
    match what was received is caught here rather than after it is paid.
    """
    rows = []
    for invoice in db.scalars(
        select(SupplierInvoice).where(SupplierInvoice.status == "submitted")
    ):
        if invoice.purchase_order_id is None:
            rows.append(
                {
                    "invoice_id": invoice.id,
                    "doc_number": invoice.doc_number,
                    "reference": invoice.reference,
                    "amount": Decimal(invoice.amount),
                    "order_number": None,
                    "ordered": None,
                    "variance": None,
                    # Not a mismatch — there is nothing to match it against,
                    # which is a different problem and needs saying differently.
                    "issue": "No order given",
                }
            )
            continue
        if abs(Decimal(invoice.variance or 0)) <= MATCH_TOLERANCE:
            continue
        order = db.get(PurchaseOrder, invoice.purchase_order_id)
        rows.append(
            {
                "invoice_id": invoice.id,
                "doc_number": invoice.doc_number,
                "reference": invoice.reference,
                "amount": Decimal(invoice.amount),
                "order_number": order.doc_number if order else None,
                "ordered": Decimal(order.total_amount or 0) if order else None,
                "variance": Decimal(invoice.variance or 0),
                "issue": "Over the order"
                if Decimal(invoice.variance) > 0
                else "Under the order",
            }
        )
    rows.sort(key=lambda r: abs(r["variance"] or 0), reverse=True)
    return rows
