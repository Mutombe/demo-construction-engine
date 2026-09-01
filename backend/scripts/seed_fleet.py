"""Fills the plant, compliance and subcontract tables.

Run after `scripts.seed`:  uv run python -m scripts.seed_fleet

Everything goes through the real services, so the numbers on the screens are
the numbers the rules produce: certifying a stage really books the cost and
holds the retention, fuel really lands in the cost ledger, and the fuel
exception report finds what it finds rather than what was planted.

The shape of the data is chosen so every screen has something to say. There
are machines that were never metered, so utilisation reads "Not measured"
rather than a misleading zero; a machine that burns badly, so the fuel
exception report is not empty; certificates that lapsed, so a vendor is
genuinely blocked from being awarded work; and stages at every point in the
lifecycle, so the subcontract screen shows a live package rather than a
finished one.

Idempotent: each block checks whether its work is already done.
"""

import random
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

import app.modules  # noqa: F401
from app.common.enums import (
    ComplianceDocType,
    EquipmentCategory,
    MeterSource,
    MeterType,
    Ownership,
    UserRole,
    VendorStatus,
)
from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.fleet import service as fleet
from app.modules.fleet.models import Equipment, FuelLog, MaintenanceSchedule, MeterReading
from app.modules.fleet.schemas import (
    AssignmentCreate,
    EquipmentCreate,
    FuelLogCreate,
    MaintenanceCreate,
    MeterReadingCreate,
    ScheduleCreate,
)
from app.modules.procurement.models import Supplier
from app.modules.projects.models import Project
from app.modules.subcontracts import service as subcontracts
from app.modules.subcontracts.models import ComplianceDocument, Subcontract
from app.modules.subcontracts.schemas import (
    CertifyRequest,
    MilestoneCreate,
    SubcontractCreate,
)
from app.modules.sync.models import SyncOperation
from app.modules.users.models import User

TODAY = date.today()
rng = random.Random(20260831)


# --- The yard ----------------------------------------------------------------
#
# (code, name, category, ownership, meter type, opening meter, charge-out
#  rate PER METERED UNIT, litres per hour it should burn)
#
# The rate is per hour for yellow plant and per kilometre for anything on
# distance. They are not remotely the same number: a tipper at an hourly
# rate would recharge a job six figures for one month of tipping.
#
# `None` for the burn rate means nobody ever established one, which is the
# normal state of a yard and is why the exception report learns a baseline
# from each machine's own history instead of insisting on a figure.

PLANT = [
    ("EXC-001", "Cat 320D Excavator", "excavator", "owned", "hours", 4180, 45, "18.0"),
    ("EXC-002", "Komatsu PC200 Excavator", "excavator", "owned", "hours", 6720, 45, "17.5"),
    ("EXC-003", "Hitachi ZX130 Excavator", "excavator", "hired", "hours", 980, 52, None),
    ("LDR-001", "Cat 950H Wheel Loader", "loader", "owned", "hours", 5310, 40, "14.0"),
    ("LDR-002", "JCB 3CX Backhoe", "loader", "owned", "hours", 3890, 28, "9.5"),
    ("GRD-001", "Cat 140K Grader", "grader", "hired", "hours", 2240, 60, "16.0"),
    ("RLR-001", "Bomag BW211 Roller", "roller", "owned", "hours", 2760, 26, "8.5"),
    ("RLR-002", "Dynapac CA250 Roller", "roller", "owned", "hours", 1420, 26, None),
    ("TIP-001", "Howo 30t Tipper", "tipper", "owned", "kilometres", 148_300, "1.80", None),
    ("TIP-002", "Howo 30t Tipper", "tipper", "owned", "kilometres", 96_450, "1.80", None),
    ("TIP-003", "Sinotruk 20t Tipper", "tipper", "hired", "kilometres", 211_900, "1.65", None),
    ("CRN-001", "Potain MDT 219 Tower Crane", "crane", "hired", "hours", 640, 85, None),
    ("GEN-001", "FG Wilson 100kVA Generator", "generator", "owned", "hours", 8910, 12, "12.0"),
    ("GEN-002", "Perkins 60kVA Generator", "generator", "owned", "hours", 3120, 9, "7.5"),
    ("PMP-001", "Honda 3in Dewatering Pump", "pump", "owned", "hours", 740, 4, None),
    ("LV-001", "Toyota Hilux D/C", "light_vehicle", "owned", "kilometres", 63_200, "0.85", None),
    ("LV-002", "Isuzu D-Max D/C", "light_vehicle", "owned", "kilometres", 41_770, "0.85", None),
]

# What each machine is on the books at. Hired plant is zero: it belongs to
# somebody else, so it is not an asset of ours and is not depreciated.
PURCHASE_COSTS = {
    "EXC-001": Decimal("88000"),
    "EXC-002": Decimal("76000"),
    "EXC-003": Decimal("0"),
    "LDR-001": Decimal("82000"),
    "LDR-002": Decimal("54000"),
    "GRD-001": Decimal("0"),
    "RLR-001": Decimal("47000"),
    "RLR-002": Decimal("39000"),
    "TIP-001": Decimal("46000"),
    "TIP-002": Decimal("44000"),
    "TIP-003": Decimal("0"),
    "CRN-001": Decimal("0"),
    "GEN-001": Decimal("23000"),
    "GEN-002": Decimal("14500"),
    "PMP-001": Decimal("3800"),
    "LV-001": Decimal("34000"),
    "LV-002": Decimal("31500"),
}

# One machine burns far more than its own history says it should. Somebody
# needs to look at it, and the report is what makes them.
THIRSTY = "GEN-001"

# Two machines have never been read since they were registered. That is a real
# state — plant goes out and nobody writes the hours down — and the utilisation
# screen has to say so rather than reporting them as idle.
NEVER_READ = {"PMP-001", "RLR-002"}

SCHEDULES = {
    "excavator": ("500hr service", 500),
    "loader": ("500hr service", 500),
    "grader": ("500hr service", 500),
    "roller": ("250hr service", 250),
    "generator": ("250hr service", 250),
    "crane": ("1000hr inspection", 1000),
}


def seed_equipment(db) -> None:
    if db.scalar(select(func.count()).select_from(Equipment)):
        print("plant: already registered")
        return

    admin = db.scalar(select(User).where(User.role == UserRole.admin))
    projects = list(db.scalars(select(Project).order_by(Project.code)))
    hire_suppliers = list(db.scalars(select(Supplier).order_by(Supplier.name).limit(4)))

    for index, (code, name, category, own, meter, opening, rate, burn) in enumerate(PLANT):
        machine = fleet_create(
            db,
            EquipmentCreate(
                code=code,
                name=name,
                category=EquipmentCategory(category),
                ownership=Ownership(own),
                meter_type=MeterType(meter),
                current_meter=Decimal(opening),
                hourly_rate=Decimal(str(rate)),
                expected_burn_rate=Decimal(burn) if burn else None,
                make=name.split()[0],
                registration=f"AE{7000 + index * 13} {chr(65 + index % 26)}Z"
                if meter == "kilometres"
                else None,
                year=2015 + (index % 8),
                supplier_id=hire_suppliers[index % len(hire_suppliers)].id
                if own == "hired" and hire_suppliers
                else None,
                purchase_date=TODAY - timedelta(days=400 + index * 55),
                # Hired plant is not ours to carry, so it has no cost and
                # never appears on the asset register.
                purchase_cost=PURCHASE_COSTS.get(code) or None,
            ),
            admin,
        )

        # Most of the yard is out working; a few are in the workshop or idle,
        # because a fleet where everything is deployed is not a real fleet.
        if index % 5 != 4 and projects:
            fleet.assign(
                db,
                machine.id,
                AssignmentCreate(
                    project_id=projects[index % len(projects)].id,
                    started_on=TODAY - timedelta(days=90 - index),
                ),
                admin,
            )

        schedule = SCHEDULES.get(category)
        if schedule and meter == "hours":
            label, interval = schedule
            db.add(
                MaintenanceSchedule(
                    equipment_id=machine.id,
                    name=label,
                    interval_meter=Decimal(interval),
                    interval_days=180,
                    last_done_meter=Decimal(opening) - Decimal(interval - 60 - index * 7),
                    last_done_date=TODAY - timedelta(days=120 + index),
                )
            )

    db.flush()
    print(f"plant: {len(PLANT)} machines registered")


def fleet_create(db, data: EquipmentCreate, user) -> Equipment:
    """The router builds the row itself, so this mirrors it."""
    machine = Equipment(**data.model_dump(), created_by=getattr(user, "id", None))
    machine.opening_meter = machine.current_meter
    db.add(machine)
    db.flush()
    return machine


def seed_readings_and_fuel(db) -> None:
    """Twelve weeks of readings and fills for every machine.

    Committed one machine at a time and skipped per machine rather than for
    the block as a whole. Against a database on the other side of an ocean
    this is several hundred round trips, and an all-or-nothing block means an
    interrupted run throws away everything it had already done.
    """
    admin = db.scalar(select(User).where(User.role == UserRole.admin))
    machines = list(db.scalars(select(Equipment).order_by(Equipment.code)))
    readings = 0
    fills = 0
    skipped = 0

    for machine in machines:
        if machine.code in NEVER_READ:
            continue
        already = db.scalar(
            select(func.count())
            .select_from(MeterReading)
            .where(MeterReading.equipment_id == machine.id)
        )
        if already:
            skipped += 1
            continue

        hours_plant = machine.meter_type is MeterType.hours
        meter = Decimal(machine.current_meter)
        # Twelve weeks of weekly readings, which is how site actually reports:
        # somebody walks the yard on a Friday with a clipboard.
        for week in range(12, 0, -1):
            when = TODAY - timedelta(days=week * 7)
            worked = rng.randint(28, 52) if hours_plant else rng.randint(700, 1900)
            if rng.random() < 0.12:
                worked = rng.randint(0, 6) if hours_plant else rng.randint(0, 120)
            meter += Decimal(worked)

            fleet.record_reading(
                db,
                machine.id,
                MeterReadingCreate(
                    reading_date=when,
                    meter=meter,
                    source=MeterSource.telematics
                    if machine.code.startswith(("EXC", "LDR"))
                    else MeterSource.manual,
                    idle_hours=Decimal(rng.randint(2, 11)) if hours_plant else None,
                ),
                admin,
            )
            readings += 1

            # Fuel is booked against the meter, which is the only thing that
            # makes litres mean anything. A fill with no meter beside it can
            # never be told apart from a siphon.
            if hours_plant:
                baseline = Decimal(machine.expected_burn_rate or "11.0")
                if machine.code == THIRSTY and week <= 5:
                    baseline *= Decimal("1.9")
                litres = (baseline * Decimal(worked) * Decimal(rng.uniform(0.92, 1.08))).quantize(
                    Decimal("0.1")
                )
            else:
                litres = (Decimal(worked) / Decimal("2.4")).quantize(Decimal("0.1"))

            if litres <= 0:
                continue
            fleet.record_fuel(
                db,
                machine.id,
                FuelLogCreate(
                    log_date=when,
                    litres=litres,
                    meter=meter,
                    unit_cost=Decimal("1.62"),
                    operator=rng.choice(
                        ["T. Moyo", "S. Chikwanha", "B. Ncube", "K. Dube", "R. Mangwiro"]
                    ),
                    reference=f"FC-{when:%y%m%d}-{machine.code[-3:]}",
                ),
                admin,
            )
            fills += 1

        db.commit()

    print(
        f"plant history: {readings} readings, {fills} fills"
        + (f", {skipped} machines already done" if skipped else "")
    )


def seed_maintenance(db) -> None:
    from app.modules.fleet.models import MaintenanceRecord

    if db.scalar(select(func.count()).select_from(MaintenanceRecord)):
        print("maintenance: already recorded")
        return

    admin = db.scalar(select(User).where(User.role == UserRole.admin))
    jobs = [
        ("EXC-001", "500hr service — oils, filters, greasing", "480", 62, "9"),
        ("EXC-002", "Track tension and idler replacement", "1240", 96, "26"),
        ("LDR-001", "500hr service and hydraulic hose", "690", 71, "14"),
        ("RLR-001", "Drum bearing replaced", "1580", 40, "31"),
        ("GEN-001", "250hr service, injector clean", "410", 25, "6"),
        ("TIP-001", "Brake overhaul and pads", "880", 55, "18"),
        ("GRD-001", "Blade edge replacement", "520", 33, "7"),
    ]
    for code, description, cost, days_ago, downtime in jobs:
        machine = db.scalar(select(Equipment).where(Equipment.code == code))
        if machine is None:
            continue
        fleet.record_maintenance(
            db,
            machine.id,
            MaintenanceCreate(
                service_date=TODAY - timedelta(days=days_ago),
                description=description,
                cost=Decimal(cost),
                downtime_hours=Decimal(downtime),
                reference=f"WS-{2400 + days_ago}",
            ),
            admin,
        )
    print(f"maintenance: {len(jobs)} jobs recorded")


# --- Vendor compliance -------------------------------------------------------
#
# Deliberately uneven. A register where every vendor is fully compliant proves
# nothing, and the screen that matters is the one that stops an award.

COMPLIANCE_SHAPES = [
    # (vendor status, {doc type: days until expiry, or None for no expiry,
    #                  or "missing" to leave it out})
    (VendorStatus.approved, {"tax_clearance": 210, "company_registration": None,
                             "public_liability": 160, "workmans_compensation": 140,
                             "safety_certificate": 300, "bank_confirmation": None}),
    (VendorStatus.approved, {"tax_clearance": 18, "company_registration": None,
                             "public_liability": 95, "workmans_compensation": 26,
                             "bank_confirmation": None}),
    (VendorStatus.approved, {"tax_clearance": -34, "company_registration": None,
                             "public_liability": 120, "workmans_compensation": 88}),
    (VendorStatus.pending, {"company_registration": None, "tax_clearance": 260}),
    (VendorStatus.approved, {"tax_clearance": 340, "company_registration": None,
                             "public_liability": 240, "workmans_compensation": 230,
                             "safety_certificate": 190, "trade_licence": 150,
                             "bank_confirmation": None, "vat_registration": None}),
    (VendorStatus.suspended, {"company_registration": None, "tax_clearance": -120}),
]


def seed_compliance(db) -> None:
    if db.scalar(select(func.count()).select_from(ComplianceDocument)):
        print("compliance: already filed")
        return

    subcontracts.ensure_requirements(db)
    admin = db.scalar(select(User).where(User.role == UserRole.admin))
    suppliers = list(db.scalars(select(Supplier).order_by(Supplier.name)))
    filed = 0

    for index, supplier in enumerate(suppliers):
        status, docs = COMPLIANCE_SHAPES[index % len(COMPLIANCE_SHAPES)]
        subcontracts.set_vendor_status(db, supplier.id, status, admin)

        for doc_type, offset in docs.items():
            expires = None if offset is None else TODAY + timedelta(days=offset)
            db.add(
                ComplianceDocument(
                    supplier_id=supplier.id,
                    doc_type=ComplianceDocType(doc_type),
                    reference=f"{doc_type[:3].upper()}/{2025 + index % 2}/{4100 + filed}",
                    issued_on=(expires - timedelta(days=365)) if expires else TODAY - timedelta(days=900),
                    expires_on=expires,
                    created_by=getattr(admin, "id", None),
                )
            )
            filed += 1

    db.flush()
    blocked = sum(
        0 if subcontracts.compliance_status(db, s.id)["is_compliant"] else 1 for s in suppliers
    )
    print(f"compliance: {filed} documents across {len(suppliers)} vendors, {blocked} blocked")


# --- Subcontract packages ----------------------------------------------------

PACKAGES = [
    (
        "Electrical installation",
        "Containment, first and second fix, DBs and testing to the whole block.",
        "10",
        [("Containment and conduit", "48000"), ("First fix wiring", "62000"),
         ("DB installation", "31000"), ("Second fix and testing", "44000")],
        3,  # stages certified
    ),
    (
        "Plumbing and drainage",
        "Below-ground drainage, risers, sanitaryware and commissioning.",
        "10",
        [("Below-ground drainage", "38000"), ("Risers and branches", "41000"),
         ("Sanitaryware", "27000"), ("Commissioning", "12000")],
        2,
    ),
    (
        "Aluminium windows and curtain walling",
        "Supply and install to elevations A through D, including glazing.",
        "5",
        [("Survey and shop drawings", "9000"), ("Frames to elevations A-B", "84000"),
         ("Frames to elevations C-D", "76000"), ("Glazing and seals", "52000")],
        2,
    ),
    (
        "Roof sheeting and rainwater goods",
        "IBR sheeting, insulation, flashings and gutters.",
        "10",
        [("Purlins and bracing", "34000"), ("Sheeting and insulation", "58000"),
         ("Flashings and gutters", "19000")],
        3,
    ),
    (
        "Painting and decorating",
        "Internal and external decoration, two coats throughout.",
        "5",
        [("External render coat", "22000"), ("Internal first coat", "26000"),
         ("Internal finish coat", "24000")],
        1,
    ),
    (
        "Tiling and floor finishes",
        "Ceramic to wet areas, screed and vinyl elsewhere.",
        "10",
        [("Screeding", "31000"), ("Wet area tiling", "36000"), ("Vinyl and skirting", "28000")],
        0,
    ),
]


def seed_subcontracts(db) -> None:
    if db.scalar(select(func.count()).select_from(Subcontract)):
        print("subcontracts: already let")
        return

    admin = db.scalar(select(User).where(User.role == UserRole.admin))
    projects = list(db.scalars(select(Project).order_by(Project.code)))
    suppliers = list(db.scalars(select(Supplier).order_by(Supplier.name)))
    if not projects or not suppliers:
        print("subcontracts: nothing to hang them on")
        return

    # Only vendors whose paperwork actually stands up can be awarded, which is
    # the point of the compliance module. Anything else would seed a state the
    # rules would never allow.
    tradeable = []
    for supplier in suppliers:
        try:
            subcontracts.require_tradeable(db, supplier.id)
            tradeable.append(supplier)
        except Exception:
            continue
    if not tradeable:
        print("subcontracts: no vendor is clear to be awarded")
        return

    let = 0
    certified = 0
    for index, (title, scope, retention, stages, sign_off) in enumerate(PACKAGES):
        project = projects[index % len(projects)]
        supplier = tradeable[index % len(tradeable)]
        total = sum(Decimal(value) for _, value in stages)

        contract = subcontracts.create_subcontract(
            db,
            project.id,
            SubcontractCreate(
                supplier_id=supplier.id,
                title=title,
                scope=scope,
                value=total,
                retention_pct=Decimal(retention),
                starts_on=TODAY - timedelta(days=150 - index * 12),
                ends_on=TODAY + timedelta(days=60 + index * 20),
                milestones=[
                    MilestoneCreate(
                        name=name,
                        value=Decimal(value),
                        due_date=TODAY - timedelta(days=120 - stage_index * 35 - index * 10),
                    )
                    for stage_index, (name, value) in enumerate(stages)
                ],
            ),
            admin,
        )
        let += 1

        # The last package stays in draft, so the screen shows what an
        # un-awarded package looks like and the Award button has a job.
        if index == len(PACKAGES) - 1:
            continue

        subcontracts.award(db, contract.id, admin)

        milestones = sorted(contract.milestones, key=lambda m: m.due_date or TODAY)
        for stage_index, milestone in enumerate(milestones):
            if stage_index < sign_off:
                subcontracts.submit_milestone(db, milestone.id, admin)
                subcontracts.certify_milestone(
                    db,
                    milestone.id,
                    CertifyRequest(
                        certified_on=(milestone.due_date or TODAY) + timedelta(days=4)
                    ),
                    admin,
                )
                certified += 1
            elif stage_index == sign_off and index % 3 != 2:
                # One stage sitting with the QS, waiting to be signed off.
                subcontracts.submit_milestone(db, milestone.id, admin)
            elif stage_index == sign_off:
                subcontracts.submit_milestone(db, milestone.id, admin)
                subcontracts.reject_milestone(
                    db,
                    milestone.id,
                    "Setting out does not match the issued drawing; re-submit once corrected.",
                    admin,
                )

    print(f"subcontracts: {let} packages let, {certified} stages certified")


# --- Field captures ----------------------------------------------------------


def seed_sync_history(db) -> None:
    """A device's history, including the ones that did not land.

    The rejected rows matter more than the applied ones: they are what proves
    a refused capture is kept and shown rather than quietly dropped.
    """
    import uuid

    if db.scalar(select(func.count()).select_from(SyncOperation)):
        print("field captures: already recorded")
        return

    user = db.scalar(select(User).where(User.role == UserRole.site_manager)) or db.scalar(
        select(User).where(User.role == UserRole.admin)
    )
    project = db.scalar(select(Project).order_by(Project.code))
    if project is None:
        return

    entries = [
        ("diary_entry", "applied", None, 9),
        ("diary_labour", "applied", None, 9),
        ("meter_reading", "applied", None, 8),
        ("site_issue", "applied", None, 7),
        ("diary_entry", "merged", "The day was already written up; your entry was added to it.", 6),
        ("fuel_log", "applied", None, 5),
        ("meter_reading", "rejected", "EXC-001 was on 4680 when it was read on "
         f"{(TODAY - timedelta(days=7)).isoformat()}; a meter cannot go backwards", 4),
        ("diary_labour", "rejected", "There is no diary for 12 Aug to hang this labour on", 3),
    ]

    for op_type, status, detail, days_ago in entries:
        captured = datetime.now(UTC) - timedelta(days=days_ago, hours=6)
        db.add(
            SyncOperation(
                client_op_id=uuid.uuid4(),
                device_id="site-tablet-01",
                user_id=getattr(user, "id", None),
                op_type=op_type,
                payload={"project_id": str(project.id)},
                status=status,
                entity_type=op_type if status in ("applied", "merged") else None,
                detail=detail,
                captured_at=captured,
                received_at=captured + timedelta(hours=rng.randint(2, 30)),
            )
        )

    print(f"field captures: {len(entries)} recorded, 2 refused")


def main() -> None:
    if settings.environment == "production":
        print("Refusing to run against production")
        sys.exit(1)

    db = SessionLocal()
    try:
        # Committed one block at a time. Against a database on the other side
        # of an ocean this takes minutes, and a single transaction at the end
        # means an interrupted run leaves nothing behind and has to start over.
        for step in (
            seed_equipment,
            seed_readings_and_fuel,
            seed_maintenance,
            seed_compliance,
            seed_subcontracts,
            seed_sync_history,
        ):
            step(db)
            db.commit()

        summary = fleet.fleet_summary(db)
        exceptions = fleet.fuel_exceptions(db)
        print(
            f"\nFleet: {summary}\n"
            f"Fuel exceptions found: {len(exceptions)}"
        )
        print("Fleet, compliance and subcontracts complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
