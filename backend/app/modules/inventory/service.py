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


def _last_delivery(db: Session, item_id: uuid.UUID):
    """The most recent goods-in for an item that came from a purchase order.

    Store receipts stamp the PO number into StockMovement.reference, which is
    the only link between stock and procurement — this walks it back to the
    supplier so reordering knows who to buy from and at what price.
    """
    from app.modules.procurement.models import PurchaseOrder

    row = db.execute(
        select(StockMovement, PurchaseOrder)
        .join(PurchaseOrder, StockMovement.reference == PurchaseOrder.doc_number)
        .where(
            StockMovement.stock_item_id == item_id,
            StockMovement.movement_type == StockMovementType.goods_in,
        )
        .order_by(StockMovement.movement_date.desc(), StockMovement.created_at.desc())
        .limit(1)
    ).first()
    return row if row is None else (row[0], row[1])


def reorder_suggestions(db: Session):
    """Low-stock items with a suggested top-up quantity, supplier and price.

    Suggested quantity tops the item back up to twice its reorder level, so a
    reorder is worth placing rather than immediately triggering again.
    """
    from app.modules.inventory.schemas import ReorderSuggestion, ReorderSuggestions

    items = list(
        db.scalars(
            select(StockItem)
            .where(
                StockItem.is_active.is_(True),
                StockItem.qty_on_hand <= StockItem.reorder_level,
            )
            .order_by(StockItem.code)
        )
    )
    suggestions = []
    total = Decimal("0")
    without_supplier = 0
    for item in items:
        target = item.reorder_level * 2
        quantity = (target - item.qty_on_hand).quantize(Decimal("0.001"))
        if quantity <= 0:
            quantity = item.reorder_level or Decimal("1")
        last = _last_delivery(db, item.id)
        movement, po = last if last else (None, None)
        unit_cost = (movement.unit_cost if movement else item.unit_cost) or Decimal("0")
        estimated = (quantity * unit_cost).quantize(CENT)
        if po is None:
            without_supplier += 1
        suggestions.append(
            ReorderSuggestion(
                stock_item_id=item.id,
                code=item.code,
                name=item.name,
                unit=item.unit,
                qty_on_hand=item.qty_on_hand,
                reorder_level=item.reorder_level,
                suggested_quantity=quantity,
                last_unit_cost=unit_cost,
                estimated_cost=estimated,
                supplier_id=po.supplier_id if po else None,
                supplier_name=po.supplier.name if po and po.supplier else None,
                last_po_number=po.doc_number if po else None,
                last_ordered=po.order_date if po else None,
            )
        )
        total += estimated
    return ReorderSuggestions(
        items=suggestions,
        total_estimated_cost=total.quantize(CENT),
        without_supplier=without_supplier,
    )


def create_reorder_pos(db: Session, data, user_id: uuid.UUID):
    """Draft one PO per supplier for the chosen low-stock items.

    Drafts only — a human reviews prices and issues them, matching the rule
    used for AI-generated documents.
    """
    from app.common.doc_numbers import next_doc_number
    from app.modules.inventory.schemas import ReorderResult
    from app.modules.procurement.models import PoItem, PurchaseOrder

    get_project(db, data.project_id)
    suggestions = {s.stock_item_id: s for s in reorder_suggestions(db).items}

    by_supplier: dict[uuid.UUID, list] = {}
    skipped: list[str] = []
    for item_id in data.stock_item_ids:
        suggestion = suggestions.get(item_id)
        if suggestion is None:
            item = get_item(db, item_id)
            skipped.append(item.code)
            continue
        if suggestion.supplier_id is None:
            skipped.append(suggestion.code)
            continue
        by_supplier.setdefault(suggestion.supplier_id, []).append(suggestion)

    po_ids, po_numbers = [], []
    for supplier_id, lines in by_supplier.items():
        total = Decimal("0")
        po_items = []
        for line in lines:
            po_items.append(
                PoItem(
                    description=f"{line.code} — {line.name}",
                    unit=line.unit,
                    quantity=line.suggested_quantity,
                    unit_price=line.last_unit_cost,
                )
            )
            total += line.suggested_quantity * line.last_unit_cost
        po = PurchaseOrder(
            project_id=data.project_id,
            supplier_id=supplier_id,
            doc_number=next_doc_number(db, PurchaseOrder, "PO"),
            expected_delivery=data.expected_delivery,
            notes="Stock reorder raised from low-stock levels — receive into the store.",
            total_amount=total.quantize(CENT),
            created_by=user_id,
            items=po_items,
        )
        db.add(po)
        db.flush()
        po_ids.append(po.id)
        po_numbers.append(po.doc_number)

    return ReorderResult(po_ids=po_ids, po_numbers=po_numbers, skipped_items=skipped)


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


def _check_barcode_free(db: Session, barcode: str, exclude_id: uuid.UUID | None = None) -> None:
    query = select(StockItem).where(StockItem.barcode == barcode)
    if exclude_id is not None:
        query = query.where(StockItem.id != exclude_id)
    existing = db.scalar(query)
    if existing is not None:
        raise ConflictError(f"Barcode already assigned to {existing.code} — {existing.name}")


def get_item_by_barcode(db: Session, barcode: str) -> StockItem:
    item = db.scalar(select(StockItem).where(StockItem.barcode == barcode))
    if item is None:
        raise NotFoundError("No stock item carries this barcode")
    return item


def create_item(db: Session, data: StockItemCreate, created_by: uuid.UUID) -> StockItem:
    if db.scalar(select(StockItem).where(StockItem.code == data.code)):
        raise ConflictError("A stock item with this code already exists")
    if data.barcode:
        _check_barcode_free(db, data.barcode)
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
    if updates.get("barcode"):
        _check_barcode_free(db, updates["barcode"], exclude_id=item.id)
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


# --- Stocktake ---------------------------------------------------------------


def _stocktake_line_read(line):
    from app.modules.inventory.schemas import StocktakeLineRead

    read = StocktakeLineRead.model_validate(line)
    item = line.stock_item
    if item:
        read.code, read.name, read.unit = item.code, item.name, item.unit
    if line.counted_quantity is not None:
        read.variance_quantity = line.counted_quantity - line.expected_quantity
        read.variance_value = (read.variance_quantity * line.unit_cost).quantize(CENT)
    return read


def stocktake_read(stocktake, detail: bool = False):
    from app.modules.inventory.schemas import StocktakeDetail, StocktakeRead

    lines = [_stocktake_line_read(line) for line in stocktake.lines]
    cls = StocktakeDetail if detail else StocktakeRead
    read = cls.model_validate(stocktake)
    read.line_count = len(lines)
    read.counted_count = sum(1 for line in lines if line.counted_quantity is not None)
    read.variance_value = sum((line.variance_value for line in lines), Decimal("0"))
    if detail:
        read.lines = sorted(lines, key=lambda line: line.code)
    return read


def get_stocktake(db: Session, stocktake_id: uuid.UUID):
    from app.modules.inventory.models import Stocktake

    stocktake = db.get(Stocktake, stocktake_id)
    if stocktake is None:
        raise NotFoundError("Stocktake not found")
    return stocktake


def list_stocktakes(db: Session, page: int, page_size: int, status=None):
    from app.modules.inventory.models import Stocktake

    query = select(Stocktake)
    if status is not None:
        query = query.where(Stocktake.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(
        db.scalars(
            query.order_by(Stocktake.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return rows, total


def create_stocktake(db: Session, data, user_id: uuid.UUID):
    """Open a counting session, snapshotting today's expected quantities."""
    from app.common.enums import StocktakeStatus
    from app.modules.inventory.models import Stocktake, StocktakeLine

    open_session = db.scalar(
        select(Stocktake).where(Stocktake.status == StocktakeStatus.counting)
    )
    if open_session:
        raise ConflictError(
            f"A stocktake ({open_session.doc_number}) is already in progress — "
            "approve or cancel it first"
        )

    query = select(StockItem).where(StockItem.is_active.is_(True))
    if data.stock_item_ids:
        query = query.where(StockItem.id.in_(data.stock_item_ids))
    if data.category:
        query = query.where(StockItem.category == data.category)
    items = list(db.scalars(query.order_by(StockItem.code)))
    if not items:
        raise ValidationFailedError("No stock items match this stocktake")

    stocktake = Stocktake(
        doc_number=next_doc_number(db, Stocktake, "STK"),
        count_date=data.count_date or date.today(),
        notes=data.notes,
        created_by=user_id,
        lines=[
            StocktakeLine(
                stock_item_id=item.id,
                expected_quantity=item.qty_on_hand,
                unit_cost=item.unit_cost,
            )
            for item in items
        ],
    )
    db.add(stocktake)
    db.flush()
    return stocktake


def set_stocktake_counts(db: Session, stocktake_id: uuid.UUID, data):
    """Record counted quantities. Lines left uncounted stay null and are
    ignored at approval — a partial count must not zero the shelf."""
    from app.common.enums import StocktakeStatus

    stocktake = get_stocktake(db, stocktake_id)
    if stocktake.status != StocktakeStatus.counting:
        raise ConflictError("Only a stocktake in progress can be counted")

    by_item = {line.stock_item_id: line for line in stocktake.lines}
    for spec in data.lines:
        line = by_item.get(spec.stock_item_id)
        if line is None:
            raise ValidationFailedError("Stock item is not part of this stocktake")
        line.counted_quantity = spec.counted_quantity
        line.notes = spec.notes
    db.flush()
    return stocktake


def approve_stocktake(db: Session, stocktake_id: uuid.UUID, user_id: uuid.UUID):
    """Post the counted variances as stock adjustments, in one transaction."""
    from datetime import datetime, timezone

    from app.common.enums import StocktakeStatus

    stocktake = get_stocktake(db, stocktake_id)
    if stocktake.status != StocktakeStatus.counting:
        raise ConflictError("Only a stocktake in progress can be approved")
    counted = [line for line in stocktake.lines if line.counted_quantity is not None]
    if not counted:
        raise ValidationFailedError("Nothing has been counted yet")

    for line in counted:
        variance = line.counted_quantity - line.expected_quantity
        if variance == 0:
            continue
        adjust(
            db,
            line.stock_item_id,
            AdjustRequest(
                quantity=variance,
                movement_date=stocktake.count_date,
                notes=f"Stocktake {stocktake.doc_number}"
                + (f": {line.notes}" if line.notes else ""),
            ),
            user_id,
        )

    stocktake.status = StocktakeStatus.approved
    stocktake.approved_at = datetime.now(timezone.utc)
    stocktake.approved_by = user_id
    db.flush()
    return stocktake


def cancel_stocktake(db: Session, stocktake_id: uuid.UUID):
    from app.common.enums import StocktakeStatus

    stocktake = get_stocktake(db, stocktake_id)
    if stocktake.status != StocktakeStatus.counting:
        raise ConflictError("Only a stocktake in progress can be cancelled")
    stocktake.status = StocktakeStatus.cancelled
    db.flush()
    return stocktake
