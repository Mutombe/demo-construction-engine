"""Idempotent dev seed. Run: uv run python -m scripts.seed
Refuses to run when ENVIRONMENT=production."""

import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

import app.modules  # noqa: F401
from app.common.enums import (
    CostCategory,
    ProjectStatus,
    RfqStatus,
    UserRole,
    WorkStatus,
)
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.boq.models import BoqItem, BoqSection
from app.modules.clients.models import Client
from app.modules.company.models import CompanySettings
from app.modules.costs.models import CostEntry
from app.modules.procurement.models import Quote, QuoteItem, Rfq, RfqItem, Supplier
from app.modules.projects.models import Phase, Project
from app.modules.tasks.models import Task, TaskDependency
from app.modules.users.models import User

TODAY = date.today()
DEV_PASSWORD = "demo1234"

USERS = [
    ("admin@demo.local", "Amara Chikwanda", UserRole.admin),
    ("pm@demo.local", "Tendai Moyo", UserRole.project_manager),
    ("site@demo.local", "Blessing Ncube", UserRole.site_manager),
    ("procurement@demo.local", "Rudo Marufu", UserRole.procurement_officer),
    ("viewer@demo.local", "Kudzai Dube", UserRole.viewer),
]


def get_or_create(db, model, defaults=None, **filters):
    instance = db.scalar(select(model).filter_by(**filters))
    if instance:
        return instance, False
    instance = model(**filters, **(defaults or {}))
    db.add(instance)
    db.flush()
    return instance, True


def seed_users(db) -> dict[str, User]:
    users = {}
    for email, full_name, role in USERS:
        user, _ = get_or_create(
            db,
            User,
            email=email,
            defaults={
                "full_name": full_name,
                "role": role,
                "hashed_password": hash_password(DEV_PASSWORD),
            },
        )
        users[role.value] = user
    return users


def seed_clients(db) -> dict[str, Client]:
    riverside, _ = get_or_create(
        db,
        Client,
        name="Riverside Property Group",
        defaults={
            "contact_person": "J. Banda",
            "email": "projects@riversidegroup.example",
            "phone": "+263 77 000 1111",
            "address": "14 Samora Machel Ave, Harare",
        },
    )
    eastlands, _ = get_or_create(
        db,
        Client,
        name="Eastlands Logistics",
        defaults={
            "contact_person": "P. Sibanda",
            "email": "ops@eastlands.example",
            "phone": "+263 78 222 3333",
            "address": "Plot 7, Feruka Rd, Mutare",
        },
    )
    return {"riverside": riverside, "eastlands": eastlands}


PHASE_TEMPLATE = [
    "Preliminaries",
    "Substructure",
    "Superstructure",
    "Roofing",
    "Services (M&E)",
    "Finishes",
    "External Works",
]


def _phases(db, project: Project, start: date, weeks_per_phase: int) -> list[Phase]:
    phases = []
    cursor = start
    for i, name in enumerate(PHASE_TEMPLATE, start=1):
        end = cursor + timedelta(weeks=weeks_per_phase)
        phase, _ = get_or_create(
            db,
            Phase,
            project_id=project.id,
            sequence=i,
            defaults={
                "name": name,
                "planned_start": cursor,
                "planned_end": end,
            },
        )
        phases.append(phase)
        cursor = end + timedelta(days=1)
    return phases


def _task(
    db,
    project: Project,
    phase: Phase,
    wbs: str,
    name: str,
    start: date,
    days: int,
    assignee: User,
    progress: int = 0,
    status: WorkStatus = WorkStatus.not_started,
    milestone: bool = False,
) -> Task:
    task, _ = get_or_create(
        db,
        Task,
        project_id=project.id,
        wbs_code=wbs,
        defaults={
            "phase_id": phase.id,
            "name": name,
            "planned_start": start,
            "planned_end": start + timedelta(days=days),
            "assignee_id": assignee.id,
            "progress_pct": progress,
            "status": status,
            "is_milestone": milestone,
            "actual_start": start if progress > 0 else None,
            "actual_end": start + timedelta(days=days) if progress == 100 else None,
        },
    )
    return task


def _dep(db, predecessor: Task, successor: Task) -> None:
    get_or_create(
        db,
        TaskDependency,
        predecessor_id=predecessor.id,
        successor_id=successor.id,
    )


def seed_riverside(db, users, clients) -> Project:
    """Active residential project, in the middle of superstructure, slightly late."""
    start = TODAY - timedelta(weeks=16)
    project, created = get_or_create(
        db,
        Project,
        code="PRJ-2026-001",
        defaults={
            "name": "Riverside Apartments — Block A",
            "description": "Six-storey residential block, 24 units, reinforced "
            "concrete frame with brick infill.",
            "client_id": clients["riverside"].id,
            "site_address": "Stand 512, Riverside Drive",
            "city": "Harare",
            "status": ProjectStatus.active,
            "planned_start": start,
            "planned_end": start + timedelta(weeks=52),
            "actual_start": start,
            "contract_value": Decimal("2450000.00"),
            "retention_pct": Decimal("10.00"),
            "project_manager_id": users["project_manager"].id,
            "created_by": users["admin"].id,
        },
    )
    if not created:
        return project

    phases = _phases(db, project, start, weeks_per_phase=7)
    pre, sub, sup, roof, serv, fin, ext = phases
    pm, site = users["project_manager"], users["site_manager"]

    # Preliminaries — done
    t11 = _task(
        db,
        project,
        pre,
        "1.1",
        "Site establishment & hoarding",
        start,
        10,
        site,
        100,
        WorkStatus.done,
    )
    t12 = _task(
        db,
        project,
        pre,
        "1.2",
        "Setting out & survey",
        start + timedelta(days=7),
        5,
        site,
        100,
        WorkStatus.done,
    )

    # Substructure — done, but it ran over budget (cost entries below)
    s = start + timedelta(weeks=3)
    t21 = _task(
        db, project, sub, "2.1", "Excavate foundation trenches", s, 12, site, 100, WorkStatus.done
    )
    t22 = _task(
        db,
        project,
        sub,
        "2.2",
        "Concrete blinding to trenches",
        s + timedelta(days=12),
        3,
        site,
        100,
        WorkStatus.done,
    )
    t23 = _task(
        db,
        project,
        sub,
        "2.3",
        "Strip footings & column bases",
        s + timedelta(days=16),
        14,
        site,
        100,
        WorkStatus.done,
    )
    t24 = _task(
        db,
        project,
        sub,
        "2.4",
        "Foundation walling to DPC",
        s + timedelta(days=31),
        12,
        site,
        100,
        WorkStatus.done,
    )
    t25 = _task(
        db,
        project,
        sub,
        "2.5",
        "Ground floor slab",
        s + timedelta(days=44),
        8,
        site,
        100,
        WorkStatus.done,
    )

    # Superstructure — in progress, one task overdue
    u = start + timedelta(weeks=11)
    t31 = _task(
        db, project, sup, "3.1", "Columns & shear walls to L1", u, 15, site, 100, WorkStatus.done
    )
    t32 = _task(
        db,
        project,
        sup,
        "3.2",
        "L1 suspended slab",
        u + timedelta(days=16),
        12,
        site,
        100,
        WorkStatus.done,
    )
    t33 = _task(
        db,
        project,
        sup,
        "3.3",
        "Columns to L2",
        u + timedelta(days=29),
        15,
        site,
        70,
        WorkStatus.in_progress,
    )
    t34 = _task(
        db,
        project,
        sup,
        "3.4",
        "L2 suspended slab",
        TODAY - timedelta(days=10),
        12,
        site,
        20,
        WorkStatus.in_progress,
    )
    t35 = _task(
        db,
        project,
        sup,
        "3.5",
        "Brick infill walls L1",
        TODAY - timedelta(days=20),
        18,
        site,
        0,
        WorkStatus.blocked,
    )
    t36 = _task(
        db,
        project,
        sup,
        "3.6",
        "Structure complete",
        start + timedelta(weeks=24),
        0,
        pm,
        0,
        WorkStatus.not_started,
        milestone=True,
    )

    # Roofing / services / finishes / external — future
    r = start + timedelta(weeks=25)
    t41 = _task(db, project, roof, "4.1", "Roof trusses & covering", r, 20, site)
    t51 = _task(
        db, project, serv, "5.1", "First-fix electrical & plumbing", r + timedelta(days=7), 25, site
    )
    t61 = _task(db, project, fin, "6.1", "Plaster & paint", r + timedelta(days=35), 30, site)
    t71 = _task(db, project, ext, "7.1", "Paving & landscaping", r + timedelta(days=60), 20, site)

    chain = [t11, t12, t21, t22, t23, t24, t25, t31, t32, t33, t34]
    for pred, succ in zip(chain, chain[1:], strict=False):
        _dep(db, pred, succ)
    _dep(db, t32, t35)
    _dep(db, t34, t36)
    _dep(db, t36, t41)
    _dep(db, t41, t51)
    _dep(db, t51, t61)
    _dep(db, t61, t71)

    # BOQ
    sections = {}
    for code, title, order in [
        ("A", "Preliminaries", 1),
        ("B", "Substructure", 2),
        ("C", "Superstructure", 3),
        ("D", "Roofing", 4),
    ]:
        sections[code], _ = get_or_create(
            db,
            BoqSection,
            project_id=project.id,
            code=code,
            defaults={"title": title, "sort_order": order},
        )

    items_spec = [
        (
            "A",
            "A.1",
            "Site establishment, offices and hoarding",
            "sum",
            1,
            38000,
            CostCategory.preliminaries,
        ),
        (
            "A",
            "A.2",
            "Insurance, supervision and attendance",
            "wk",
            52,
            450,
            CostCategory.preliminaries,
        ),
        (
            "B",
            "B.1",
            "Excavate foundation trenches n.e. 1.5m deep",
            "m3",
            420,
            Decimal("8.50"),
            CostCategory.labour,
        ),
        (
            "B",
            "B.2",
            "Concrete grade 15 blinding 50mm thick",
            "m2",
            310,
            Decimal("6.20"),
            CostCategory.material,
        ),
        (
            "B",
            "B.3",
            "Concrete grade 25 in strip footings",
            "m3",
            96,
            Decimal("148.00"),
            CostCategory.material,
        ),
        (
            "B",
            "B.4",
            "High-tensile rebar, cut bent and fixed",
            "kg",
            8400,
            Decimal("1.85"),
            CostCategory.material,
        ),
        (
            "B",
            "B.5",
            "Common brickwork in foundation walls",
            "m2",
            520,
            Decimal("28.50"),
            CostCategory.subcontract,
        ),
        (
            "B",
            "B.6",
            "Concrete grade 25 ground slab 150mm",
            "m3",
            68,
            Decimal("152.00"),
            CostCategory.material,
        ),
        (
            "C",
            "C.1",
            "Concrete grade 30 in columns and walls",
            "m3",
            210,
            Decimal("162.00"),
            CostCategory.material,
        ),
        (
            "C",
            "C.2",
            "Concrete grade 30 suspended slabs",
            "m3",
            340,
            Decimal("158.00"),
            CostCategory.material,
        ),
        (
            "C",
            "C.3",
            "Rebar to superstructure",
            "kg",
            46200,
            Decimal("1.85"),
            CostCategory.material,
        ),
        (
            "C",
            "C.4",
            "Formwork to soffits and columns",
            "m2",
            3800,
            Decimal("14.20"),
            CostCategory.subcontract,
        ),
        (
            "C",
            "C.5",
            "Brick infill walls 230mm",
            "m2",
            2400,
            Decimal("31.00"),
            CostCategory.subcontract,
        ),
        (
            "D",
            "D.1",
            "Timber roof trusses supplied and erected",
            "m2",
            480,
            Decimal("38.00"),
            CostCategory.subcontract,
        ),
        (
            "D",
            "D.2",
            "Concrete roof tiles on battens",
            "m2",
            480,
            Decimal("24.50"),
            CostCategory.material,
        ),
    ]
    items = {}
    for section_code, code, desc, unit, qty, rate, cat in items_spec:
        items[code], _ = get_or_create(
            db,
            BoqItem,
            project_id=project.id,
            section_id=sections[section_code].id,
            item_code=code,
            defaults={
                "description": desc,
                "unit": unit,
                "quantity": Decimal(str(qty)),
                "rate": Decimal(str(rate)),
                "cost_category": cat,
            },
        )
    # A variation order on substructure (rock encountered)
    items["B.7"], _ = get_or_create(
        db,
        BoqItem,
        project_id=project.id,
        section_id=sections["B"].id,
        item_code="B.7",
        defaults={
            "description": "VO-01: Break out rock in trench bottoms",
            "unit": "m3",
            "quantity": Decimal("60"),
            "rate": Decimal("42.00"),
            "cost_category": CostCategory.plant,
            "item_type": "variation",
            "variation_ref": "VO-01",
        },
    )

    # Cost entries: substructure deliberately ~15% over budget
    cost_spec = [
        ("B.1", -100, "Excavation labour gangs", Decimal("4650.00")),
        ("B.2", -96, "Blinding concrete delivered", Decimal("2010.00")),
        ("B.3", -90, "Readymix 25MPa footings", Decimal("15900.00")),
        ("B.4", -85, "Rebar supply — footings", Decimal("17200.00")),
        ("B.5", -74, "Foundation brickwork subcontract", Decimal("16600.00")),
        ("B.6", -63, "Ground slab pour", Decimal("11400.00")),
        ("B.7", -95, "Rock breaker hire", Decimal("3100.00")),
        ("C.1", -40, "Columns readymix L1", Decimal("13300.00")),
        ("C.2", -25, "L1 slab readymix", Decimal("18900.00")),
        ("C.3", -30, "Rebar superstructure — first delivery", Decimal("28400.00")),
        ("C.4", -28, "Formwork subcontract claim 1", Decimal("21500.00")),
        ("A.1", -110, "Site establishment", Decimal("36200.00")),
        (None, -50, "Security and sundry site costs", Decimal("5400.00")),
        (None, -20, "Water bowser hire", Decimal("1850.00")),
    ]
    for item_code, days_ago, desc, amount in cost_spec:
        get_or_create(
            db,
            CostEntry,
            project_id=project.id,
            description=desc,
            defaults={
                "boq_item_id": items[item_code].id if item_code else None,
                "entry_date": TODAY + timedelta(days=days_ago),
                "amount": amount,
                "created_by": users["site_manager"].id,
            },
        )
    return project


def seed_warehouse(db, users, clients) -> Project:
    """Active steel-frame warehouse, early stage, on budget."""
    start = TODAY - timedelta(weeks=5)
    project, created = get_or_create(
        db,
        Project,
        code="PRJ-2026-002",
        defaults={
            "name": "Mutare Distribution Warehouse",
            "description": "4,000m2 steel portal frame warehouse with office pod.",
            "client_id": clients["eastlands"].id,
            "site_address": "Plot 7, Feruka Industrial Park",
            "city": "Mutare",
            "status": ProjectStatus.active,
            "planned_start": start,
            "planned_end": start + timedelta(weeks=30),
            "actual_start": start,
            "contract_value": Decimal("1180000.00"),
            "retention_pct": Decimal("5.00"),
            "project_manager_id": users["project_manager"].id,
            "created_by": users["admin"].id,
        },
    )
    if not created:
        return project

    phases = _phases(db, project, start, weeks_per_phase=4)
    pre, sub, sup = phases[0], phases[1], phases[2]
    site = users["site_manager"]

    w1 = _task(
        db, project, pre, "1.1", "Site clearance & grading", start, 8, site, 100, WorkStatus.done
    )
    w2 = _task(
        db,
        project,
        sub,
        "2.1",
        "Bulk earthworks & compaction",
        start + timedelta(days=9),
        15,
        site,
        100,
        WorkStatus.done,
    )
    w3 = _task(
        db,
        project,
        sub,
        "2.2",
        "Pad foundations",
        start + timedelta(days=25),
        12,
        site,
        60,
        WorkStatus.in_progress,
    )
    w4 = _task(
        db, project, sup, "3.1", "Steel frame erection", TODAY + timedelta(days=10), 25, site
    )
    w5 = _task(
        db, project, sup, "3.2", "Roof sheeting & cladding", TODAY + timedelta(days=38), 20, site
    )
    for pred, succ in zip([w1, w2, w3, w4], [w2, w3, w4, w5], strict=True):
        _dep(db, pred, succ)

    section, _ = get_or_create(
        db,
        BoqSection,
        project_id=project.id,
        code="A",
        defaults={"title": "Groundworks & Frame", "sort_order": 1},
    )
    spec = [
        ("A.1", "Bulk excavation and compaction", "m3", 5200, Decimal("4.80"), CostCategory.plant),
        (
            "A.2",
            "Concrete grade 30 pad foundations",
            "m3",
            140,
            Decimal("155.00"),
            CostCategory.material,
        ),
        (
            "A.3",
            "Structural steel portal frame supplied & erected",
            "t",
            96,
            Decimal("2350.00"),
            CostCategory.subcontract,
        ),
        (
            "A.4",
            "Roof and wall cladding IBR 0.5mm",
            "m2",
            6200,
            Decimal("18.50"),
            CostCategory.material,
        ),
    ]
    items = {}
    for code, desc, unit, qty, rate, cat in spec:
        items[code], _ = get_or_create(
            db,
            BoqItem,
            project_id=project.id,
            section_id=section.id,
            item_code=code,
            defaults={
                "description": desc,
                "unit": unit,
                "quantity": Decimal(str(qty)),
                "rate": Decimal(str(rate)),
                "cost_category": cat,
            },
        )
    for item_code, days_ago, desc, amount in [
        ("A.1", -28, "Dozer and roller hire", Decimal("21300.00")),
        ("A.2", -10, "Readymix pads — first pours", Decimal("9800.00")),
        (None, -15, "Site services connection", Decimal("2400.00")),
    ]:
        get_or_create(
            db,
            CostEntry,
            project_id=project.id,
            description=desc,
            defaults={
                "boq_item_id": items[item_code].id if item_code else None,
                "entry_date": TODAY + timedelta(days=days_ago),
                "amount": amount,
                "created_by": users["site_manager"].id,
            },
        )
    return project


def seed_fitout(db, users, clients) -> Project:
    """Planning-stage office fit-out; no site activity yet."""
    start = TODAY + timedelta(weeks=6)
    project, created = get_or_create(
        db,
        Project,
        code="PRJ-2026-003",
        defaults={
            "name": "Riverside HQ Office Fit-out",
            "description": "Interior fit-out of 2 floors: partitions, ceilings, AC and joinery.",
            "client_id": clients["riverside"].id,
            "site_address": "3rd & 4th Floor, Riverside Towers",
            "city": "Harare",
            "status": ProjectStatus.planning,
            "planned_start": start,
            "planned_end": start + timedelta(weeks=14),
            "contract_value": Decimal("310000.00"),
            "project_manager_id": users["project_manager"].id,
            "created_by": users["admin"].id,
        },
    )
    if created:
        _phases(db, project, start, weeks_per_phase=2)
    return project


SUPPLIERS = [
    (
        "Mashonaland Building Supplies",
        "Tapiwa Gumbo",
        "sales@mashonaland.example",
        "cement, aggregates, blocks",
    ),
    (
        "SteelCo Zimbabwe (Pvt) Ltd",
        "Linda Chirwa",
        "quotes@steelco.example",
        "rebar, structural steel",
    ),
    (
        "Nyanga Timber & Hardware",
        "Farai Moyo",
        "info@nyangatimber.example",
        "timber, formwork, hardware",
    ),
    (
        "Premier Plumbing & Electrical",
        "Grace Banda",
        "sales@premierpe.example",
        "plumbing, electrical, HVAC",
    ),
]


def seed_procurement(db, users) -> None:
    suppliers = {}
    for name, contact, email, categories in SUPPLIERS:
        suppliers[name], _ = get_or_create(
            db,
            Supplier,
            name=name,
            defaults={
                "contact_name": contact,
                "email": email,
                "categories": categories,
                "created_by": users["procurement_officer"].id,
            },
        )

    project = db.scalar(select(Project).where(Project.code == "PRJ-2026-001"))
    if project is None:
        return
    boq_items = {
        i.item_code: i for i in db.scalars(select(BoqItem).where(BoqItem.project_id == project.id))
    }
    wanted = [boq_items.get("B.3"), boq_items.get("B.4"), boq_items.get("C.3")]
    if not all(wanted):
        return

    year = TODAY.year
    rfq, created = get_or_create(
        db,
        Rfq,
        doc_number=f"RFQ-{year}-001",
        defaults={
            "project_id": project.id,
            "title": "Supply of Concrete and Reinforcement — Substructure & Superstructure",
            "status": RfqStatus.issued,
            "due_date": TODAY + timedelta(days=10),
            "created_by": users["procurement_officer"].id,
            "body": (
                "## Introduction\n"
                "Demo Construction Co. invites your quotation for the supply of readymix "
                "concrete and reinforcement steel for the Riverside Apartments — Block A "
                "project in Harare.\n\n"
                "## Scope of Supply\n"
                "Supply and delivery to site of the items listed in the attached schedule. "
                "Delivery in staged loads against site call-off.\n\n"
                "## Submission Requirements\n"
                "Itemised pricing per the schedule, delivery lead times, and quote validity "
                "of not less than 30 days.\n\n"
                "## Commercial Terms\n"
                "State your payment terms. Prices to include delivery to Stand 512, "
                "Riverside Drive, Harare."
            ),
            "items": [
                RfqItem(
                    boq_item_id=item.id,
                    description=item.description,
                    unit=item.unit,
                    quantity=item.quantity,
                    sort_order=i,
                )
                for i, item in enumerate(wanted)
            ],
        },
    )
    if not created:
        return

    lines = {item.boq_item_id: item for item in rfq.items}
    b3, b4, c3 = (lines[w.id] for w in wanted)

    # Quote 1: full coverage, standard pricing
    prices_full = {b3.id: Decimal("146.00"), b4.id: Decimal("1.82"), c3.id: Decimal("1.88")}
    get_or_create(
        db,
        Quote,
        rfq_id=rfq.id,
        supplier_id=suppliers["Mashonaland Building Supplies"].id,
        defaults={
            "received_date": TODAY - timedelta(days=2),
            "valid_until": TODAY + timedelta(days=28),
            "payment_terms": "50% deposit, balance on delivery",
            "delivery_terms": "Staged deliveries within 5 working days of call-off",
            "total_amount": sum(
                (li.quantity * prices_full[li.id] for li in [b3, b4, c3]),
                Decimal("0"),
            ),
            "created_by": users["procurement_officer"].id,
            "items": [
                QuoteItem(
                    rfq_item_id=li.id,
                    description=li.description,
                    unit=li.unit,
                    quantity=li.quantity,
                    unit_price=prices_full[li.id],
                )
                for li in [b3, b4, c3]
            ],
        },
    )

    # Quote 2: cheaper steel, but no concrete line (coverage gap for the demo)
    prices_partial = {b4.id: Decimal("1.74"), c3.id: Decimal("1.79")}
    get_or_create(
        db,
        Quote,
        rfq_id=rfq.id,
        supplier_id=suppliers["SteelCo Zimbabwe (Pvt) Ltd"].id,
        defaults={
            "received_date": TODAY - timedelta(days=1),
            "valid_until": TODAY + timedelta(days=14),
            "payment_terms": "30 days net",
            "delivery_terms": "Ex works Harare; transport at cost",
            "notes": "Steel only — we do not supply readymix concrete.",
            "total_amount": sum(
                (li.quantity * prices_partial[li.id] for li in [b4, c3]),
                Decimal("0"),
            ),
            "created_by": users["procurement_officer"].id,
            "items": [
                QuoteItem(
                    rfq_item_id=li.id,
                    description=li.description,
                    unit=li.unit,
                    quantity=li.quantity,
                    unit_price=prices_partial[li.id],
                )
                for li in [b4, c3]
            ],
        },
    )


DIARY_TEMPLATE = [
    (
        "sunny",
        26,
        "1x tower crane, 2x mixers",
        "Columns to L2 grid A-D: rebar fixing and shutter erection.",
        None,
    ),
    (
        "sunny",
        28,
        "1x tower crane, 2x mixers, 1x pump",
        "Poured columns grid A-D, 18m3. Started L2 slab decking.",
        None,
    ),
    (
        "cloudy",
        30,
        "1x tower crane, 2x mixers",
        "L2 slab decking 60% complete. Brick deliveries stacked bay 2.",
        None,
    ),
    (
        "rain",
        12,
        "1x tower crane (idle)",
        "Rain most of day. Indoor prep: rebar cutting and bending schedule.",
        "Slab decking suspended — rain from 09:30",
    ),
    (
        "storm",
        0,
        "site secured",
        "Site closed - storm warning. Materials covered and secured.",
        "Full day lost to storm",
    ),
    (
        "sunny",
        32,
        "1x tower crane, 2x mixers, 1x pump",
        "Recovered decking programme; L2 slab decking complete. Rebar mats started.",
        None,
    ),
    (
        "sunny",
        30,
        "1x tower crane, 2x mixers",
        "L2 slab rebar 70%. Services sleeves set out with plumber.",
        None,
    ),
    (
        "cloudy",
        29,
        "1x tower crane, 2x mixers, 1x pump",
        "L2 slab rebar complete, inspected. Pour booked for tomorrow.",
        None,
    ),
    (
        "sunny",
        34,
        "1x tower crane, 2x pumps",
        "L2 slab poured, 92m3 over 7 hours. Finish acceptable.",
        None,
    ),
    (
        "sunny",
        22,
        "1x tower crane",
        "Curing and stripping program. Block deliveries to bay 3.",
        None,
    ),
]


def seed_site(db, users) -> None:
    from app.modules.site.models import SiteDiaryEntry, SiteIssue

    project = db.scalar(select(Project).where(Project.code == "PRJ-2026-001"))
    if project is None:
        return
    site_user = users["site_manager"]

    entry_day = TODAY - timedelta(days=13)
    template_index = 0
    while entry_day <= TODAY and template_index < len(DIARY_TEMPLATE):
        if entry_day.weekday() < 5:  # skip weekends
            weather, labour, plant, work, delays = DIARY_TEMPLATE[template_index]
            get_or_create(
                db,
                SiteDiaryEntry,
                project_id=project.id,
                entry_date=entry_day,
                defaults={
                    "weather": weather,
                    "labour_headcount": labour,
                    "plant_equipment": plant,
                    "work_done": work,
                    "delays": delays,
                    "created_by": site_user.id,
                },
            )
            template_index += 1
        entry_day += timedelta(days=1)

    issues = [
        (
            "Blocked site access - delivery truck",
            "low",
            "resolved",
            TODAY - timedelta(days=9),
            TODAY - timedelta(days=8),
            "Truck moved; delivery rescheduled to gate 2.",
        ),
        ("Scaffold inspection overdue", "high", "open", TODAY - timedelta(days=4), None, None),
        (
            "Retaining wall crack observed grid C",
            "critical",
            "open",
            TODAY - timedelta(days=2),
            None,
            None,
        ),
    ]
    for title, severity, status, raised, resolved, notes in issues:
        get_or_create(
            db,
            SiteIssue,
            project_id=project.id,
            title=title,
            defaults={
                "severity": severity,
                "status": status,
                "raised_date": raised,
                "resolved_date": resolved,
                "resolution_notes": notes,
                "created_by": site_user.id,
            },
        )


def seed_expenses(db, users) -> None:
    from app.modules.expenses.models import ExpenseClaim
    from app.modules.expenses.schemas import ExpenseClaimCreate
    from app.modules.expenses.service import approve_claim, create_claim, reject_claim

    project = db.scalar(select(Project).where(Project.code == "PRJ-2026-001"))
    if project is None:
        return
    if db.scalar(select(ExpenseClaim).limit(1)):
        return  # already seeded

    site_user, pm = users["site_manager"], users["project_manager"]

    approved = create_claim(
        db,
        project.id,
        ExpenseClaimCreate(
            category="fuel",
            expense_date=TODAY - timedelta(days=6),
            amount=Decimal("184.20"),
            description="Diesel for generator and telehandler",
            receipt_ref="FUEL-88231",
        ),
        site_user.id,
    )
    approve_claim(db, approved.id, pm)

    create_claim(
        db,
        project.id,
        ExpenseClaimCreate(
            category="transport",
            expense_date=TODAY - timedelta(days=2),
            amount=Decimal("95.00"),
            description="Hiab hire for rebar offload",
        ),
        site_user.id,
    )
    create_claim(
        db,
        project.id,
        ExpenseClaimCreate(
            category="tools",
            expense_date=TODAY - timedelta(days=1),
            amount=Decimal("62.50"),
            description="Replacement vibrator poker head",
            receipt_ref="TLS-1140",
        ),
        site_user.id,
    )
    rejected = create_claim(
        db,
        project.id,
        ExpenseClaimCreate(
            category="meals",
            expense_date=TODAY - timedelta(days=5),
            amount=Decimal("48.00"),
            description="Team lunch during pour",
        ),
        site_user.id,
    )
    reject_claim(db, rejected.id, "No receipt provided", pm)


STOCK_ITEMS = [
    (
        "CEM-425",
        "Cement 42.5N 50kg",
        "cement",
        "bag",
        Decimal("400"),
        [("120", "11.80"), ("200", "12.40")],
    ),
    ("REB-Y12", "Rebar Y12 6m length", "steel", "length", Decimal("150"), [("400", "9.20")]),
    ("BRK-STD", "Concrete brick standard", "masonry", "ea", Decimal("5000"), [("12000", "0.42")]),
    ("TIM-38", "Timber 38x114 SA pine", "timber", "m", Decimal("200"), [("600", "2.85")]),
    ("DSL", "Diesel", "fuel", "litre", Decimal("100"), [("40", "1.52")]),
    ("PNT-W", "PVA paint white", "finishes", "litre", Decimal("60"), [("180", "3.10")]),
    ("PPE-HV", "Hi-vis vest", "ppe", "ea", Decimal("20"), [("50", "4.00")]),
    ("TIL-300", "Floor tile 300x300", "finishes", "m2", Decimal("80"), [("240", "8.90")]),
]

# Valid EAN-13s so camera scanning and handheld scanners both resolve them
STOCK_BARCODES = {
    "CEM-425": "6001234500018",
    "REB-Y12": "6001234500025",
    "BRK-STD": "6001234500032",
    "TIM-38": "6001234500049",
    "DSL": "6001234500056",
    "PNT-W": "6001234500063",
    "PPE-HV": "6001234500070",
    "TIL-300": "6001234500087",
}


def seed_inventory(db, users) -> None:
    from app.modules.inventory.models import StockItem
    from app.modules.inventory.schemas import GoodsInRequest, IssueRequest, StockItemCreate
    from app.modules.inventory.service import create_item, goods_in, issue_to_project

    project = db.scalar(select(Project).where(Project.code == "PRJ-2026-001"))
    if db.scalar(select(StockItem).limit(1)):
        return  # already seeded
    proc = users["procurement_officer"]

    items = {}
    for code, name, category, unit, reorder, deliveries in STOCK_ITEMS:
        item = create_item(
            db,
            StockItemCreate(
                code=code,
                name=name,
                category=category,
                unit=unit,
                reorder_level=reorder,
                barcode=STOCK_BARCODES.get(code),
            ),
            proc.id,
        )
        for qty, cost in deliveries:
            goods_in(
                db,
                item.id,
                GoodsInRequest(
                    quantity=Decimal(qty),
                    unit_cost=Decimal(cost),
                    reference="Opening stock" if len(deliveries) == 1 else None,
                ),
                proc.id,
            )
        items[code] = item

    if project is not None:
        for code, qty in [("CEM-425", "80"), ("REB-Y12", "120"), ("BRK-STD", "3500")]:
            issue_to_project(
                db,
                items[code].id,
                IssueRequest(project_id=project.id, quantity=Decimal(qty)),
                users["site_manager"].id,
            )


def seed_valuations(db, users) -> None:
    from app.modules.valuations.models import Valuation
    from app.modules.valuations.schemas import ValuationCreate
    from app.modules.valuations.service import create_valuation, issue_valuation, pay_valuation

    project = db.scalar(select(Project).where(Project.code == "PRJ-2026-001"))
    if project is None or db.scalar(select(Valuation).limit(1)):
        return
    pm = users["project_manager"]

    v1 = create_valuation(
        db,
        project.id,
        ValuationCreate(
            period_end=TODAY - timedelta(days=75),
            gross_valuation=Decimal("300000.00"),
            notes="Valuation 1 — preliminaries and substructure to DPC",
        ),
        pm.id,
    )
    issue_valuation(db, v1.id, TODAY - timedelta(days=70))
    pay_valuation(db, v1.id, TODAY - timedelta(days=40))
    db.flush()  # session has autoflush off; make the transition visible to the next query

    v2 = create_valuation(
        db,
        project.id,
        ValuationCreate(
            period_end=TODAY - timedelta(days=45),
            gross_valuation=Decimal("620000.00"),
            notes="Valuation 2 — ground slab and columns to L1",
        ),
        pm.id,
    )
    issue_valuation(db, v2.id, TODAY - timedelta(days=40))
    db.flush()

    create_valuation(
        db,
        project.id,
        ValuationCreate(
            period_end=TODAY - timedelta(days=10),
            gross_valuation=Decimal("890000.00"),
            notes="Valuation 3 — L1 slab and columns to L2 (draft, under measure)",
        ),
        pm.id,
    )


def seed_purchase_orders(db, users) -> None:
    """One PO received into the store (WAC restock, no project cost) and one left
    issued so demos can receive it or drop its delivery note into the AI inbox."""
    from app.common.enums import PoDestination
    from app.modules.inventory.models import StockItem
    from app.modules.procurement.models import PurchaseOrder
    from app.modules.procurement.schemas import (
        PoCreate,
        PoItemCreate,
        PoReceive,
        PoStoreLineMapping,
    )
    from app.modules.procurement.service import create_po, issue_po, receive_po

    project = db.scalar(select(Project).where(Project.code == "PRJ-2026-001"))
    if project is None or db.scalar(select(PurchaseOrder).limit(1)):
        return
    proc = users["procurement_officer"]
    suppliers = {s.name: s for s in db.scalars(select(Supplier))}
    stock = {i.code: i for i in db.scalars(select(StockItem))}

    po1 = create_po(
        db,
        project.id,
        PoCreate(
            supplier_id=suppliers["Mashonaland Building Supplies"].id,
            items=[
                PoItemCreate(
                    description="Cement 42.5N 50kg",
                    unit="bag",
                    quantity=Decimal("300"),
                    unit_price=Decimal("12.10"),
                ),
                PoItemCreate(
                    description="PVA paint white",
                    unit="litre",
                    quantity=Decimal("100"),
                    unit_price=Decimal("3.05"),
                ),
            ],
        ),
        proc.id,
    )
    issue_po(db, po1.id)
    if "CEM-425" in stock and "PNT-W" in stock:
        receive_po(
            db,
            po1.id,
            PoReceive(
                received_date=TODAY - timedelta(days=3),
                destination=PoDestination.store,
                store_lines=[
                    PoStoreLineMapping(
                        po_item_id=po1.items[0].id, stock_item_id=stock["CEM-425"].id
                    ),
                    PoStoreLineMapping(po_item_id=po1.items[1].id, stock_item_id=stock["PNT-W"].id),
                ],
            ),
            proc.id,
        )

    po2 = create_po(
        db,
        project.id,
        PoCreate(
            supplier_id=suppliers["SteelCo Zimbabwe (Pvt) Ltd"].id,
            expected_delivery=TODAY + timedelta(days=7),
            items=[
                PoItemCreate(
                    description="Rebar Y12 6m length",
                    unit="length",
                    quantity=Decimal("500"),
                    unit_price=Decimal("9.10"),
                ),
                PoItemCreate(
                    description="Rebar Y16 6m length",
                    unit="length",
                    quantity=Decimal("200"),
                    unit_price=Decimal("15.40"),
                ),
            ],
        ),
        proc.id,
    )
    issue_po(db, po2.id)


WORKERS = [
    # (name, trade, basis, rate, pay items)
    ("Josiah Mapfumo", "Bricklayer", "daily", "38.00", [("allowance", "Transport", "12.00")]),
    ("Peter Chirwa", "Bricklayer", "daily", "38.00", []),
    ("Simba Dlamini", "Carpenter / shutterhand", "daily", "42.00", []),
    ("Nomsa Khumalo", "Steel fixer", "daily", "40.00", [("deduction", "Tool advance", "15.00")]),
    ("Gift Moyo", "General hand", "daily", "22.00", []),
    ("Tarisai Gumbo", "General hand", "daily", "22.00", []),
    ("Elias Phiri", "Crane operator", "hourly", "9.50", [("allowance", "Height pay", "20.00")]),
    ("Mercy Sibanda", "Site clerk", "hourly", "6.00", []),
]


def seed_payroll(db, users) -> None:
    from app.modules.payroll.models import Worker
    from app.modules.payroll.schemas import (
        PayItemCreate,
        PayRunCreate,
        TimesheetCreate,
        WorkerCreate,
    )
    from app.modules.payroll.service import (
        add_pay_item,
        approve_pay_run,
        create_pay_run,
        create_timesheet,
        create_worker,
    )

    if db.scalar(select(Worker).limit(1)):
        return  # already seeded
    pm, site = users["project_manager"], users["site_manager"]
    riverside = db.scalar(select(Project).where(Project.code == "PRJ-2026-001"))
    warehouse = db.scalar(select(Project).where(Project.code == "PRJ-2026-002"))
    if riverside is None or warehouse is None:
        return

    workers = []
    for name, trade, basis, rate, items in WORKERS:
        worker = create_worker(
            db,
            WorkerCreate(full_name=name, trade=trade, pay_basis=basis, rate=Decimal(rate)),
            pm.id,
        )
        for kind, label, amount in items:
            add_pay_item(db, worker.id, PayItemCreate(kind=kind, label=label, amount=Decimal(amount)))
        workers.append(worker)

    # Two weeks of weekday timesheets. Elias (crane) splits time with the
    # warehouse project; everyone else is on Riverside.
    def _week(start: date) -> None:
        for offset in range(7):
            day = start + timedelta(days=offset)
            if day.weekday() >= 5:
                continue
            for i, worker in enumerate(workers):
                if worker.pay_basis.value == "daily":
                    qty, ot = Decimal("1"), Decimal("0")
                else:
                    qty, ot = Decimal("8"), Decimal("2") if day.weekday() == 3 else Decimal("0")
                project = warehouse if (worker.trade == "Crane operator" and offset % 2) else riverside
                create_timesheet(
                    db,
                    TimesheetCreate(
                        worker_id=worker.id,
                        project_id=project.id,
                        work_date=day,
                        quantity=qty,
                        overtime_quantity=ot,
                    ),
                    site.id,
                )
                _ = i

    last_monday = TODAY - timedelta(days=TODAY.weekday())
    prev_monday = last_monday - timedelta(days=7)
    _week(prev_monday)
    _week(last_monday)

    # Last week's run approved (labour costs land in the ledgers)...
    run = create_pay_run(
        db,
        PayRunCreate(
            period_start=prev_monday,
            period_end=prev_monday + timedelta(days=6),
            notes="Weekly site labour",
        ),
        pm.id,
    )
    approve_pay_run(db, run.id, pm.id)
    # ...and this week's sits in draft for the demo.
    create_pay_run(
        db,
        PayRunCreate(period_start=last_monday, period_end=last_monday + timedelta(days=6)),
        pm.id,
    )


def seed_portal_link(db, users) -> str | None:
    from app.modules.portal.models import ClientAccessToken
    from app.modules.portal.schemas import PortalLinkCreate
    from app.modules.portal.service import create_link, portal_url

    if db.scalar(select(ClientAccessToken).limit(1)):
        return None
    riverside_client = db.scalar(
        select(Client).where(Client.name == "Riverside Property Group")
    )
    if riverside_client is None:
        return None
    _, raw = create_link(
        db,
        riverside_client.id,
        PortalLinkCreate(label="Demo link — J. Banda", expires_in_days=180),
        users["project_manager"].id,
    )
    return portal_url(raw)


def seed_measurement(db, users) -> None:
    """A measured draft valuation on the warehouse project (hybrid demo:
    Riverside stays single-figure, Mutare is measured line-by-line)."""
    from app.modules.valuations.models import Valuation
    from app.modules.valuations.schemas import (
        MeasurementLineIn,
        MeasurementSet,
        ValuationCreate,
    )
    from app.modules.valuations.service import create_valuation, set_measurement

    project = db.scalar(select(Project).where(Project.code == "PRJ-2026-002"))
    if project is None:
        return
    if db.scalar(select(Valuation).where(Valuation.project_id == project.id).limit(1)):
        return
    draft = create_valuation(
        db,
        project.id,
        ValuationCreate(
            period_end=TODAY - timedelta(days=3),
            gross_valuation=Decimal("1"),  # replaced by the measurement below
            notes="Valuation 1 — earthworks complete, pads underway (measured)",
        ),
        users["project_manager"].id,
    )
    items = {
        i.item_code: i
        for i in db.scalars(select(BoqItem).where(BoqItem.project_id == project.id))
    }
    measures = [("A.1", "5200"), ("A.2", "60"), ("A.3", "12")]
    lines = [
        MeasurementLineIn(boq_item_id=items[code].id, qty_to_date=Decimal(qty))
        for code, qty in measures
        if code in items
    ]
    if lines:
        set_measurement(db, draft.id, MeasurementSet(lines=lines))


def seed_requisitions(db, users) -> None:
    """Site requests waiting on procurement, including one deliberately aged
    so the aging queue demonstrates the delay it is meant to expose."""
    from app.modules.requisitions.models import Requisition
    from app.modules.requisitions.schemas import RequisitionCreate, RequisitionItemCreate
    from app.modules.requisitions.service import create_requisition

    if db.scalar(select(Requisition).limit(1)):
        return

    riverside = db.scalar(select(Project).where(Project.code == "PRJ-2026-001"))
    warehouse = db.scalar(select(Project).where(Project.code == "PRJ-2026-002"))
    specs = [
        (
            riverside,
            5,  # days ago — well past the urgency threshold
            "Slab pour Friday; site is down to half a day of cement.",
            [("Cement 42.5N 50kg", "bag", "200"), ("River sand", "m3", "18")],
        ),
        (
            warehouse,
            1,
            "Rebar for the pad bases, needed before the crew moves across.",
            [("Rebar Y12 6m length", "length", "150")],
        ),
    ]
    for project, days_ago, notes, lines in specs:
        if project is None:
            continue
        requisition = create_requisition(
            db,
            project.id,
            RequisitionCreate(
                needed_by=TODAY + timedelta(days=3),
                notes=notes,
                items=[
                    RequisitionItemCreate(
                        description=description, unit=unit, quantity=Decimal(qty)
                    )
                    for description, unit, qty in lines
                ],
            ),
            users["site_manager"].id,
        )
        # Backdate so the queue shows real ages rather than everything at zero
        requisition.created_at = requisition.created_at - timedelta(days=days_ago)
    db.flush()


PROJECT_COORDS = {
    "PRJ-2026-001": (Decimal("-17.783200"), Decimal("31.088900")),  # Riverside Drive, Harare
    "PRJ-2026-002": (Decimal("-18.944600"), Decimal("32.623100")),  # Feruka, Mutare
    "PRJ-2026-003": (Decimal("-17.828800"), Decimal("31.052900")),  # Harare CBD
}


def seed_coordinates(db) -> None:
    """Idempotent pin backfill so the site map has markers."""
    for code, (lat, lng) in PROJECT_COORDS.items():
        project = db.scalar(select(Project).where(Project.code == code))
        if project is not None and project.latitude is None:
            project.latitude = lat
            project.longitude = lng
    db.flush()


def main() -> None:
    if settings.environment == "production":
        print("Refusing to seed a production environment.")
        sys.exit(1)

    db = SessionLocal()
    try:
        get_or_create(db, CompanySettings, name="Demo Construction Co.")
        users = seed_users(db)
        clients = seed_clients(db)
        seed_riverside(db, users, clients)
        seed_warehouse(db, users, clients)
        seed_fitout(db, users, clients)
        seed_procurement(db, users)
        seed_site(db, users)
        seed_expenses(db, users)
        seed_inventory(db, users)
        seed_valuations(db, users)
        seed_purchase_orders(db, users)
        seed_payroll(db, users)
        seed_measurement(db, users)
        seed_requisitions(db, users)
        seed_coordinates(db)
        portal_link = seed_portal_link(db, users)
        db.commit()
        print("Seed complete.")
        print(f"Login with any of: {', '.join(u[0] for u in USERS)} / {DEV_PASSWORD}")
        if portal_link:
            print(f"Client portal demo link (Riverside Property Group): {portal_link}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
