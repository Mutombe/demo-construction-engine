"""What a supplier is actually like to deal with.

Four things decide whether to use somebody again, and they are not all knowable
the same way.

    delivery         in the dates already recorded
    price            in how their bids sat against the others on the same RFQ
    quality          only the person who took the delivery knows
    professionalism  the same

The first two are derived and cost nobody any typing. The last two cannot be
derived from anything and are the reason this module exists at all: without
somewhere to put them, the only supplier knowledge a company has walks out
with whoever leaves.

Every figure returns `None` rather than a number when there is nothing behind
it. A supplier with one delivery does not have a 100% record, and a scorecard
that says otherwise is worse than one that admits it does not know yet.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import PoStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.procurement.models import (
    PurchaseOrder,
    Quote,
    Supplier,
    SupplierAssessment,
)

ONE = Decimal("0.1")

# Below this there is not enough history for a figure to mean anything, and it
# is reported as provisional rather than presented as a verdict.
CONFIDENT_AFTER = 3


def record_assessment(db: Session, purchase_order_id: uuid.UUID, data, user=None):
    """Judge one delivery.

    Tied to the order rather than to the supplier, so every score can be traced
    back to a specific thing that arrived on a specific day. A rating nobody can
    trace is a rumour.
    """
    order = db.get(PurchaseOrder, purchase_order_id)
    if order is None:
        raise NotFoundError("Purchase order not found")
    if order.status is not PoStatus.received:
        raise ConflictError(
            "Nothing has been delivered on this order yet, so there is nothing to judge"
        )

    for field in ("quality", "professionalism"):
        value = getattr(data, field, None)
        if value is not None and not 1 <= int(value) <= 5:
            raise ValidationFailedError(f"{field} is scored from one to five")

    existing = db.scalar(
        select(SupplierAssessment).where(
            SupplierAssessment.purchase_order_id == purchase_order_id
        )
    )
    if existing is not None:
        # Revising a judgement is fine; adding a second one for the same
        # delivery is not, because it would count twice in the average.
        existing.quality = data.quality
        existing.professionalism = data.professionalism
        existing.would_use_again = data.would_use_again
        existing.notes = data.notes
        db.flush()
        return existing

    assessment = SupplierAssessment(
        supplier_id=order.supplier_id,
        purchase_order_id=order.id,
        assessed_on=getattr(data, "assessed_on", None) or date.today(),
        quality=data.quality,
        professionalism=data.professionalism,
        would_use_again=data.would_use_again,
        notes=data.notes,
        created_by=getattr(user, "id", None),
    )
    db.add(assessment)
    db.flush()
    return assessment


def list_assessments(db: Session, supplier_id: uuid.UUID):
    return list(
        db.scalars(
            select(SupplierAssessment)
            .where(SupplierAssessment.supplier_id == supplier_id)
            .order_by(SupplierAssessment.assessed_on.desc())
        )
    )


def _mean(values: list) -> Decimal | None:
    numbers = [Decimal(v) for v in values if v is not None]
    if not numbers:
        return None
    return (sum(numbers) / len(numbers)).quantize(ONE)


def price_competitiveness(db: Session, supplier_id: uuid.UUID) -> dict:
    """How their bids sat against everybody else's on the same enquiry.

    This is what "fair price" actually means. Comparing a supplier's price to
    their own quote only says whether they are honest; comparing it to the
    other bids for the same work says whether they are dear, and that is the
    question being asked.

    Only enquiries with at least two bids count. A price is not high or low on
    its own — it is only high or low against something.
    """
    rows = db.execute(
        select(Quote.rfq_id, Quote.supplier_id, Quote.total_amount)
    ).all()

    by_rfq: dict = {}
    for rfq_id, sid, total in rows:
        if total is None or Decimal(total) <= 0:
            continue
        by_rfq.setdefault(rfq_id, []).append((sid, Decimal(total)))

    deltas: list[Decimal] = []
    contested = 0
    won = 0
    for bids in by_rfq.values():
        if len(bids) < 2:
            continue
        ours = [total for sid, total in bids if sid == supplier_id]
        if not ours:
            continue
        contested += 1
        mine = ours[0]
        best = min(total for _sid, total in bids)
        if mine == best:
            won += 1
        # Against the cheapest bid, as a percentage. Zero means they were the
        # cheapest; twenty means they were a fifth dearer than the best offer.
        deltas.append(((mine - best) / best * 100).quantize(ONE))

    return {
        "contested_enquiries": contested,
        "lowest_bid_count": won,
        "avg_above_lowest_pct": _mean(deltas),
    }


def supplier_rating(db: Session, supplier_id: uuid.UUID) -> dict:
    """The four dimensions, plus an overall only where all four are known.

    The overall is deliberately withheld unless every part of it has evidence.
    Averaging three knowns and one blank produces a number that looks like a
    verdict and is not one.
    """
    from app.modules.procurement import service as procurement

    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise NotFoundError("Supplier not found")

    assessments = list_assessments(db, supplier_id)
    quality = _mean([a.quality for a in assessments])
    professionalism = _mean([a.professionalism for a in assessments])

    scorecard = procurement.supplier_scorecard(db, supplier_id)
    on_time_pct = getattr(scorecard, "on_time_pct", None)
    # On a five-point scale so it sits beside the judged scores rather than
    # being read as a different kind of number.
    delivery = (
        (Decimal(on_time_pct) / 20).quantize(ONE) if on_time_pct is not None else None
    )

    price = price_competitiveness(db, supplier_id)
    above = price["avg_above_lowest_pct"]
    if above is None:
        price_score = None
    else:
        # Level with the cheapest bid is five; a fifth dearer is one. Beyond
        # that it floors rather than going negative.
        price_score = max(Decimal("1.0"), Decimal("5.0") - (Decimal(above) / 5)).quantize(ONE)

    parts = [quality, professionalism, delivery, price_score]
    overall = _mean(parts) if all(p is not None for p in parts) else None

    would_use = [a.would_use_again for a in assessments if a.would_use_again is not None]
    judged = len([a for a in assessments if a.quality or a.professionalism])

    return {
        "supplier_id": supplier_id,
        "supplier_name": supplier.name,
        "quality": quality,
        "professionalism": professionalism,
        "delivery": delivery,
        "price": price_score,
        "overall": overall,
        # What the numbers are built on, so nobody reads four assessments as a
        # settled reputation.
        "assessments": len(assessments),
        "judged_deliveries": judged,
        "contested_enquiries": price["contested_enquiries"],
        "lowest_bid_count": price["lowest_bid_count"],
        "avg_above_lowest_pct": above,
        "on_time_pct": on_time_pct,
        "would_use_again_pct": (
            (Decimal(sum(1 for w in would_use if w)) * 100 / len(would_use)).quantize(ONE)
            if would_use
            else None
        ),
        # Below this there is history but not enough of it to argue from.
        "provisional": len(assessments) < CONFIDENT_AFTER,
    }


def ratings_for(db: Session, supplier_ids: list[uuid.UUID]) -> dict:
    """Ratings for a set of suppliers at once, for a bid comparison.

    The whole point of keeping this history is that it is in front of somebody
    at the moment they are choosing, rather than filed where it gets looked up
    after the order has gone out.
    """
    return {sid: supplier_rating(db, sid) for sid in set(supplier_ids)}


def leaderboard(db: Session) -> list[dict]:
    """Every supplier that has been dealt with, worst last."""
    rows = []
    for supplier in db.scalars(
        select(Supplier).where(Supplier.is_active.is_(True)).order_by(Supplier.name)
    ):
        rating = supplier_rating(db, supplier.id)
        if not rating["assessments"] and rating["on_time_pct"] is None:
            # Never traded with. Not a bad supplier, just an unknown one, and
            # ranking them among the judged would imply otherwise.
            continue
        rows.append(rating)
    rows.sort(
        key=lambda r: (r["overall"] is None, -(r["overall"] or Decimal("0"))),
    )
    return rows


def unassessed_deliveries(db: Session, limit: int = 50) -> list[dict]:
    """Deliveries nobody has judged yet.

    Left to memory this never happens: the person who took the delivery is on
    site the next morning and the order is closed. A short list of what is
    outstanding is the only thing that makes the history get written down.
    """
    rows = db.execute(
        select(PurchaseOrder, Supplier)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .outerjoin(
            SupplierAssessment,
            SupplierAssessment.purchase_order_id == PurchaseOrder.id,
        )
        .where(
            PurchaseOrder.status == PoStatus.received,
            SupplierAssessment.id.is_(None),
        )
        .order_by(PurchaseOrder.received_date.desc())
        .limit(limit)
    ).all()

    return [
        {
            "purchase_order_id": order.id,
            "doc_number": order.doc_number,
            "supplier_id": supplier.id,
            "supplier_name": supplier.name,
            "received_date": order.received_date,
            "total_amount": Decimal(order.total_amount or 0),
        }
        for order, supplier in rows
    ]
