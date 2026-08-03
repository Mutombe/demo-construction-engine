import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.common.doc_numbers import next_doc_number
from app.common.enums import CostSource, StockMovementType
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.boq.models import BoqItem
from app.modules.costs.models import CostEntry
from app.modules.inventory.models import StockItem, StockMovement
from app.modules.inventory.schemas import (
    AdjustRequest,
    GoodsInRequest,
    IssueRequest,
    StockItemCreate,
    StockItemRead,
    StockItemUpdate,
)
from app.modules.projects.service import get_project

CENT = Decimal("0.01")


def item_read(item: StockItem) -> StockItemRead:
    read = StockItemRead.model_validate(item)
    read.low_stock = item.qty_on_hand <= item.reorder_level
    return read


def list_items(
    db: Session,
    page: int,
    page_size: int,
    search: str | None = None,
    active_only: bool = False,
    low_stock_only: bool = False,
) -> tuple[list[StockItem], int]:
    query = select(StockItem)
    if search:
        query = query.where(
            StockItem.code.ilike(f"%{search}%")
            | StockItem.name.ilike(f"%{search}%")
            | StockItem.category.ilike(f"%{search}%")
        )
    if active_only:
        query = query.where(StockItem.is_active.is_(True))
    if low_stock_only:
        query = query.where(StockItem.qty_on_hand <= StockItem.reorder_level)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = list(
        db.scalars(query.order_by(StockItem.code).offset((page - 1) * page_size).limit(page_size))
    )
    return items, total


def get_item(db: Session, item_id: uuid.UUID) -> StockItem:
    item = db.get(StockItem, item_id)
    if item is None:
        raise NotFoundError("Stock item not found")
    return item


def _lock_item(db: Session, item_id: uuid.UUID) -> StockItem:
    """Row-lock the item so concurrent movements serialize their stock math."""
    item = db.scalar(select(StockItem).where(StockItem.id == item_id).with_for_update())
    if item is None:
        raise NotFoundError("Stock item not found")
    return item


def create_item(db: Session, data: StockItemCreate, created_by: uuid.UUID) -> StockItem:
    if db.scalar(select(StockItem).where(StockItem.code == data.code)):
        raise ConflictError("A stock item with this code already exists")
    item = StockItem(**data.model_dump(), created_by=created_by)
    db.add(item)
    db.flush()
    return item


def update_item(db: Session, item_id: uuid.UUID, data: StockItemUpdate) -> StockItem:
    item = get_item(db, item_id)
    updates = data.model_dump(exclude_unset=True)
    if (
        "code" in updates
        and updates["code"] != item.code
        and db.scalar(select(StockItem).where(StockItem.code == updates["code"]))
    ):
        raise ConflictError("A stock item with this code already exists")
    for field, value in updates.items():
        setattr(item, field, value)
    return item


def list_movements(
    db: Session, item_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[StockMovement], int]:
    get_item(db, item_id)
    query = (
        select(StockMovement)
        .options(joinedload(StockMovement.project))
        .where(StockMovement.stock_item_id == item_id)
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    movements = list(
        db.scalars(
            query.order_by(StockMovement.movement_date.desc(), StockMovement.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return movements, total


def goods_in(
    db: Session, item_id: uuid.UUID, data: GoodsInRequest, user_id: uuid.UUID
) -> StockItem:
    item = _lock_item(db, item_id)
    qoh, qty = item.qty_on_hand, data.quantity
    if qoh <= 0:
        item.unit_cost = data.unit_cost
    else:
        item.unit_cost = (((qoh * item.unit_cost) + (qty * data.unit_cost)) / (qoh + qty)).quantize(
            CENT
        )
    item.qty_on_hand = qoh + qty
    db.add(
        StockMovement(
            stock_item_id=item.id,
            doc_number=next_doc_number(db, StockMovement, "GRN"),
            movement_type=StockMovementType.goods_in,
            movement_date=data.movement_date or date.today(),
            quantity=qty,
            unit_cost=data.unit_cost,
            reference=data.reference,
            notes=data.notes,
            created_by=user_id,
        )
    )
    db.flush()
    return item


def issue_to_project(
    db: Session, item_id: uuid.UUID, data: IssueRequest, user_id: uuid.UUID
) -> StockItem:
    item = _lock_item(db, item_id)
    get_project(db, data.project_id)
    if data.boq_item_id is not None:
        boq_item = db.get(BoqItem, data.boq_item_id)
        if boq_item is None or boq_item.project_id != data.project_id:
            raise ValidationFailedError("BOQ item does not exist in this project")
    if data.quantity > item.qty_on_hand:
        raise ConflictError(f"Insufficient stock: only {item.qty_on_hand} {item.unit} on hand")

    doc = next_doc_number(db, StockMovement, "ISS")
    when = data.movement_date or date.today()
    amount = (data.quantity * item.unit_cost).quantize(CENT)
    entry = CostEntry(
        project_id=data.project_id,
        boq_item_id=data.boq_item_id,
        entry_date=when,
        description=f"Store issue {doc}: {item.name}",
        amount=amount,
        quantity=data.quantity,
        source=CostSource.inventory_issue,
        reference=doc,
        created_by=user_id,
    )
    db.add(entry)
    db.flush()

    item.qty_on_hand -= data.quantity  # WAC unchanged on issue
    db.add(
        StockMovement(
            stock_item_id=item.id,
            doc_number=doc,
            movement_type=StockMovementType.issue,
            movement_date=when,
            quantity=-data.quantity,
            unit_cost=item.unit_cost,
            project_id=data.project_id,
            boq_item_id=data.boq_item_id,
            cost_entry_id=entry.id,
            notes=data.notes,
            created_by=user_id,
        )
    )
    db.flush()
    return item


def adjust(db: Session, item_id: uuid.UUID, data: AdjustRequest, user_id: uuid.UUID) -> StockItem:
    if data.quantity == 0:
        raise ValidationFailedError("Adjustment quantity cannot be zero")
    item = _lock_item(db, item_id)
    if item.qty_on_hand + data.quantity < 0:
        raise ConflictError("Adjustment would take stock below zero")
    item.qty_on_hand += data.quantity  # WAC unchanged; quantity corrections only
    db.add(
        StockMovement(
            stock_item_id=item.id,
            doc_number=next_doc_number(db, StockMovement, "ADJ"),
            movement_type=StockMovementType.adjustment,
            movement_date=data.movement_date or date.today(),
            quantity=data.quantity,
            unit_cost=item.unit_cost,
            notes=data.notes,
            created_by=user_id,
        )
    )
    db.flush()
    return item
