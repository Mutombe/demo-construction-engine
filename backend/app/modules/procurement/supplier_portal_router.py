"""Routes for the supplier portal.

Split into two halves that must not be confused. The `/supplier-portal/{token}`
routes are **unauthenticated** and reachable by anyone holding the link, so
every one of them is scoped to the supplier the token resolves to and never
takes a supplier id from the caller. The staff routes are behind the usual
permissions.
"""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import UserRole
from app.core.deps import CurrentUser, DbDep, require_roles
from app.modules.procurement import supplier_portal

# Anyone holding the link reaches these. Every route is scoped to the
# supplier the token resolves to and never takes a supplier id from the
# caller.
router = APIRouter(tags=["supplier-portal"])

# Staff routes. Mounted under the authenticated router in main, so they
# are never reachable with a portal link even by accident.
staff_router = APIRouter(tags=["supplier-portal"])

proc_admin = Depends(require_roles(UserRole.procurement_officer, UserRole.admin))


# --- Schemas -----------------------------------------------------------------


class TokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    supplier_id: uuid.UUID
    label: str | None
    expires_at: str | None = None
    revoked_at: str | None = None
    last_used_at: str | None = None


class TokenIssued(BaseModel):
    id: uuid.UUID
    label: str | None
    # Shown once. Only the hash is stored, so this cannot be recovered later.
    url: str


class IssueRequest(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    days: int = Field(default=365, ge=1, le=1095)


class PortalOrder(BaseModel):
    id: uuid.UUID
    doc_number: str
    order_date: date | None = None
    status: str
    total_amount: Decimal


class PortalInvoice(BaseModel):
    id: uuid.UUID
    doc_number: str
    reference: str | None = None
    invoice_date: date
    amount: Decimal
    status: str
    variance: Decimal
    note: str | None = None


class PortalOverview(BaseModel):
    supplier_name: str
    company_name: str
    is_compliant: bool
    missing_documents: list[str] = []
    orders: list[PortalOrder] = []
    invoices: list[PortalInvoice] = []


class InvoiceSubmit(BaseModel):
    purchase_order_id: uuid.UUID | None = None
    reference: str | None = Field(default=None, max_length=60)
    invoice_date: date | None = None
    amount: Decimal = Field(gt=0)
    notes: str | None = None


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doc_number: str
    supplier_id: uuid.UUID
    purchase_order_id: uuid.UUID | None
    reference: str | None
    invoice_date: date
    amount: Decimal
    variance: Decimal
    status: str
    notes: str | None
    decision_note: str | None


class DecisionRequest(BaseModel):
    accept: bool
    note: str | None = None


class MatchRow(BaseModel):
    invoice_id: uuid.UUID
    doc_number: str
    reference: str | None = None
    amount: Decimal
    order_number: str | None = None
    ordered: Decimal | None = None
    variance: Decimal | None = None
    issue: str


# --- The supplier's side, no login ------------------------------------------


@router.get("/supplier-portal/{token}", response_model=PortalOverview)
def portal_overview(token: str, db: DbDep) -> PortalOverview:
    """Their orders, their invoices, and any paperwork of theirs that lapsed."""
    return supplier_portal.overview(db, supplier_portal.resolve(db, token))


@router.post("/supplier-portal/{token}/invoices", response_model=InvoiceRead, status_code=201)
def portal_submit_invoice(token: str, body: InvoiceSubmit, db: DbDep) -> InvoiceRead:
    """Submit an invoice against an order.

    Records a claim; posts nothing. The payable was created when the goods
    were received, and booking this as well would owe them twice for one
    delivery.
    """
    return supplier_portal.submit_invoice(db, supplier_portal.resolve(db, token), body)


# --- The staff side ----------------------------------------------------------


@staff_router.get("/suppliers/{supplier_id}/portal-links", response_model=list[TokenRead])
def list_links(supplier_id: uuid.UUID, db: DbDep, _=proc_admin) -> list[TokenRead]:
    return [
        TokenRead(
            id=t.id,
            supplier_id=t.supplier_id,
            label=t.label,
            expires_at=t.expires_at.isoformat() if t.expires_at else None,
            revoked_at=t.revoked_at.isoformat() if t.revoked_at else None,
            last_used_at=t.last_used_at.isoformat() if t.last_used_at else None,
        )
        for t in supplier_portal.list_tokens(db, supplier_id)
    ]


@staff_router.post(
    "/suppliers/{supplier_id}/portal-links", response_model=TokenIssued, status_code=201
)
def issue_link(
    supplier_id: uuid.UUID, body: IssueRequest, db: DbDep, user: CurrentUser, _=proc_admin
) -> TokenIssued:
    """Mint a link for a supplier. The URL comes back once and cannot be
    recovered afterwards — only its hash is kept."""
    token, raw = supplier_portal.issue_token(db, supplier_id, body.label, body.days, user)
    return TokenIssued(id=token.id, label=token.label, url=supplier_portal.portal_url(raw))


@staff_router.delete("/portal-links/{token_id}", status_code=204)
def revoke_link(token_id: uuid.UUID, db: DbDep, _=proc_admin) -> None:
    supplier_portal.revoke_token(db, token_id)


@staff_router.get("/supplier-invoices", response_model=list[InvoiceRead])
def list_supplier_invoices(
    db: DbDep,
    _=proc_admin,
    status: str | None = None,
    supplier_id: uuid.UUID | None = None,
) -> list[InvoiceRead]:
    return list(db.scalars(supplier_portal.list_invoices(db, status, supplier_id)))


@staff_router.post("/supplier-invoices/{invoice_id}/decide", response_model=InvoiceRead)
def decide_supplier_invoice(
    invoice_id: uuid.UUID, body: DecisionRequest, db: DbDep, user: CurrentUser, _=proc_admin
) -> InvoiceRead:
    """Accept the claim or send it back with a reason."""
    return supplier_portal.decide_invoice(db, invoice_id, body.accept, body.note, user)


@staff_router.get("/supplier-invoices/matching", response_model=list[MatchRow])
def get_matching_report(db: DbDep, _=proc_admin) -> list[MatchRow]:
    """Claims that do not agree with the order they are against.

    The reason the portal earns its keep: a supplier billing more than was
    ordered is caught here rather than after it has been paid.
    """
    return supplier_portal.matching_report(db)
