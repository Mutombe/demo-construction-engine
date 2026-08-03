import uuid

from fastapi import APIRouter, Depends

from app.common.enums import UserRole
from app.common.pagination import PageParamsDep
from app.common.schemas import Page
from app.core.deps import DbDep, require_roles
from app.modules.procurement import service
from app.modules.procurement.schemas import (
    PoCreate,
    PoDetail,
    PoRead,
    PoReceive,
    PoUpdate,
    QuoteCreate,
    QuoteRead,
    QuoteUpdate,
    RfqCreate,
    RfqDetail,
    RfqItemsReplace,
    RfqRead,
    RfqUpdate,
    SupplierCreate,
    SupplierRead,
    SupplierUpdate,
)

router = APIRouter(tags=["procurement"])

proc_write = Depends(require_roles(UserRole.procurement_officer, UserRole.project_manager))
# Approval seam: same pair today, but a stricter rule would change only this constant
po_approve = Depends(require_roles(UserRole.procurement_officer, UserRole.project_manager))
proc_user = require_roles(UserRole.procurement_officer, UserRole.project_manager)


def _po_read(po) -> PoRead:
    read = PoRead.model_validate(po)
    read.supplier_name = po.supplier.name if po.supplier else None
    return read


def _po_detail(po) -> PoDetail:
    detail = PoDetail.model_validate(po)
    detail.supplier_name = po.supplier.name if po.supplier else None
    detail.project_name = po.project.name if po.project else None
    detail.project_code = po.project.code if po.project else None
    return detail


# --- Suppliers --------------------------------------------------------------


@router.get("/suppliers", response_model=Page[SupplierRead])
def list_suppliers(
    db: DbDep,
    params: PageParamsDep,
    search: str | None = None,
    active_only: bool = False,
) -> Page[SupplierRead]:
    suppliers, total = service.list_suppliers(
        db, params.page, params.page_size, search, active_only
    )
    return Page(
        items=[SupplierRead.model_validate(s) for s in suppliers],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/suppliers", response_model=SupplierRead, status_code=201)
def create_supplier(body: SupplierCreate, db: DbDep, user=Depends(proc_user)) -> SupplierRead:
    return SupplierRead.model_validate(service.create_supplier(db, body, user.id))


@router.get("/suppliers/{supplier_id}", response_model=SupplierRead)
def get_supplier(supplier_id: uuid.UUID, db: DbDep) -> SupplierRead:
    return SupplierRead.model_validate(service.get_supplier(db, supplier_id))


@router.patch("/suppliers/{supplier_id}", response_model=SupplierRead, dependencies=[proc_write])
def update_supplier(supplier_id: uuid.UUID, body: SupplierUpdate, db: DbDep) -> SupplierRead:
    return SupplierRead.model_validate(service.update_supplier(db, supplier_id, body))


# --- RFQs -------------------------------------------------------------------


@router.get("/projects/{project_id}/rfqs", response_model=Page[RfqRead])
def list_rfqs(project_id: uuid.UUID, db: DbDep, params: PageParamsDep) -> Page[RfqRead]:
    rfqs, total = service.list_rfqs(db, project_id, params.page, params.page_size)
    return Page(items=rfqs, total=total, page=params.page, page_size=params.page_size)


@router.post("/projects/{project_id}/rfqs", response_model=RfqDetail, status_code=201)
def create_rfq(
    project_id: uuid.UUID, body: RfqCreate, db: DbDep, user=Depends(proc_user)
) -> RfqDetail:
    rfq = service.create_rfq(db, project_id, body, user.id)
    return service.rfq_detail(db, rfq.id)


@router.get("/rfqs/{rfq_id}", response_model=RfqDetail)
def get_rfq(rfq_id: uuid.UUID, db: DbDep) -> RfqDetail:
    return service.rfq_detail(db, rfq_id)


@router.patch("/rfqs/{rfq_id}", response_model=RfqDetail, dependencies=[proc_write])
def update_rfq(rfq_id: uuid.UUID, body: RfqUpdate, db: DbDep) -> RfqDetail:
    service.update_rfq(db, rfq_id, body)
    return service.rfq_detail(db, rfq_id)


@router.put("/rfqs/{rfq_id}/items", response_model=RfqDetail, dependencies=[proc_write])
def replace_rfq_items(rfq_id: uuid.UUID, body: RfqItemsReplace, db: DbDep) -> RfqDetail:
    service.replace_rfq_items(db, rfq_id, body.items)
    return service.rfq_detail(db, rfq_id)


@router.post("/rfqs/{rfq_id}/issue", response_model=RfqDetail, dependencies=[proc_write])
def issue_rfq(rfq_id: uuid.UUID, db: DbDep) -> RfqDetail:
    service.issue_rfq(db, rfq_id)
    return service.rfq_detail(db, rfq_id)


@router.delete("/rfqs/{rfq_id}", status_code=204, dependencies=[proc_write])
def delete_rfq(rfq_id: uuid.UUID, db: DbDep) -> None:
    service.delete_rfq(db, rfq_id)


# --- Quotes -----------------------------------------------------------------


@router.get("/rfqs/{rfq_id}/quotes", response_model=list[QuoteRead])
def list_quotes(rfq_id: uuid.UUID, db: DbDep) -> list[QuoteRead]:
    return service.list_quotes(db, rfq_id)


@router.post("/rfqs/{rfq_id}/quotes", response_model=QuoteRead, status_code=201)
def create_quote(
    rfq_id: uuid.UUID, body: QuoteCreate, db: DbDep, user=Depends(proc_user)
) -> QuoteRead:
    quote = service.create_quote(db, rfq_id, body, user.id)
    return service.quote_read(db, quote)


@router.patch("/quotes/{quote_id}", response_model=QuoteRead, dependencies=[proc_write])
def update_quote(quote_id: uuid.UUID, body: QuoteUpdate, db: DbDep) -> QuoteRead:
    quote = service.update_quote(db, quote_id, body)
    return service.quote_read(db, quote)


@router.delete("/quotes/{quote_id}", status_code=204, dependencies=[proc_write])
def delete_quote(quote_id: uuid.UUID, db: DbDep) -> None:
    service.delete_quote(db, quote_id)


@router.post("/quotes/{quote_id}/accept", response_model=QuoteRead, dependencies=[po_approve])
def accept_quote(quote_id: uuid.UUID, db: DbDep) -> QuoteRead:
    quote = service.accept_quote(db, quote_id)
    return service.quote_read(db, quote)


# --- Purchase orders --------------------------------------------------------


@router.get("/projects/{project_id}/purchase-orders", response_model=Page[PoRead])
def list_purchase_orders(project_id: uuid.UUID, db: DbDep, params: PageParamsDep) -> Page[PoRead]:
    pos, total = service.list_pos(db, project_id, params.page, params.page_size)
    return Page(
        items=[_po_read(p) for p in pos],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/projects/{project_id}/purchase-orders", response_model=PoDetail, status_code=201)
def create_purchase_order(
    project_id: uuid.UUID, body: PoCreate, db: DbDep, user=Depends(proc_user)
) -> PoDetail:
    return _po_detail(service.create_po(db, project_id, body, user.id))


@router.get("/purchase-orders/{po_id}", response_model=PoDetail)
def get_purchase_order(po_id: uuid.UUID, db: DbDep) -> PoDetail:
    return _po_detail(service.get_po(db, po_id))


@router.patch("/purchase-orders/{po_id}", response_model=PoDetail, dependencies=[proc_write])
def update_purchase_order(po_id: uuid.UUID, body: PoUpdate, db: DbDep) -> PoDetail:
    return _po_detail(service.update_po(db, po_id, body))


@router.post("/purchase-orders/{po_id}/issue", response_model=PoDetail, dependencies=[po_approve])
def issue_purchase_order(po_id: uuid.UUID, db: DbDep) -> PoDetail:
    return _po_detail(service.issue_po(db, po_id))


@router.post("/purchase-orders/{po_id}/receive", response_model=PoDetail)
def receive_purchase_order(
    po_id: uuid.UUID, body: PoReceive, db: DbDep, user=Depends(proc_user)
) -> PoDetail:
    return _po_detail(service.receive_po(db, po_id, body, user.id))


@router.post("/purchase-orders/{po_id}/cancel", response_model=PoDetail, dependencies=[po_approve])
def cancel_purchase_order(po_id: uuid.UUID, db: DbDep) -> PoDetail:
    return _po_detail(service.cancel_po(db, po_id))


@router.get("/purchase-orders/{po_id}/pdf")
def download_purchase_order_pdf(po_id: uuid.UUID, db: DbDep):
    from fastapi import Response

    from app.modules.procurement.pdf import po_pdf

    po = service.get_po(db, po_id)
    return Response(
        content=po_pdf(db, po),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{po.doc_number}.pdf"'},
    )
