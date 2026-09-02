"""Enough trading history for the supplier scorecard to mean anything.

    uv run python -m scripts.seed_procurement_history

A rating built on one delivery is not a rating, and a bid comparison with one
bidder shows nothing. This puts several enquiries out to the whole supplier
list, takes prices back from each, turns the winners into orders and delivers
them — some on time, some late — so every figure on the scorecard has real
history behind it.

The suppliers are given distinct characters on purpose. One is cheap and
unreliable, one is dear and excellent, one is unremarkable. That contrast is
the entire point of keeping the history: it is what makes the cheapest bid the
wrong answer sometimes.
"""

import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

import app.modules  # noqa: F401
from app.common.enums import PoStatus, UserRole
from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.boq.models import BoqItem, BoqSection
from app.modules.procurement import rating, service as procurement
from app.modules.procurement.models import PurchaseOrder, Quote, Rfq, Supplier
from app.modules.procurement.schemas import (
    AssessmentCreate,
    PoCreate,
    PoReceive,
    QuoteCreate,
    QuoteItemCreate,
    RfqCreate,
    RfqItemCreate,
)
from app.modules.projects.models import Project
from app.modules.users.models import User

TODAY = date.today()

# What each supplier is like, which is what the scorecard has to end up
# reproducing from the evidence rather than being told.
#
# (price multiplier against the keenest bid, days late, quality, professionalism)
CHARACTERS = [
    ("keen but careless", Decimal("1.00"), 6, 2, 2),
    ("dear and excellent", Decimal("1.22"), 0, 5, 5),
    ("middle of the road", Decimal("1.09"), 1, 4, 3),
    ("steady", Decimal("1.14"), 0, 4, 4),
]

ENQUIRIES = [
    ("Readymix concrete C25", "8400"),
    ("Reinforcement bar, cut and bent", "15600"),
    ("Facing brick and mortar", "9200"),
    ("Structural steel — beams", "24800"),
    ("Roof sheeting and flashings", "11400"),
    ("Electrical first-fix materials", "7300"),
    ("Plumbing and sanitaryware", "13900"),
    ("Timber and formwork ply", "6800"),
    ("Paint and surface preparation", "5400"),
    ("Aluminium windows", "18700"),
    ("Ceramic tiling", "8900"),
    ("Ironmongery and fixings", "4200"),
]

# Everything is dated inside the last two months. Earlier periods are closed,
# and a closed period refuses a posting rather than quietly changing accounts
# somebody has already reported on — which is the whole reason to close one.
WINDOW_DAYS = 50


def _admin(db):
    return db.scalar(select(User).where(User.role == UserRole.admin))


def _boq_item(db, project) -> BoqItem | None:
    return db.scalar(
        select(BoqItem)
        .join(BoqSection, BoqSection.id == BoqItem.section_id)
        .where(BoqSection.project_id == project.id)
        .limit(1)
    )


def seed_trading_history(db) -> None:
    admin = _admin(db)
    suppliers = list(db.scalars(select(Supplier).order_by(Supplier.name)))
    projects = list(db.scalars(select(Project).order_by(Project.code)))
    if len(suppliers) < 2 or not projects:
        print("history: need at least two suppliers and a project")
        return

    already = {
        title
        for title in db.scalars(select(Rfq.title))
    }

    made = {"rfqs": 0, "quotes": 0, "orders": 0, "received": 0}

    for index, (title, base) in enumerate(ENQUIRIES):
        if title in already:
            continue
        project = projects[index % len(projects)]
        item = _boq_item(db, project)
        if item is None:
            continue

        rfq = procurement.create_rfq(
            db,
            project.id,
            RfqCreate(title=title, items=[RfqItemCreate(boq_item_id=item.id)]),
            admin.id,
        )
        db.flush()
        procurement.issue_rfq(db, rfq.id)
        db.flush()
        made["rfqs"] += 1

        # Everybody prices it, at the level their character implies. Real
        # enquiries get a spread, and the spread is what makes a price
        # comparable at all.
        priced = []
        for offset, supplier in enumerate(suppliers):
            _name, multiplier, *_rest = CHARACTERS[offset % len(CHARACTERS)]
            # A little movement per enquiry, so nobody is mechanically cheapest
            # every single time.
            drift = Decimal("1") + (Decimal(index % 3) - 1) / 100
            total = (Decimal(base) * multiplier * drift).quantize(Decimal("0.01"))
            quote = procurement.create_quote(
                db,
                rfq.id,
                QuoteCreate(
                    supplier_id=supplier.id,
                    received_date=TODAY - timedelta(days=WINDOW_DAYS - index * 3),
                    items=[
                        QuoteItemCreate(
                            description=title,
                            unit="item",
                            quantity=Decimal("1"),
                            unit_price=total,
                        )
                    ],
                ),
                admin.id,
            )
            db.flush()
            priced.append((supplier, offset, total, quote))
            made["quotes"] += 1

        # The cheapest usually wins, but not always. Rotating the winner is
        # also the only way every supplier ends up with a record: a register
        # where one firm has all the history and the rest have none cannot
        # demonstrate a comparison.
        priced.sort(key=lambda row: row[2])
        winner = priced[index % len(priced)]
        supplier, offset, total, quote = winner
        _name, _multiplier, late, quality, professionalism = CHARACTERS[
            offset % len(CHARACTERS)
        ]

        procurement.accept_quote(db, quote.id)
        db.flush()

        expected = TODAY - timedelta(days=(WINDOW_DAYS - 6) - index * 3)
        order = procurement.create_po(
            db,
            project.id,
            PoCreate(quote_id=quote.id, expected_delivery=expected),
            admin.id,
        )
        db.flush()
        procurement.issue_po(db, order.id, admin.id)
        db.flush()
        made["orders"] += 1

        # The last enquiry stays out on order, so the screens show something
        # still owing rather than a perfectly closed history.
        if index == len(ENQUIRIES) - 1:
            continue

        procurement.receive_po(
            db,
            order.id,
            PoReceive(received_date=expected + timedelta(days=late)),
            admin.id,
        )
        db.flush()
        made["received"] += 1

        # Judged straight away, except one that is left for the outstanding
        # list — because in practice this is exactly what gets forgotten.
        if index % 4 != 3:
            rating.record_assessment(
                db,
                order.id,
                AssessmentCreate(
                    quality=quality,
                    professionalism=professionalism,
                    would_use_again=quality >= 3,
                    notes=(
                        "Delivered short, chased twice"
                        if quality <= 2
                        else "No issues"
                        if quality >= 4
                        else "Adequate"
                    ),
                ),
                admin,
            )

    print(
        f"history: {made['rfqs']} enquiries, {made['quotes']} bids, "
        f"{made['orders']} orders, {made['received']} delivered"
    )


def report(db) -> None:
    rows = rating.leaderboard(db)
    print(f"\nscorecard across {len(rows)} suppliers traded with:")
    for row in rows:
        overall = f"{row['overall']:.1f}" if row["overall"] is not None else "  — "
        above = (
            f"{row['avg_above_lowest_pct']:>5.1f}% over"
            if row["avg_above_lowest_pct"] is not None
            else "    no bids"
        )
        print(
            f"  {overall}  {row['supplier_name'][:26]:<26} "
            f"quality {row['quality'] or '-'}  "
            f"on time {row['on_time_pct'] or 0:.0f}%  {above}"
        )
    outstanding = rating.unassessed_deliveries(db)
    print(f"\n{len(outstanding)} deliveries still waiting to be judged")


def main() -> None:
    if settings.environment == "production":
        print("Refusing to run against production")
        sys.exit(1)

    db = SessionLocal()
    try:
        seed_trading_history(db)
        db.commit()
        report(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
