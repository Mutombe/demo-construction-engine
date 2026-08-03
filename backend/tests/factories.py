import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.common.enums import UserRole, WorkStatus
from app.core.security import create_access_token, hash_password
from app.modules.boq.models import BoqItem, BoqSection
from app.modules.clients.models import Client
from app.modules.costs.models import CostEntry
from app.modules.projects.models import Phase, Project
from app.modules.tasks.models import Task
from app.modules.users.models import User

DEFAULT_PASSWORD = "testpass123"

_counter = 0


def _next() -> int:
    global _counter
    _counter += 1
    return _counter


def make_user(db: Session, role: UserRole = UserRole.viewer, **kw) -> User:
    n = _next()
    user = User(
        email=kw.pop("email", f"user{n}@test.local"),
        full_name=kw.pop("full_name", f"Test User {n}"),
        hashed_password=hash_password(kw.pop("password", DEFAULT_PASSWORD)),
        role=role,
        **kw,
    )
    db.add(user)
    db.flush()
    return user


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


def make_client_record(db: Session, **kw) -> Client:
    n = _next()
    client = Client(name=kw.pop("name", f"Client {n}"), **kw)
    db.add(client)
    db.flush()
    return client


def make_project(db: Session, client: Client | None = None, **kw) -> Project:
    n = _next()
    if client is None:
        client = make_client_record(db)
    project = Project(
        code=kw.pop("code", f"PRJ-TEST-{n:03d}"),
        name=kw.pop("name", f"Project {n}"),
        client_id=client.id,
        **kw,
    )
    db.add(project)
    db.flush()
    return project


def make_phase(db: Session, project: Project, **kw) -> Phase:
    n = _next()
    phase = Phase(
        project_id=project.id,
        name=kw.pop("name", f"Phase {n}"),
        sequence=kw.pop("sequence", n),
        **kw,
    )
    db.add(phase)
    db.flush()
    return phase


def make_task(db: Session, project: Project, **kw) -> Task:
    n = _next()
    task = Task(
        project_id=project.id,
        name=kw.pop("name", f"Task {n}"),
        planned_start=kw.pop("planned_start", date.today()),
        planned_end=kw.pop("planned_end", date.today() + timedelta(days=5)),
        **kw,
    )
    db.add(task)
    db.flush()
    return task


def make_boq_section(db: Session, project: Project, **kw) -> BoqSection:
    n = _next()
    section = BoqSection(
        project_id=project.id,
        code=kw.pop("code", f"S{n}"),
        title=kw.pop("title", f"Section {n}"),
        **kw,
    )
    db.add(section)
    db.flush()
    return section


def make_boq_item(db: Session, section: BoqSection, **kw) -> BoqItem:
    n = _next()
    item = BoqItem(
        section_id=section.id,
        project_id=section.project_id,
        item_code=kw.pop("item_code", f"I{n}"),
        description=kw.pop("description", f"Item {n}"),
        unit=kw.pop("unit", "m3"),
        quantity=kw.pop("quantity", Decimal("10")),
        rate=kw.pop("rate", Decimal("100")),
        **kw,
    )
    db.add(item)
    db.flush()
    db.refresh(item)
    return item


def make_cost_entry(db: Session, project: Project, **kw) -> CostEntry:
    entry = CostEntry(
        project_id=project.id,
        entry_date=kw.pop("entry_date", date.today()),
        amount=kw.pop("amount", Decimal("500")),
        **kw,
    )
    db.add(entry)
    db.flush()
    return entry


def make_supplier(db: Session, **kw):
    from app.modules.procurement.models import Supplier

    n = _next()
    supplier = Supplier(name=kw.pop("name", f"Supplier {n}"), **kw)
    db.add(supplier)
    db.flush()
    return supplier


def make_rfq(db: Session, project: Project, boq_items: list[BoqItem], **kw):
    from app.common.enums import RfqStatus
    from app.modules.procurement.models import Rfq, RfqItem

    n = _next()
    rfq = Rfq(
        project_id=project.id,
        doc_number=kw.pop("doc_number", f"RFQ-TEST-{n:03d}"),
        title=kw.pop("title", f"RFQ {n}"),
        status=kw.pop("status", RfqStatus.issued),
        items=[
            RfqItem(
                boq_item_id=item.id,
                description=item.description,
                unit=item.unit,
                quantity=item.quantity,
                sort_order=i,
            )
            for i, item in enumerate(boq_items)
        ],
        **kw,
    )
    db.add(rfq)
    db.flush()
    return rfq


def make_quote(db: Session, rfq, supplier, prices: dict | None = None, **kw):
    """prices: {rfq_item_id: unit_price}; defaults to 100 per unit on all lines."""
    from app.modules.procurement.models import Quote, QuoteItem

    if prices is None:
        prices = {item.id: Decimal("100") for item in rfq.items}
    rfq_items = {item.id: item for item in rfq.items}
    items = [
        QuoteItem(
            rfq_item_id=item_id,
            description=rfq_items[item_id].description,
            unit=rfq_items[item_id].unit,
            quantity=rfq_items[item_id].quantity,
            unit_price=Decimal(str(price)),
        )
        for item_id, price in prices.items()
    ]
    total = sum(
        (rfq_items[iid].quantity * Decimal(str(p)) for iid, p in prices.items()),
        Decimal("0"),
    )
    quote = Quote(
        rfq_id=rfq.id,
        supplier_id=supplier.id,
        total_amount=total,
        items=items,
        **kw,
    )
    db.add(quote)
    db.flush()
    return quote


def done(task: Task) -> Task:
    task.status = WorkStatus.done
    task.progress_pct = 100
    return task


def fake_uuid() -> str:
    return str(uuid.uuid4())
