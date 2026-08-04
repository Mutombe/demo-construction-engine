"""Global record search behind the command palette.

One round trip across every addressable entity, ranked so an exact document
number beats a fuzzy name match. Each entity contributes a small capped slice
rather than one type flooding the list.

Results respect role: payroll records only reach roles that can read payroll,
matching the gating on the payroll endpoints themselves.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.common.enums import UserRole
from app.modules.search.schemas import SearchHit, SearchResults
from app.modules.users.models import User

# Per-entity cap: enough to find what you meant, small enough that one noisy
# entity cannot push everything else off the list.
PER_TYPE_LIMIT = 5
TOTAL_LIMIT = 25
MIN_QUERY = 2


def _rank(hit: SearchHit, needle: str) -> tuple[int, int, str]:
    """Exact code match first, then prefix matches, then everything else.

    Someone typing a document number wants that document, not a description
    that happens to contain the digits.
    """
    code = (hit.code or "").lower()
    label = hit.label.lower()
    if code == needle:
        tier = 0
    elif code.startswith(needle):
        tier = 1
    elif label.startswith(needle):
        tier = 2
    elif needle in code:
        tier = 3
    else:
        tier = 4
    return (tier, len(hit.label), hit.label.lower())


def search(db: Session, query: str, user: User) -> SearchResults:
    needle = query.strip().lower()
    if len(needle) < MIN_QUERY:
        return SearchResults(query=query, hits=[], total=0, truncated=False)

    pattern = f"%{needle}%"
    hits: list[SearchHit] = []

    def add(rows, build):
        for row in rows:
            hits.append(build(row))

    # --- Projects
    from app.modules.projects.models import Project

    add(
        db.scalars(
            select(Project)
            .options(joinedload(Project.client))
            .where(Project.code.ilike(pattern) | Project.name.ilike(pattern))
            .limit(PER_TYPE_LIMIT)
        ),
        lambda p: SearchHit(
            type="project",
            type_label="Projects",
            id=str(p.id),
            label=p.name,
            sublabel=p.client.name if p.client else None,
            code=p.code,
            url=f"/projects/{p.id}",
        ),
    )

    # --- Clients
    from app.modules.clients.models import Client

    add(
        db.scalars(
            select(Client)
            .where(Client.name.ilike(pattern) | Client.contact_person.ilike(pattern))
            .limit(PER_TYPE_LIMIT)
        ),
        lambda c: SearchHit(
            type="client",
            type_label="Clients",
            id=str(c.id),
            label=c.name,
            sublabel=c.contact_person,
            code=None,
            url=f"/clients/{c.id}",
        ),
    )

    # --- Suppliers
    from app.modules.procurement.models import (
        PurchaseOrder,
        Rfq,
        Supplier,
    )

    add(
        db.scalars(
            select(Supplier)
            .where(Supplier.name.ilike(pattern) | Supplier.categories.ilike(pattern))
            .limit(PER_TYPE_LIMIT)
        ),
        lambda s: SearchHit(
            type="supplier",
            type_label="Suppliers",
            id=str(s.id),
            label=s.name,
            sublabel=s.categories,
            code=None,
            url=f"/procurement/suppliers/{s.id}",
        ),
    )

    # --- Purchase orders
    add(
        db.scalars(
            select(PurchaseOrder)
            .options(
                joinedload(PurchaseOrder.supplier), joinedload(PurchaseOrder.project)
            )
            .where(PurchaseOrder.doc_number.ilike(pattern))
            .limit(PER_TYPE_LIMIT)
        ),
        lambda po: SearchHit(
            type="purchase_order",
            type_label="Purchase Orders",
            id=str(po.id),
            label=po.supplier.name if po.supplier else "Purchase order",
            sublabel=f"{po.status.value} · {po.project.name if po.project else ''}".strip(
                " ·"
            ),
            code=po.doc_number,
            url=f"/procurement/pos/{po.id}",
        ),
    )

    # --- RFQs
    add(
        db.scalars(
            select(Rfq)
            .options(joinedload(Rfq.project))
            .where(Rfq.doc_number.ilike(pattern) | Rfq.title.ilike(pattern))
            .limit(PER_TYPE_LIMIT)
        ),
        lambda r: SearchHit(
            type="rfq",
            type_label="RFQs",
            id=str(r.id),
            label=r.title,
            sublabel=f"{r.status.value} · {r.project.name if r.project else ''}".strip(" ·"),
            code=r.doc_number,
            url=f"/procurement/rfqs/{r.id}",
        ),
    )

    # --- Requisitions
    from app.modules.requisitions.models import Requisition

    add(
        db.scalars(
            select(Requisition)
            .options(joinedload(Requisition.project))
            .where(Requisition.doc_number.ilike(pattern))
            .limit(PER_TYPE_LIMIT)
        ),
        lambda r: SearchHit(
            type="requisition",
            type_label="Material Requests",
            id=str(r.id),
            label=r.project.name if r.project else "Material request",
            sublabel=r.status.value,
            code=r.doc_number,
            url=f"/procurement/requisitions/{r.id}",
        ),
    )

    # --- Stock items (barcode included: scanners type into the palette too)
    from app.modules.inventory.models import StockItem

    add(
        db.scalars(
            select(StockItem)
            .where(
                StockItem.code.ilike(pattern)
                | StockItem.name.ilike(pattern)
                | StockItem.barcode.ilike(pattern)
            )
            .limit(PER_TYPE_LIMIT)
        ),
        lambda i: SearchHit(
            type="stock_item",
            type_label="Stock Items",
            id=str(i.id),
            label=i.name,
            sublabel=i.category,
            code=i.code,
            url=f"/inventory/{i.id}",
        ),
    )

    # --- Valuations
    from app.modules.valuations.models import Valuation

    add(
        db.scalars(
            select(Valuation)
            .options(joinedload(Valuation.project))
            .where(Valuation.doc_number.ilike(pattern))
            .limit(PER_TYPE_LIMIT)
        ),
        lambda v: SearchHit(
            type="valuation",
            type_label="Valuations",
            id=str(v.id),
            label=v.project.name if v.project else "Valuation",
            sublabel=v.status.value,
            code=v.doc_number,
            url=f"/valuations/{v.id}",
        ),
    )

    # --- Expense claims
    from app.modules.expenses.models import ExpenseClaim

    add(
        db.scalars(
            select(ExpenseClaim)
            .where(
                ExpenseClaim.doc_number.ilike(pattern)
                | ExpenseClaim.description.ilike(pattern)
            )
            .limit(PER_TYPE_LIMIT)
        ),
        lambda e: SearchHit(
            type="expense",
            type_label="Expenses",
            id=str(e.id),
            label=e.description[:80],
            sublabel=e.status.value,
            code=e.doc_number,
            url=f"/expenses/{e.id}",
        ),
    )

    # --- Workers, only for roles that may read payroll at all
    if user.role in (UserRole.admin, UserRole.project_manager):
        from app.modules.payroll.models import Worker

        add(
            db.scalars(
                select(Worker)
                .where(Worker.full_name.ilike(pattern) | Worker.trade.ilike(pattern))
                .limit(PER_TYPE_LIMIT)
            ),
            lambda w: SearchHit(
                type="worker",
                type_label="Workers",
                id=str(w.id),
                label=w.full_name,
                sublabel=w.trade,
                code=None,
                url=f"/payroll/workers/{w.id}",
            ),
        )

    hits.sort(key=lambda hit: _rank(hit, needle))
    return SearchResults(
        query=query,
        hits=hits[:TOTAL_LIMIT],
        total=len(hits),
        truncated=len(hits) > TOTAL_LIMIT,
    )
