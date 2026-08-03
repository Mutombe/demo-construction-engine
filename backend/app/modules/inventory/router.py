import uuid

from fastapi import APIRouter, Depends

from app.common.enums import UserRole
from app.common.pagination import PageParamsDep
from app.common.schemas import Page
from app.core.deps import DbDep, require_roles
from app.modules.inventory import service
from app.modules.inventory.schemas import (
    AdjustRequest,
    GoodsInRequest,
    IssueRequest,
    StockItemCreate,
    StockItemRead,
    StockItemUpdate,
    StockMovementRead,
)

router = APIRouter(tags=["inventory"])

inv_write = Depends(require_roles(UserRole.procurement_officer, UserRole.project_manager))
inv_write_user = require_roles(UserRole.procurement_officer, UserRole.project_manager)
inv_issue_user = require_roles(
    UserRole.procurement_officer, UserRole.project_manager, UserRole.site_manager
)


def _movement_read(m) -> StockMovementRead:
    read = StockMovementRead.model_validate(m)
    read.project_name = m.project.name if m.project else None
    return read


@router.get("/stock-items", response_model=Page[StockItemRead])
def list_stock_items(
    db: DbDep,
    params: PageParamsDep,
    search: str | None = None,
    active_only: bool = False,
    low_stock_only: bool = False,
) -> Page[StockItemRead]:
    items, total = service.list_items(
        db, params.page, params.page_size, search, active_only, low_stock_only
    )
    return Page(
        items=[service.item_read(i) for i in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/stock-items", response_model=StockItemRead, status_code=201)
def create_stock_item(
    body: StockItemCreate, db: DbDep, user=Depends(inv_write_user)
) -> StockItemRead:
    return service.item_read(service.create_item(db, body, user.id))


# NOTE: declared before /stock-items/{item_id} so the path never hits the UUID route
@router.get("/stock-items/by-barcode/{barcode}", response_model=StockItemRead)
def get_stock_item_by_barcode(barcode: str, db: DbDep) -> StockItemRead:
    return service.item_read(service.get_item_by_barcode(db, barcode))


@router.get("/stock-items/{item_id}", response_model=StockItemRead)
def get_stock_item(item_id: uuid.UUID, db: DbDep) -> StockItemRead:
    return service.item_read(service.get_item(db, item_id))


@router.patch("/stock-items/{item_id}", response_model=StockItemRead, dependencies=[inv_write])
def update_stock_item(item_id: uuid.UUID, body: StockItemUpdate, db: DbDep) -> StockItemRead:
    return service.item_read(service.update_item(db, item_id, body))


@router.get("/stock-items/{item_id}/movements", response_model=Page[StockMovementRead])
def list_stock_movements(
    item_id: uuid.UUID, db: DbDep, params: PageParamsDep
) -> Page[StockMovementRead]:
    movements, total = service.list_movements(db, item_id, params.page, params.page_size)
    return Page(
        items=[_movement_read(m) for m in movements],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/stock-items/{item_id}/goods-in", response_model=StockItemRead)
def goods_in(
    item_id: uuid.UUID, body: GoodsInRequest, db: DbDep, user=Depends(inv_write_user)
) -> StockItemRead:
    return service.item_read(service.goods_in(db, item_id, body, user.id))


@router.post("/stock-items/{item_id}/issue", response_model=StockItemRead)
def issue_stock(
    item_id: uuid.UUID, body: IssueRequest, db: DbDep, user=Depends(inv_issue_user)
) -> StockItemRead:
    return service.item_read(service.issue_to_project(db, item_id, body, user.id))


@router.post("/stock-items/{item_id}/adjust", response_model=StockItemRead)
def adjust_stock(
    item_id: uuid.UUID, body: AdjustRequest, db: DbDep, user=Depends(inv_write_user)
) -> StockItemRead:
    return service.item_read(service.adjust(db, item_id, body, user.id))
