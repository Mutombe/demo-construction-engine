"""Fills the tables the commercial work added.

    uv run python -m scripts.seed_commercial

Run after `scripts.seed_fleet`, which puts the plant and the subcontract
packages there for these to hang off.

Everything goes through the real services, so the figures are what the rules
produce. That matters more here than elsewhere: a plant recharge and a
back-charge both post to the ledger, and hand-written rows would leave the
books saying something the code would never have said.

Idempotent, and each block commits on its own so a slow connection does not
throw away a completed one.
"""

import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

import app.modules  # noqa: F401
from app.common.enums import PlantCostingMode, UserRole
from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.company.models import CompanySettings
from app.modules.procurement import supplier_portal
from app.modules.procurement.models import (
    PurchaseOrder,
    Supplier,
    SupplierInvoice,
)
from app.modules.subcontracts import commercial
from app.modules.subcontracts.models import BackCharge, Subcontract, SubcontractVariation
from app.modules.subcontracts.schemas import BackChargeCreate, VariationCreate
from app.modules.users.models import User

TODAY = date.today()


def _admin(db):
    return db.scalar(select(User).where(User.role == UserRole.admin))


# --- Variations --------------------------------------------------------------
#
# One approved, one still pending and one omission, so the screen shows all
# three states rather than a single tidy row.

VARIATIONS = [
    ("Additional ridge flashing to the north elevation", "8400", "approved", "R. Ncube"),
    ("Upgrade to powder-coated fixings throughout", "12750", "pending", "T. Marimo"),
    ("Rooflights omitted from the store block", "-6200", "approved", "R. Ncube"),
    ("Extra scaffold lift for the gable", "3100", "pending", "S. Chikwanha"),
]


def seed_variations(db) -> None:
    if db.scalar(select(func.count()).select_from(SubcontractVariation)):
        print("variations: already instructed")
        return

    admin = _admin(db)
    contracts = [
        c
        for c in db.scalars(select(Subcontract).order_by(Subcontract.doc_number))
        if c.status.value != "draft"
    ]
    if not contracts:
        print("variations: no live package to instruct against")
        return

    approved = 0
    for index, (title, amount, status, who) in enumerate(VARIATIONS):
        contract = contracts[index % len(contracts)]
        variation = commercial.create_variation(
            db,
            contract.id,
            VariationCreate(
                title=title,
                amount=Decimal(amount),
                instructed_on=TODAY - timedelta(days=40 - index * 9),
                instructed_by=who,
                description=(
                    "Instructed on site and priced against the schedule of rates."
                ),
            ),
            admin,
        )
        if status == "approved":
            commercial.approve_variation(db, variation.id, admin)
            approved += 1

    print(f"variations: {len(VARIATIONS)} instructed, {approved} approved")


# --- Back-charges ------------------------------------------------------------

BACK_CHARGES = [
    ("Blockwork damaged during installation, made good by others", "1850"),
    ("Scaffold left on site after completion, removed by others", "640"),
]


def seed_back_charges(db) -> None:
    if db.scalar(select(func.count()).select_from(BackCharge)):
        print("back-charges: already raised")
        return

    admin = _admin(db)
    contracts = [
        c
        for c in db.scalars(select(Subcontract).order_by(Subcontract.doc_number))
        if c.status.value != "draft"
    ]
    if not contracts:
        print("back-charges: nothing to charge against")
        return

    for index, (reason, amount) in enumerate(BACK_CHARGES):
        commercial.raise_back_charge(
            db,
            contracts[index % len(contracts)].id,
            BackChargeCreate(
                reason=reason,
                amount=Decimal(amount),
                raised_on=TODAY - timedelta(days=20 - index * 6),
            ),
            admin,
        )
    print(f"back-charges: {len(BACK_CHARGES)} raised")


def seed_withholding(db) -> None:
    """Give a couple of packages a rate, so the certificate has the line on it.

    Left at zero elsewhere on purpose: that is what a subcontractor holding a
    valid tax clearance is due, and a register where every package withholds
    would not show the distinction the rule exists for.
    """
    contracts = list(db.scalars(select(Subcontract).order_by(Subcontract.doc_number)))
    if not contracts:
        return
    changed = 0
    for contract in contracts[:2]:
        if Decimal(contract.withholding_pct or 0) == 0:
            contract.withholding_pct = Decimal("10")
            changed += 1
    db.flush()
    print(f"withholding: {changed} packages set to 10%")


# --- Plant recharge ----------------------------------------------------------


def seed_plant_recharge(db) -> None:
    """Switch the books to internal hire and charge a month out.

    This is the one block that changes how the company costs its plant, which
    is a real accounting decision. It is done here because the demo data is
    meaningless without it: on direct costing the recharge screen correctly
    refuses to run and there is nothing to look at.
    """
    from app.modules.fleet import plant
    from app.modules.fleet.models import PlantRecharge

    if db.scalar(select(func.count()).select_from(PlantRecharge)):
        print("plant recharge: already run")
        return

    settings_row = db.scalar(select(CompanySettings).limit(1))
    if settings_row is None:
        print("plant recharge: no company settings")
        return
    settings_row.plant_costing_mode = PlantCostingMode.internal_hire
    db.flush()

    admin = _admin(db)
    # Last month, which has a full set of readings behind it.
    first_of_this = TODAY.replace(day=1)
    period = (first_of_this - timedelta(days=1)).replace(day=1)

    result = plant.run_recharge(db, period, admin)
    print(
        f"plant recharge: {result['recharged']} charges for {period:%b %Y}, "
        f"{result['total']} total"
    )


def seed_depreciation(db) -> None:
    from app.modules.fleet import plant
    from app.modules.fleet.models import DepreciationCharge, Equipment

    if db.scalar(select(func.count()).select_from(DepreciationCharge)):
        print("depreciation: already posted")
        return

    admin = _admin(db)
    # Nothing has a life on it yet, so the run would find nothing to do.
    # Owned plant gets one; hired plant deliberately does not, because it is
    # not ours to write down.
    lives = 0
    for machine in db.scalars(select(Equipment).order_by(Equipment.code)):
        if machine.ownership.value != "owned" or not machine.purchase_cost:
            continue
        if machine.useful_life_months:
            continue
        machine.useful_life_months = 60
        machine.residual_value = (Decimal(machine.purchase_cost) * Decimal("0.15")).quantize(
            Decimal("0.01")
        )
        lives += 1
    db.flush()

    first_of_this = TODAY.replace(day=1)
    posted = Decimal("0")
    months = 0
    for back in (3, 2, 1):
        period = first_of_this
        for _ in range(back):
            period = (period - timedelta(days=1)).replace(day=1)
        result = plant.run_depreciation(db, period, admin)
        posted += Decimal(result["total"])
        months += 1
    print(f"depreciation: {lives} machines given a life, {months} months posted, {posted} total")


# --- Supplier portal ---------------------------------------------------------

INVOICES = [
    # (days ago, amount relative to the order, reference, what happens to it)
    (18, Decimal("1.00"), "INV-4417", "accepted"),
    (11, Decimal("1.24"), "INV-4482", None),
    (6, Decimal("1.00"), "INV-4511", "queried"),
    (3, Decimal("0.60"), "INV-4530", None),
]


def seed_supplier_invoices(db) -> None:
    """Claims sent in through the portal, including one that does not match.

    A register where every invoice agrees with its order would demonstrate
    nothing: the point of taking them this way is catching the one that does
    not.
    """
    if db.scalar(select(func.count()).select_from(SupplierInvoice)):
        print("supplier invoices: already submitted")
        return

    admin = _admin(db)
    orders = list(
        db.scalars(
            select(PurchaseOrder)
            .where(PurchaseOrder.total_amount > 0)
            .order_by(PurchaseOrder.order_date.desc())
            .limit(len(INVOICES))
        )
    )
    if not orders:
        print("supplier invoices: no orders to claim against")
        return

    class _Body:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    tokens: dict = {}
    submitted = 0
    for index, (days_ago, factor, reference, outcome) in enumerate(INVOICES):
        order = orders[index % len(orders)]
        supplier_id = order.supplier_id
        if supplier_id not in tokens:
            token, _raw = supplier_portal.issue_token(
                db, supplier_id, "Portal access", 365, admin
            )
            tokens[supplier_id] = token

        invoice = supplier_portal.submit_invoice(
            db,
            tokens[supplier_id],
            _Body(
                purchase_order_id=order.id,
                reference=reference,
                invoice_date=TODAY - timedelta(days=days_ago),
                amount=(Decimal(order.total_amount) * factor).quantize(Decimal("0.01")),
                notes=None,
            ),
        )
        submitted += 1
        if outcome == "accepted":
            supplier_portal.decide_invoice(db, invoice.id, True, None, admin)
        elif outcome == "queried":
            supplier_portal.decide_invoice(
                db, invoice.id, False, "Send the signed delivery note with it", admin
            )

    mismatches = supplier_portal.matching_report(db)
    print(
        f"supplier invoices: {submitted} submitted across {len(tokens)} portal links, "
        f"{len(mismatches)} not matching their order"
    )


def main() -> None:
    if settings.environment == "production":
        print("Refusing to run against production")
        sys.exit(1)

    db = SessionLocal()
    try:
        for step in (
            seed_withholding,
            seed_variations,
            seed_back_charges,
            seed_plant_recharge,
            seed_depreciation,
            seed_supplier_invoices,
            seed_assessments,
        ):
            step(db)
            db.commit()
        print("\nCommercial data complete.")
    finally:
        db.close()




# --- Supplier performance ----------------------------------------------------

# Deliberately uneven. A register where every supplier scores four proves
# nothing; the screen exists to show the one you should stop using.
SUPPLIER_SHAPES = [
    (5, 5, True, "Straight off the truck, driver waited while we counted it"),
    (4, 4, True, "Good load, an hour late but they rang ahead"),
    (2, 3, False, "Short delivery and two broken pallets; had to chase twice"),
    (4, 5, True, "No issues at all"),
    (3, 2, False, "Right material, but nobody answers the phone"),
    (5, 4, True, "Sound as always"),
]


def seed_assessments(db) -> None:
    from app.common.enums import PoStatus
    from app.modules.procurement import rating
    from app.modules.procurement.models import PurchaseOrder, SupplierAssessment
    from app.modules.procurement.schemas import AssessmentCreate

    if db.scalar(select(func.count()).select_from(SupplierAssessment)):
        print("assessments: already judged")
        return

    admin = _admin(db)
    received = list(
        db.scalars(
            select(PurchaseOrder)
            .where(PurchaseOrder.status == PoStatus.received)
            .order_by(PurchaseOrder.received_date.desc())
        )
    )
    if not received:
        print("assessments: nothing delivered to judge")
        return

    # Most deliveries get judged, but not all of them — the outstanding list
    # exists precisely because this never happens perfectly.
    judged = 0
    for index, order in enumerate(received):
        if index % 4 == 3:
            continue
        quality, professionalism, again, note = SUPPLIER_SHAPES[index % len(SUPPLIER_SHAPES)]
        rating.record_assessment(
            db,
            order.id,
            AssessmentCreate(
                quality=quality,
                professionalism=professionalism,
                would_use_again=again,
                notes=note,
            ),
            admin,
        )
        judged += 1

    outstanding = len(rating.unassessed_deliveries(db))
    print(f"assessments: {judged} deliveries judged, {outstanding} still outstanding")

if __name__ == "__main__":
    main()
