"""The supplier's side of an RFQ.

Until now an RFQ could be drafted and issued but never actually sent: someone
had to email it and key the reply back in. This is the missing half — a link
per supplier, and a form that writes the quote straight into the comparison.

Security is the same shape as the client portal, because the situation is the
same: an outsider holding an opaque token, not a staff user. The token is
scoped to one (rfq, supplier) pair, so a supplier reaches exactly one RFQ and
never sees what anyone else quoted.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import QuoteStatus, RfqStatus
from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationFailedError,
)
from app.core.deps import DbDep
from app.modules.procurement.models import (
    Quote,
    QuoteItem,
    Rfq,
    RfqInvite,
    RfqItem,
    Supplier,
)

DEFAULT_VALID_DAYS = 21


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def invite_url(raw_token: str) -> str:
    origin = settings.cors_origins[0] if settings.cors_origins else ""
    return f"{origin}/rfq/{raw_token}"


# --- Staff side --------------------------------------------------------------


def send_rfq(
    db: Session,
    rfq_id: uuid.UUID,
    supplier_ids: list[uuid.UUID],
    expires_in_days: int,
    user_id: uuid.UUID | None = None,
) -> list[tuple[RfqInvite, str]]:
    """One link per supplier, each shown exactly once.

    Only an issued RFQ can go out: sending a draft would invite pricing against
    something still being edited.
    """
    rfq = db.get(Rfq, rfq_id)
    if rfq is None:
        raise NotFoundError("RFQ not found")
    if rfq.status is RfqStatus.draft:
        raise ConflictError("Issue the RFQ before sending it to suppliers")
    if not supplier_ids:
        raise ValidationFailedError("Choose at least one supplier")

    issued: list[tuple[RfqInvite, str]] = []
    for supplier_id in dict.fromkeys(supplier_ids):
        supplier = db.get(Supplier, supplier_id)
        if supplier is None:
            raise NotFoundError("Supplier not found")

        existing = db.scalar(
            select(RfqInvite).where(
                RfqInvite.rfq_id == rfq_id, RfqInvite.supplier_id == supplier_id
            )
        )
        raw = secrets.token_urlsafe(32)
        if existing is not None:
            if existing.responded_at is not None:
                # Re-sending after a reply would let them quietly replace a
                # quote that has already been compared against others.
                raise ConflictError(f"{supplier.name} has already responded")
            # Re-sending reissues the link and invalidates the old one.
            existing.token_hash = _hash(raw)
            existing.expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)
            existing.revoked_at = None
            existing.sent_at = datetime.now(UTC)
            invite = existing
        else:
            invite = RfqInvite(
                rfq_id=rfq_id,
                supplier_id=supplier_id,
                token_hash=_hash(raw),
                expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
                sent_at=datetime.now(UTC),
                created_by=user_id,
            )
            db.add(invite)
        db.flush()
        issued.append((invite, raw))
    return issued


def list_invites(db: Session, rfq_id: uuid.UUID) -> list[RfqInvite]:
    return list(
        db.scalars(
            select(RfqInvite).where(RfqInvite.rfq_id == rfq_id).order_by(RfqInvite.created_at)
        )
    )


def revoke_invite(db: Session, invite_id: uuid.UUID) -> RfqInvite:
    invite = db.get(RfqInvite, invite_id)
    if invite is None:
        raise NotFoundError("Invite not found")
    invite.revoked_at = datetime.now(UTC)
    db.flush()
    return invite


def invite_status(invite: RfqInvite) -> str:
    if invite.revoked_at is not None:
        return "revoked"
    if invite.responded_at is not None:
        return "responded"
    if invite.expires_at < datetime.now(UTC):
        return "expired"
    if invite.opened_at is not None:
        return "opened"
    return "sent"


# --- Supplier side -----------------------------------------------------------


def get_supplier_invite(
    db: DbDep,
    x_rfq_token: Annotated[str | None, Header()] = None,
) -> RfqInvite:
    if not x_rfq_token:
        raise UnauthorizedError("This link is not valid")
    invite = db.scalar(select(RfqInvite).where(RfqInvite.token_hash == _hash(x_rfq_token)))
    if invite is None or invite.revoked_at is not None:
        raise UnauthorizedError("This link is no longer valid")
    if invite.expires_at < datetime.now(UTC):
        raise UnauthorizedError("This link has expired")
    if invite.opened_at is None:
        invite.opened_at = datetime.now(UTC)
    return invite


SupplierInvite = Annotated[RfqInvite, Depends(get_supplier_invite)]


def rfq_for_supplier(db: Session, invite: RfqInvite) -> dict:
    """What the supplier is allowed to see.

    Deliberately narrow: the scope of work and the quantities, never the BOQ
    rates, the budget, or another supplier's quote.
    """
    rfq = db.get(Rfq, invite.rfq_id)
    items = list(
        db.scalars(
            select(RfqItem).where(RfqItem.rfq_id == rfq.id).order_by(RfqItem.sort_order)
        )
    )
    company = _company_name(db)
    return {
        "rfq_id": rfq.id,
        "doc_number": rfq.doc_number,
        "title": rfq.title,
        "body": rfq.body,
        "due_date": rfq.due_date,
        "buyer_name": company,
        "supplier_name": invite.supplier.name,
        "already_responded": invite.responded_at is not None,
        "items": [
            {
                "id": item.id,
                "description": item.description,
                "unit": item.unit,
                "quantity": item.quantity,
            }
            for item in items
        ],
    }


def _company_name(db: Session) -> str:
    from app.modules.company.models import CompanySettings

    company = db.scalar(select(CompanySettings))
    return company.name if company else "Construction ERP"


def submit_quote(db: Session, invite: RfqInvite, data) -> Quote:
    """Writes a real Quote, so a supplier reply lands in the same comparison
    as one keyed in by procurement."""
    if invite.responded_at is not None:
        raise ConflictError("A quote has already been submitted on this link")
    rfq = db.get(Rfq, invite.rfq_id)
    if rfq.status is not RfqStatus.issued:
        raise ConflictError("This request is no longer open for quotes")

    if db.scalar(
        select(Quote).where(Quote.rfq_id == rfq.id, Quote.supplier_id == invite.supplier_id)
    ):
        raise ConflictError("A quote from this supplier is already recorded")

    priced = [line for line in data.items if line.unit_price is not None]
    if not priced:
        raise ValidationFailedError("Price at least one line")

    quote = Quote(
        rfq_id=rfq.id,
        supplier_id=invite.supplier_id,
        status=QuoteStatus.received,
        received_date=date.today(),
        valid_until=data.valid_until,
        payment_terms=data.payment_terms,
        delivery_terms=data.delivery_terms,
        notes=data.notes,
        ai_extracted=False,
    )
    db.add(quote)
    db.flush()

    rfq_items = {
        item.id: item
        for item in db.scalars(select(RfqItem).where(RfqItem.rfq_id == rfq.id))
    }
    total = Decimal("0")
    for line in priced:
        source = rfq_items.get(line.rfq_item_id)
        if source is None:
            raise ValidationFailedError("That line is not on this request")
        quantity = line.quantity if line.quantity is not None else source.quantity
        db.add(
            QuoteItem(
                quote_id=quote.id,
                rfq_item_id=source.id,
                description=source.description,
                unit=source.unit,
                quantity=quantity,
                unit_price=line.unit_price,
            )
        )
        total += (quantity * line.unit_price).quantize(Decimal("0.01"))
    quote.total_amount = total
    invite.responded_at = datetime.now(UTC)
    db.flush()

    _notify_procurement(db, rfq, invite, total)
    return quote


def _notify_procurement(db: Session, rfq: Rfq, invite: RfqInvite, total: Decimal) -> None:
    """A quote that arrives while nobody is looking may as well not have."""
    from app.common.enums import UserRole
    from app.modules.notifications import service as notifications

    notifications.notify_roles(
        db,
        (UserRole.procurement_officer, UserRole.project_manager, UserRole.admin),
        type="quote_received",
        title=f"{invite.supplier.name} quoted {rfq.doc_number}",
        body=f"{total} for {rfq.title}",
        link=f"/procurement/rfqs/{rfq.id}",
    )
