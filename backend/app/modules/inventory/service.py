import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.common.doc_numbers import next_doc_number
from app.common.enums import CostSource, StockLossReason, StockMovementType
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.boq.models import BoqItem
from app.modules.costs.models import CostEntry
from app.modules.inventory.models import (
    StockBatch,
    StockItem,
    StockLevel,
    StockLocation,
    StockMovement,
)
from app.modules.inventory.schemas import (
    AdjustRequest,
    GoodsInRequest,
    IssueRequest,
    StockItemCreate,
    StockItemRead,
    StockItemUpdate,
)
from app.modules.projects.service import get_project
from app.modules.accounting import service as accounting

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
    location_id: uuid.UUID | None = None,
) -> tuple[list[StockItem], int]:
    query = select(StockItem)
    if location_id is not None:
        # Only items actually held at that location, so the list matches what
        # someone standing in that store would find on the shelves.
        query = query.join(StockLevel, StockLevel.stock_item_id == StockItem.id).where(
            StockLevel.location_id == location_id, StockLevel.quantity != 0
        )
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


def default_location(db: Session) -> StockLocation:
    """The location anything unspecified belongs to.

    Created on first use if absent rather than assumed, so a fresh install —
    or any path that builds the schema without running the data migration —
    still works instead of failing on the first goods-in. Exactly one location
    carries is_default, which is what lets every existing single-store caller
    keep working without naming a location.
    """
    location = db.scalar(
        select(StockLocation).where(StockLocation.is_default.is_(True))
    )
    if location is None:
        location = StockLocation(
            code="MAIN", name="Main Store", is_default=True, is_active=True
        )
        db.add(location)
        db.flush()
    return location


def get_location(db: Session, location_id: uuid.UUID) -> StockLocation:
    location = db.get(StockLocation, location_id)
    if location is None:
        raise NotFoundError("Stock location not found")
    return location


def _resolve_location(db: Session, location_id: uuid.UUID | None) -> StockLocation:
    return get_location(db, location_id) if location_id else default_location(db)


def _lock_level(db: Session, item_id: uuid.UUID, location_id: uuid.UUID) -> StockLevel:
    """Row-lock this item's balance at this location, creating it at zero.

    Locking the level rather than the item lets two locations move the same
    item concurrently without serialising against each other.
    """
    level = db.scalar(
        select(StockLevel)
        .where(StockLevel.stock_item_id == item_id, StockLevel.location_id == location_id)
        .with_for_update()
    )
    if level is None:
        level = StockLevel(stock_item_id=item_id, location_id=location_id, quantity=Decimal("0"))
        db.add(level)
        db.flush()
    return level


def level_quantity(db: Session, item_id: uuid.UUID, location_id: uuid.UUID) -> Decimal:
    return db.scalar(
        select(func.coalesce(StockLevel.quantity, 0)).where(
            StockLevel.stock_item_id == item_id, StockLevel.location_id == location_id
        )
    ) or Decimal("0")


def _upsert_batch(db, item, location, batch_number, expiry, supplier_ref, received):
    """Find this lot at this location, or start it.

    The same lot at two locations is two rows sharing a batch_number, so a
    recall gathers them with one query while quantity stays a simple
    item-by-location grid.
    """
    batch = db.scalar(
        select(StockBatch)
        .where(
            StockBatch.stock_item_id == item.id,
            StockBatch.location_id == location.id,
            StockBatch.batch_number == batch_number,
        )
        .with_for_update()
    )
    if batch is None:
        batch = StockBatch(
            stock_item_id=item.id,
            location_id=location.id,
            batch_number=batch_number,
            expiry_date=expiry,
            received_date=received,
            supplier_ref=supplier_ref,
            quantity=Decimal("0"),
        )
        db.add(batch)
        db.flush()
    elif expiry and batch.expiry_date != expiry:
        # Same lot number cannot carry two different dates
        raise ValidationFailedError(
            f"Batch {batch_number} is already recorded with expiry "
            f"{batch.expiry_date}"
        )
    return batch


def _consume_batches(db, item, location, quantity, batch_id=None):
    """Take quantity out of the lots at a location, earliest expiry first.

    FEFO rather than FIFO: with perishable material what matters is what goes
    off soonest, not what arrived first. Undated lots are consumed last, since
    anything with a date is more urgent than anything without one.
    """
    query = select(StockBatch).where(
        StockBatch.stock_item_id == item.id,
        StockBatch.location_id == location.id,
        StockBatch.quantity > 0,
    )
    if batch_id is not None:
        query = query.where(StockBatch.id == batch_id)
    batches = list(
        db.scalars(
            query.order_by(
                StockBatch.expiry_date.is_(None),  # dated lots first
                StockBatch.expiry_date,
                StockBatch.received_date,
            ).with_for_update()
        )
    )
    available = sum((b.quantity for b in batches), Decimal("0"))
    if available < quantity:
        where = "that batch" if batch_id else f"the lots at {location.name}"
        raise ConflictError(
            f"Insufficient stock in {where}: only {available} {item.unit} available"
        )

    taken = []
    remaining = quantity
    for batch in batches:
        if remaining <= 0:
            break
        portion = min(batch.quantity, remaining)
        batch.quantity -= portion
        remaining -= portion
        taken.append((batch, portion))
    return taken


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
    from app.common.enums import TrackingMode

    item = _lock_item(db, item_id)
    location = _resolve_location(db, getattr(data, "location_id", None))
    level = _lock_level(db, item.id, location.id)

    batch = None
    if item.tracking_mode != TrackingMode.none:
        batch_number = (getattr(data, "batch_number", None) or "").strip()
        if not batch_number:
            raise ValidationFailedError(
                f"{item.name} is {item.tracking_mode.value}-tracked — a "
                f"{'serial' if item.tracking_mode == TrackingMode.serial else 'batch'} "
                "number is required"
            )
        if item.tracking_mode == TrackingMode.serial and data.quantity != 1:
            raise ValidationFailedError(
                "Serial-tracked items are received one unit at a time"
            )
        batch = _upsert_batch(
            db,
            item,
            location,
            batch_number,
            getattr(data, "expiry_date", None),
            getattr(data, "supplier_ref", None),
            data.movement_date or date.today(),
        )
        batch.quantity += data.quantity

    qoh, qty = item.qty_on_hand, data.quantity
    # Weighted average is company-wide: the same material costs the same
    # wherever it is stored, so receiving anywhere reprices the item once.
    if qoh <= 0:
        item.unit_cost = data.unit_cost
    else:
        item.unit_cost = (((qoh * item.unit_cost) + (qty * data.unit_cost)) / (qoh + qty)).quantize(
            CENT
        )
    item.qty_on_hand = qoh + qty
    level.quantity += qty
    db.add(
        StockMovement(
            stock_item_id=item.id,
            location_id=location.id,
            doc_number=next_doc_number(db, StockMovement, "GRN"),
            batch_id=batch.id if batch else None,
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
    # Stock arriving is an asset swap, not a project cost: the job is charged
    # when the material is issued. Posted here rather than at the purchase
    # order because this is the single door stock comes through — a direct
    # receipt and a PO delivery both land on the books the same way.
    accounting.post_goods_in(
        db,
        amount=qty * data.unit_cost,
        reference=data.reference or item.code,
        when=data.movement_date or date.today(),
    )
    return item


def issue_to_project(
    db: Session, item_id: uuid.UUID, data: IssueRequest, user_id: uuid.UUID
) -> StockItem:
    item = _lock_item(db, item_id)
    location = _resolve_location(db, getattr(data, "location_id", None))
    level = _lock_level(db, item.id, location.id)
    get_project(db, data.project_id)
    if data.boq_item_id is not None:
        boq_item = db.get(BoqItem, data.boq_item_id)
        if boq_item is None or boq_item.project_id != data.project_id:
            raise ValidationFailedError("BOQ item does not exist in this project")
    # Checked against the location, not the company: material in the yard
    # cannot be issued from a site store that does not hold it.
    if data.quantity > level.quantity:
        raise ConflictError(
            f"Insufficient stock at {location.name}: only {level.quantity} "
            f"{item.unit} there"
        )

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
    accounting.post_cost_entry(db, entry)

    item.qty_on_hand -= data.quantity  # WAC unchanged on issue
    level.quantity -= data.quantity

    # A tracked item issues from specific lots, so the ledger records which
    # ones — that link is what makes a recall answerable later. One movement
    # per lot keeps each row's quantity true to a single batch.
    from app.common.enums import TrackingMode

    if item.tracking_mode != TrackingMode.none:
        taken = _consume_batches(
            db, item, location, data.quantity, getattr(data, "batch_id", None)
        )
        for index, (batch, portion) in enumerate(taken):
            db.add(
                StockMovement(
                    stock_item_id=item.id,
                    location_id=location.id,
                    batch_id=batch.id,
                    doc_number=doc if index == 0 else f"{doc}-{index + 1}",
                    movement_type=StockMovementType.issue,
                    movement_date=when,
                    quantity=-portion,
                    unit_cost=item.unit_cost,
                    project_id=data.project_id,
                    boq_item_id=data.boq_item_id,
                    cost_entry_id=entry.id,
                    notes=data.notes,
                    created_by=user_id,
                )
            )
    else:
        db.add(
            StockMovement(
                stock_item_id=item.id,
                location_id=location.id,
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
    """Correct the book, or record a loss.

    Stock going out has to say why. Wastage, breakage, theft and a miscount
    all reduce the same number and each needs a different response, so an
    undifferentiated adjustment hides the only thing worth knowing. Stock
    going *in* needs no reason: adding to the book is a correction by
    definition, because nothing was lost.
    """
    if data.quantity == 0:
        raise ValidationFailedError("Adjustment quantity cannot be zero")
    reason = getattr(data, "loss_reason", None)
    if data.quantity < 0 and reason is None:
        raise ValidationFailedError(
            "Say why the stock is going out. Wastage, breakage, theft and a bad "
            "count each need a different answer, and one adjustment figure "
            "cannot tell them apart."
        )
    if data.quantity > 0:
        reason = StockLossReason.correction
    item = _lock_item(db, item_id)
    location = _resolve_location(db, getattr(data, "location_id", None))
    level = _lock_level(db, item.id, location.id)
    if level.quantity + data.quantity < 0:
        raise ConflictError(
            f"Adjustment would take {location.name} below zero "
            f"(holds {level.quantity})"
        )
    item.qty_on_hand += data.quantity  # WAC unchanged; quantity corrections only
    level.quantity += data.quantity
    db.add(
        StockMovement(
            stock_item_id=item.id,
            location_id=location.id,
            doc_number=next_doc_number(db, StockMovement, "ADJ"),
            movement_type=StockMovementType.adjustment,
            movement_date=data.movement_date or date.today(),
            quantity=data.quantity,
            unit_cost=item.unit_cost,
            loss_reason=reason,
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
    read.location_name = stocktake.location.name if stocktake.location else None
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

    # A count happens at one place: you cannot walk two stores at once, and
    # the expected quantity has to be what is on THAT shelf.
    location = _resolve_location(db, getattr(data, "location_id", None))

    query = select(StockItem).where(StockItem.is_active.is_(True))
    if data.stock_item_ids:
        query = query.where(StockItem.id.in_(data.stock_item_ids))
    if data.category:
        query = query.where(StockItem.category == data.category)
    items = list(db.scalars(query.order_by(StockItem.code)))
    if not items:
        raise ValidationFailedError("No stock items match this stocktake")

    held = {
        row.stock_item_id: row.quantity
        for row in db.scalars(
            select(StockLevel).where(StockLevel.location_id == location.id)
        )
    }
    stocktake = Stocktake(
        doc_number=next_doc_number(db, Stocktake, "STK"),
        location_id=location.id,
        count_date=data.count_date or date.today(),
        notes=data.notes,
        created_by=user_id,
        lines=[
            StocktakeLine(
                stock_item_id=item.id,
                expected_quantity=held.get(item.id, Decimal("0")),
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
                location_id=stocktake.location_id,
                quantity=variance,
                movement_date=stocktake.count_date,
                # A count variance is a correction by definition: it is the
                # book being brought to what is actually on the shelf. Where
                # the difference went is a separate question, and guessing at
                # it here would put invented wastage into the loss report.
                loss_reason=StockLossReason.correction,
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


# --- Locations ---------------------------------------------------------------


def location_read(db: Session, location: StockLocation):
    from app.modules.inventory.schemas import StockLocationRead

    read = StockLocationRead.model_validate(location)
    read.project_name = location.project.name if location.project else None
    rows = db.execute(
        select(func.count(), func.coalesce(func.sum(StockLevel.quantity * StockItem.unit_cost), 0))
        .select_from(StockLevel)
        .join(StockItem, StockItem.id == StockLevel.stock_item_id)
        .where(StockLevel.location_id == location.id, StockLevel.quantity != 0)
    ).first()
    read.item_count = rows[0] if rows else 0
    read.stock_value = (rows[1] if rows else Decimal("0")).quantize(CENT)
    return read


def list_locations(db: Session, active_only: bool = False) -> list[StockLocation]:
    query = select(StockLocation).options(joinedload(StockLocation.project))
    if active_only:
        query = query.where(StockLocation.is_active.is_(True))
    return list(db.scalars(query.order_by(StockLocation.code)))


def create_location(db: Session, data, created_by: uuid.UUID) -> StockLocation:
    if db.scalar(select(StockLocation).where(StockLocation.code == data.code)):
        raise ConflictError("A location with this code already exists")
    if data.project_id is not None:
        get_project(db, data.project_id)
    location = StockLocation(**data.model_dump(), created_by=created_by)
    db.add(location)
    db.flush()
    return location


def update_location(db: Session, location_id: uuid.UUID, data) -> StockLocation:
    location = get_location(db, location_id)
    updates = data.model_dump(exclude_unset=True)
    if (
        "code" in updates
        and updates["code"] != location.code
        and db.scalar(select(StockLocation).where(StockLocation.code == updates["code"]))
    ):
        raise ConflictError("A location with this code already exists")
    if updates.get("is_active") is False:
        if location.is_default:
            raise ConflictError("The default location cannot be deactivated")
        holding = db.scalar(
            select(func.count())
            .select_from(StockLevel)
            .where(StockLevel.location_id == location.id, StockLevel.quantity != 0)
        ) or 0
        if holding:
            raise ConflictError(
                f"{location.name} still holds {holding} item(s) — transfer them out first"
            )
    for field, value in updates.items():
        setattr(location, field, value)
    return location


def item_levels(db: Session, item_id: uuid.UUID):
    """Where this item actually is, so a total of 40 does not hide that all of
    it sits at the wrong site."""
    from app.modules.inventory.schemas import StockLevelRead

    item = get_item(db, item_id)
    rows = db.execute(
        select(StockLevel, StockLocation)
        .join(StockLocation, StockLocation.id == StockLevel.location_id)
        .where(StockLevel.stock_item_id == item_id, StockLevel.quantity != 0)
        .order_by(StockLocation.code)
    ).all()
    return [
        StockLevelRead(
            location_id=location.id,
            location_code=location.code,
            location_name=location.name,
            quantity=level.quantity,
            value=(level.quantity * item.unit_cost).quantize(CENT),
        )
        for level, location in rows
    ]


# --- Transfers ---------------------------------------------------------------


def list_transfers(db: Session, page: int, page_size: int, location_id=None):
    from app.modules.inventory.models import StockTransfer

    query = select(StockTransfer).options(
        joinedload(StockTransfer.stock_item),
        joinedload(StockTransfer.from_location),
        joinedload(StockTransfer.to_location),
    )
    if location_id is not None:
        query = query.where(
            (StockTransfer.from_location_id == location_id)
            | (StockTransfer.to_location_id == location_id)
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(
        db.scalars(
            query.order_by(StockTransfer.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return rows, total


def transfer_read(transfer):
    from app.modules.inventory.schemas import StockTransferRead

    read = StockTransferRead.model_validate(transfer)
    if transfer.stock_item:
        read.item_code = transfer.stock_item.code
        read.item_name = transfer.stock_item.name
    if transfer.from_location:
        read.from_location_name = transfer.from_location.name
    if transfer.to_location:
        read.to_location_name = transfer.to_location.name
    read.value = (transfer.quantity * transfer.unit_cost).quantize(CENT)
    return read


def transfer_stock(db: Session, data, user_id: uuid.UUID):
    """Move material between locations.

    Posts a matched pair of ledger rows so the company total is unchanged and
    both locations reconcile. No cost entry: moving our own stock between our
    own stores spends nothing — cost reaches a project only on issue.
    """
    from app.modules.inventory.models import StockTransfer

    if data.from_location_id == data.to_location_id:
        raise ValidationFailedError("Source and destination must be different")

    item = _lock_item(db, data.stock_item_id)
    source = get_location(db, data.from_location_id)
    destination = get_location(db, data.to_location_id)
    if not destination.is_active:
        raise ValidationFailedError(f"{destination.name} is not active")

    # Lock in a stable order so two opposing transfers cannot deadlock
    first, second = sorted([source.id, destination.id], key=str)
    levels = {
        first: _lock_level(db, item.id, first),
        second: _lock_level(db, item.id, second),
    }
    from_level, to_level = levels[source.id], levels[destination.id]

    if data.quantity > from_level.quantity:
        raise ConflictError(
            f"Insufficient stock at {source.name}: only {from_level.quantity} "
            f"{item.unit} there"
        )

    when = data.transfer_date or date.today()
    doc = next_doc_number(db, StockTransfer, "TRF")
    transfer = StockTransfer(
        doc_number=doc,
        stock_item_id=item.id,
        from_location_id=source.id,
        to_location_id=destination.id,
        transfer_date=when,
        quantity=data.quantity,
        unit_cost=item.unit_cost,
        notes=data.notes,
        created_by=user_id,
    )
    db.add(transfer)

    from_level.quantity -= data.quantity
    to_level.quantity += data.quantity
    # Company total is untouched: the pair nets to zero.
    for location_id, signed, suffix in (
        (source.id, -data.quantity, "O"),
        (destination.id, data.quantity, "I"),
    ):
        db.add(
            StockMovement(
                stock_item_id=item.id,
                location_id=location_id,
                doc_number=f"{doc}-{suffix}",
                movement_type=StockMovementType.transfer,
                movement_date=when,
                quantity=signed,
                unit_cost=item.unit_cost,
                reference=doc,
                notes=data.notes,
                created_by=user_id,
            )
        )
    db.flush()
    return transfer


# --- Batches, expiry and recall ----------------------------------------------


def batch_read(batch, item=None):
    from app.modules.inventory.schemas import StockBatchRead

    item = item or batch.stock_item
    read = StockBatchRead.model_validate(batch)
    if item:
        read.item_code, read.item_name = item.code, item.name
        read.value = (batch.quantity * item.unit_cost).quantize(CENT)
    if batch.location:
        read.location_name = batch.location.name
    if batch.expiry_date:
        read.days_to_expiry = (batch.expiry_date - date.today()).days
        read.is_expired = read.days_to_expiry < 0
        warn_within = item.expiry_warning_days if item else 30
        read.is_expiring_soon = not read.is_expired and read.days_to_expiry <= warn_within
    return read


def list_batches(db: Session, item_id: uuid.UUID | None = None, location_id=None,
                 include_empty: bool = False):
    query = select(StockBatch).options(
        joinedload(StockBatch.stock_item), joinedload(StockBatch.location)
    )
    if item_id is not None:
        query = query.where(StockBatch.stock_item_id == item_id)
    if location_id is not None:
        query = query.where(StockBatch.location_id == location_id)
    if not include_empty:
        query = query.where(StockBatch.quantity > 0)
    rows = db.scalars(
        query.order_by(StockBatch.expiry_date.is_(None), StockBatch.expiry_date)
    )
    return [batch_read(b) for b in rows]


def expiry_report(db: Session):
    """What is past its date, and what is about to be.

    Only batches still holding stock: an expired lot that has been fully used
    is history, not a problem to act on.
    """
    from app.modules.inventory.schemas import ExpiryReport

    batches = db.scalars(
        select(StockBatch)
        .options(joinedload(StockBatch.stock_item), joinedload(StockBatch.location))
        .where(StockBatch.quantity > 0, StockBatch.expiry_date.is_not(None))
        .order_by(StockBatch.expiry_date)
    )
    expired, soon = [], []
    for batch in batches:
        read = batch_read(batch)
        if read.is_expired:
            expired.append(read)
        elif read.is_expiring_soon:
            soon.append(read)
    return ExpiryReport(
        expired=expired,
        expiring_soon=soon,
        expired_value=sum((b.value for b in expired), Decimal("0")).quantize(CENT),
        expiring_value=sum((b.value for b in soon), Decimal("0")).quantize(CENT),
    )


def recall_trace(db: Session, batch_number: str):
    """Everywhere one lot went.

    The question a recall actually asks is "which jobs got this cement?" — so
    this returns both what is still on the shelf and every issue that took it
    to a project, gathered across locations.
    """
    from app.modules.inventory.schemas import RecallTrace, RecallUsage
    from app.modules.projects.models import Project

    batches = list(
        db.scalars(
            select(StockBatch)
            .options(joinedload(StockBatch.stock_item), joinedload(StockBatch.location))
            .where(StockBatch.batch_number == batch_number)
        )
    )
    if not batches:
        raise NotFoundError(f"No batch numbered {batch_number}")

    batch_ids = [b.id for b in batches]
    rows = db.execute(
        select(StockMovement, StockLocation.name, Project.id, Project.name)
        .outerjoin(StockLocation, StockLocation.id == StockMovement.location_id)
        .outerjoin(Project, Project.id == StockMovement.project_id)
        .where(
            StockMovement.batch_id.in_(batch_ids),
            StockMovement.movement_type == StockMovementType.issue,
        )
        .order_by(StockMovement.movement_date.desc())
    ).all()

    usages = [
        RecallUsage(
            movement_id=movement.id,
            doc_number=movement.doc_number,
            movement_date=movement.movement_date,
            quantity=abs(movement.quantity),
            location_name=location_name,
            project_id=project_id,
            project_name=project_name,
        )
        for movement, location_name, project_id, project_name in rows
    ]
    return RecallTrace(
        batch_number=batch_number,
        batches=[batch_read(b) for b in batches],
        remaining_quantity=sum((b.quantity for b in batches), Decimal("0")),
        issued_quantity=sum((u.quantity for u in usages), Decimal("0")),
        usages=usages,
    )


def loss_report(db: Session, start: date, end: date, project_id=None) -> dict:
    """What left the store without reaching a job, and why.

    Corrections are counted and reported but never added to the total. The
    stock was not there to begin with, so nothing was lost — including them
    would inflate a wastage figure with somebody's arithmetic, and wastage is
    a number people are meant to act on.
    """
    from app.common.enums import REAL_LOSSES

    rows = db.execute(
        select(StockMovement, StockItem)
        .join(StockItem, StockItem.id == StockMovement.stock_item_id)
        .where(
            StockMovement.movement_type == StockMovementType.adjustment,
            StockMovement.quantity < 0,
            StockMovement.movement_date >= start,
            StockMovement.movement_date <= end,
        )
        .order_by(StockMovement.movement_date.desc())
    ).all()

    by_reason: dict = {}
    by_item: dict = {}
    total = Decimal("0")
    corrections = Decimal("0")

    for movement, item in rows:
        reason = movement.loss_reason or StockLossReason.correction
        quantity = abs(Decimal(movement.quantity))
        value = (quantity * Decimal(movement.unit_cost or item.unit_cost or 0)).quantize(
            Decimal("0.01")
        )

        bucket = by_reason.setdefault(
            reason.value,
            {"reason": reason.value, "movements": 0, "quantity": Decimal("0"),
             "value": Decimal("0")},
        )
        bucket["movements"] += 1
        bucket["quantity"] += quantity
        bucket["value"] += value

        if reason in REAL_LOSSES:
            total += value
            row = by_item.setdefault(
                item.id,
                {
                    "stock_item_id": item.id,
                    "code": item.code,
                    "name": item.name,
                    "unit": item.unit,
                    "quantity": Decimal("0"),
                    "value": Decimal("0"),
                    "reasons": [],
                },
            )
            row["quantity"] += quantity
            row["value"] += value
            if reason.value not in row["reasons"]:
                row["reasons"].append(reason.value)
        else:
            corrections += value

    return {
        "start": start,
        "end": end,
        "total_value": total.quantize(Decimal("0.01")),
        "correction_value": corrections.quantize(Decimal("0.01")),
        "by_reason": sorted(by_reason.values(), key=lambda r: -r["value"]),
        "by_item": sorted(by_item.values(), key=lambda r: -r["value"]),
    }
