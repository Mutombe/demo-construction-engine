"""Inventory analytics and demand forecasting.

Every number here is derived from movements the system already records, so
nothing depends on new data entry. Where a figure rests on an assumption —
carrying-cost rate, lead time when a supplier has no history — the assumption
is a parameter with a stated default rather than a hidden constant.

Deliberately conservative: an item with too little history to judge reports
its metrics as null instead of a confident-looking number computed from two
data points.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import PoStatus, StockMovementType
from app.modules.inventory.models import StockItem, StockMovement

CENT = Decimal("0.01")
ZERO = Decimal("0")
DAYS_IN_YEAR = Decimal("365")

# Industry rule of thumb: storage, insurance, tied-up capital and obsolescence
# come to roughly a fifth to a quarter of stock value per year.
DEFAULT_CARRYING_RATE = Decimal("0.25")
DEFAULT_LEAD_TIME_DAYS = 14
# Below this many issues we have a coincidence, not a consumption rate
MIN_ISSUES_TO_FORECAST = 2


def _movement_totals(db: Session, since: date):
    """Issued, received and net change per item over the window."""
    rows = db.execute(
        select(
            StockMovement.stock_item_id,
            # FILTER belongs on the aggregate, not on abs()
            func.coalesce(
                func.sum(func.abs(StockMovement.quantity)).filter(
                    StockMovement.movement_type == StockMovementType.issue
                ),
                0,
            ),
            func.coalesce(func.sum(StockMovement.quantity), 0),
            func.count().filter(StockMovement.movement_type == StockMovementType.issue),
        )
        .where(StockMovement.movement_date >= since)
        .group_by(StockMovement.stock_item_id)
    ).all()
    return {
        item_id: {"issued": issued, "net": net, "issue_count": issue_count}
        for item_id, issued, net, issue_count in rows
    }


def _last_dates(db: Session):
    """When each item last moved at all, and last actually went out."""
    last_any = dict(
        db.execute(
            select(StockMovement.stock_item_id, func.max(StockMovement.movement_date))
            .group_by(StockMovement.stock_item_id)
        ).all()
    )
    last_issue = dict(
        db.execute(
            select(StockMovement.stock_item_id, func.max(StockMovement.movement_date))
            .where(StockMovement.movement_type == StockMovementType.issue)
            .group_by(StockMovement.stock_item_id)
        ).all()
    )
    return last_any, last_issue


def average_lead_time_days(db: Session) -> int:
    """How long deliveries actually take, from orders already received.

    Company-wide rather than per supplier: a reorder point is about how long
    the shelf must last, and the buyer may not be the last supplier used.
    """
    from app.modules.procurement.models import PurchaseOrder

    rows = db.scalars(
        select(PurchaseOrder).where(
            PurchaseOrder.status == PoStatus.received,
            PurchaseOrder.received_date.is_not(None),
        )
    ).all()
    gaps = [
        (po.received_date - po.order_date).days
        for po in rows
        if po.received_date and po.order_date and po.received_date >= po.order_date
    ]
    if not gaps:
        return DEFAULT_LEAD_TIME_DAYS
    return max(1, round(sum(gaps) / len(gaps)))


def inventory_analytics(
    db: Session,
    days: int = 90,
    carrying_rate: Decimal = DEFAULT_CARRYING_RATE,
    dead_after_days: int = 90,
):
    """Turnover, ageing, carrying cost and dead stock per item."""
    from app.modules.inventory.schemas import (
        InventoryAnalytics,
        InventoryAnalyticsRow,
    )

    today = date.today()
    since = today - timedelta(days=days)
    totals = _movement_totals(db, since)
    last_any, last_issue = _last_dates(db)

    items = list(
        db.scalars(select(StockItem).where(StockItem.is_active.is_(True)).order_by(StockItem.code))
    )

    rows: list[InventoryAnalyticsRow] = []
    total_value = ZERO
    total_dead_value = ZERO
    total_issued_value = ZERO
    for item in items:
        stats = totals.get(item.id, {"issued": ZERO, "net": ZERO, "issue_count": 0})
        closing = item.qty_on_hand
        # Opening is recoverable: closing minus the net of everything that
        # happened, which makes the average real rather than assumed.
        opening = closing - stats["net"]
        average_qty = (opening + closing) / 2
        average_value = (average_qty * item.unit_cost).quantize(CENT)
        closing_value = (closing * item.unit_cost).quantize(CENT)
        issued_value = (stats["issued"] * item.unit_cost).quantize(CENT)

        # Annualised so the ratio reads the same whatever window is chosen
        turnover = None
        days_on_hand = None
        if average_value > 0 and issued_value > 0:
            exact = (issued_value / average_value) * (DAYS_IN_YEAR / Decimal(days))
            turnover = exact.quantize(Decimal("0.01"))
            # Derived from the unrounded ratio so display rounding does not
            # compound into the day count
            days_on_hand = int((DAYS_IN_YEAR / exact).to_integral_value())

        since_issue = (
            (today - last_issue[item.id]).days if item.id in last_issue else None
        )
        # Dead means value sitting still: nothing issued for a long time while
        # stock remains. An empty bin is not dead stock, it is just empty.
        is_dead = closing > 0 and (since_issue is None or since_issue >= dead_after_days)

        carrying_cost = (average_value * carrying_rate).quantize(CENT)

        rows.append(
            InventoryAnalyticsRow(
                stock_item_id=item.id,
                code=item.code,
                name=item.name,
                category=item.category,
                unit=item.unit,
                qty_on_hand=closing,
                stock_value=closing_value,
                average_stock_value=average_value,
                issued_quantity=stats["issued"],
                issued_value=issued_value,
                turnover_ratio=turnover,
                days_on_hand=days_on_hand,
                annual_carrying_cost=carrying_cost,
                last_movement=last_any.get(item.id),
                last_issue=last_issue.get(item.id),
                days_since_issue=since_issue,
                is_dead_stock=is_dead,
            )
        )
        total_value += closing_value
        total_issued_value += issued_value
        if is_dead:
            total_dead_value += closing_value

    return InventoryAnalytics(
        window_days=days,
        carrying_rate=carrying_rate,
        total_stock_value=total_value.quantize(CENT),
        total_issued_value=total_issued_value.quantize(CENT),
        annual_carrying_cost=(total_value * carrying_rate).quantize(CENT),
        dead_stock_value=total_dead_value.quantize(CENT),
        dead_stock_count=sum(1 for r in rows if r.is_dead_stock),
        rows=rows,
    )


def demand_forecast(db: Session, days: int = 90, safety_days: int = 7):
    """What each item is being used at, and when it runs out.

    Consumption is a plain moving average over the window. Deliberately not
    something cleverer: with this much history a seasonal model would be
    fitting noise, and a wrong number that looks sophisticated is worse than a
    simple one people can sanity-check.
    """
    from app.modules.inventory.schemas import DemandForecast, DemandForecastRow

    today = date.today()
    since = today - timedelta(days=days)
    totals = _movement_totals(db, since)
    lead_time = average_lead_time_days(db)

    items = list(
        db.scalars(select(StockItem).where(StockItem.is_active.is_(True)).order_by(StockItem.code))
    )

    rows: list[DemandForecastRow] = []
    for item in items:
        stats = totals.get(item.id, {"issued": ZERO, "issue_count": 0})
        issue_count = stats["issue_count"]
        # Too few issues is a coincidence, not a rate
        if issue_count < MIN_ISSUES_TO_FORECAST or stats["issued"] <= 0:
            rows.append(
                DemandForecastRow(
                    stock_item_id=item.id,
                    code=item.code,
                    name=item.name,
                    unit=item.unit,
                    qty_on_hand=item.qty_on_hand,
                    reorder_level=item.reorder_level,
                    lead_time_days=lead_time,
                    has_enough_history=False,
                )
            )
            continue

        daily = (Decimal(stats["issued"]) / Decimal(days)).quantize(Decimal("0.001"))
        cover_days = (
            int((item.qty_on_hand / daily).to_integral_value()) if daily > 0 else None
        )
        # Enough to last the delivery, plus a buffer for a bad week
        suggested_point = (daily * Decimal(lead_time + safety_days)).quantize(
            Decimal("0.001")
        )
        # Order about a month of use at a time, never less than the shortfall
        suggested_qty = max(
            (daily * Decimal("30")).quantize(Decimal("0.001")),
            (suggested_point - item.qty_on_hand).quantize(Decimal("0.001")),
        )
        rows.append(
            DemandForecastRow(
                stock_item_id=item.id,
                code=item.code,
                name=item.name,
                unit=item.unit,
                qty_on_hand=item.qty_on_hand,
                reorder_level=item.reorder_level,
                lead_time_days=lead_time,
                has_enough_history=True,
                daily_usage=daily,
                monthly_usage=(daily * Decimal("30")).quantize(Decimal("0.001")),
                days_of_cover=cover_days,
                projected_stockout=(
                    today + timedelta(days=cover_days) if cover_days is not None else None
                ),
                suggested_reorder_point=suggested_point,
                suggested_order_quantity=max(suggested_qty, ZERO),
                # The reorder level someone typed may not match reality
                reorder_level_is_low=item.reorder_level < suggested_point,
                needs_ordering=item.qty_on_hand <= suggested_point,
            )
        )

    at_risk = [r for r in rows if r.needs_ordering]
    return DemandForecast(
        window_days=days,
        lead_time_days=lead_time,
        safety_days=safety_days,
        rows=rows,
        needs_ordering_count=len(at_risk),
        forecastable_count=sum(1 for r in rows if r.has_enough_history),
    )


def item_consumption_trend(db: Session, item_id: uuid.UUID, months: int = 6):
    """Monthly issue quantity, so a trend is visible rather than inferred."""
    from app.modules.inventory.schemas import ConsumptionMonth, ConsumptionTrend

    today = date.today()
    keys: list[str] = []
    cursor = date(today.year, today.month, 1)
    for _ in range(months):
        keys.append(cursor.strftime("%Y-%m"))
        previous_last = cursor - timedelta(days=1)
        cursor = date(previous_last.year, previous_last.month, 1)
    keys.reverse()
    window_start = date(int(keys[0][:4]), int(keys[0][5:]), 1)

    buckets = dict.fromkeys(keys, ZERO)
    movements = db.scalars(
        select(StockMovement).where(
            StockMovement.stock_item_id == item_id,
            StockMovement.movement_type == StockMovementType.issue,
            StockMovement.movement_date >= window_start,
        )
    )
    for movement in movements:
        key = movement.movement_date.strftime("%Y-%m")
        if key in buckets:
            buckets[key] += abs(movement.quantity)

    return ConsumptionTrend(
        stock_item_id=item_id,
        months=[ConsumptionMonth(month=key, quantity=buckets[key]) for key in keys],
        total=sum(buckets.values(), ZERO),
    )
