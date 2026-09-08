import uuid

from fastapi import APIRouter, Depends

from app.common.enums import RequisitionStatus, UserRole
from app.common.pagination import PageParamsDep
from app.common.schemas import Page
from app.core.deps import DbDep, require_roles
from app.modules.procurement.schemas import PoDetail, RfqDetail
from app.modules.procurement.service import po_detail, rfq_detail
from app.modules.requisitions import line, service
from app.modules.requisitions.schemas import (
    ConvertToPo,
    RequisitionCreate,
    RequisitionDetail,
    RequisitionLineDetail,
    RequisitionRead,
)

router = APIRouter(tags=["requisitions"])

# Site raises requests; procurement (and PMs) action them
req_create = require_roles(UserRole.site_manager, UserRole.project_manager)
req_action = require_roles(UserRole.procurement_officer, UserRole.project_manager)


@router.get("/requisitions", response_model=Page[RequisitionRead])
def list_requisitions(
    db: DbDep,
    params: PageParamsDep,
    project_id: uuid.UUID | None = None,
    status: RequisitionStatus | None = None,
) -> Page[RequisitionRead]:
    rows, total = service.list_requisitions(
        db, params.page, params.page_size, project_id, status
    )
    return Page(
        items=[service.requisition_read(db, r) for r in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post(
    "/projects/{project_id}/requisitions",
    response_model=RequisitionDetail,
    status_code=201,
)
def create_requisition(
    project_id: uuid.UUID,
    body: RequisitionCreate,
    db: DbDep,
    user=Depends(req_create),
) -> RequisitionDetail:
    requisition = service.create_requisition(db, project_id, body, user.id)
    return service.requisition_detail(db, requisition.id)


@router.get("/requisitions/{requisition_id}", response_model=RequisitionDetail)
def get_requisition(requisition_id: uuid.UUID, db: DbDep) -> RequisitionDetail:
    return service.requisition_detail(db, requisition_id)


@router.post(
    "/requisitions/{requisition_id}/cancel",
    response_model=RequisitionRead,
    dependencies=[Depends(req_create)],
)
def cancel_requisition(requisition_id: uuid.UUID, db: DbDep) -> RequisitionRead:
    return service.requisition_read(db, service.cancel_requisition(db, requisition_id))


@router.post("/requisitions/{requisition_id}/convert-to-rfq", response_model=RfqDetail)
def convert_requisition_to_rfq(
    requisition_id: uuid.UUID, db: DbDep, user=Depends(req_action)
) -> RfqDetail:
    rfq = service.convert_to_rfq(db, requisition_id, user.id)
    return rfq_detail(db, rfq.id)


@router.post("/requisitions/{requisition_id}/convert-to-po", response_model=PoDetail)
def convert_requisition_to_po(
    requisition_id: uuid.UUID, body: ConvertToPo, db: DbDep, user=Depends(req_action)
) -> PoDetail:
    po = service.convert_to_po(db, requisition_id, body, user.id)
    return po_detail(db, po.id)


@router.get("/requisition-items/{item_id}", response_model=RequisitionLineDetail)
def get_requisition_line(item_id: uuid.UUID, db: DbDep) -> RequisitionLineDetail:
    """One requested line, and what became of it.

    A line is where a shortage on site turns into buying, and following it from
    the request to the delivery is the question people actually have. The line
    row itself holds a description and a quantity, so everything else is found
    by looking at what happened around it.
    """
    return line.line_detail(db, item_id)
