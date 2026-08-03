import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.common.enums import BoqItemType, CostSource, ExpenseStatus
from app.modules.boq.models import BoqItem, BoqSection
from app.modules.costs.models import CostEntry
from app.modules.expenses.models import ExpenseClaim
from app.modules.inventory.models import StockItem
from app.modules.procurement.models import PurchaseOrder, Quote, Rfq
from app.modules.projects.service import get_project
from app.modules.reports.render import ReportColumn, ReportTable
from app.modules.users.models import User

ZERO = Decimal("0")


def project_cost_report(db: Session, project_id: uuid.UUID) -> ReportTable:
    project = get_project(db, project_id)
    actuals = dict(
        db.execute(
            select(CostEntry.boq_item_id, func.sum(CostEntry.amount))
            .where(CostEntry.project_id == project_id, CostEntry.boq_item_id.is_not(None))
            .group_by(CostEntry.boq_item_id)
        ).all()
    )
    unallocated = db.scalar(
        select(func.coalesce(func.sum(CostEntry.amount), 0)).where(
            CostEntry.project_id == project_id, CostEntry.boq_item_id.is_(None)
        )
    ) or ZERO

    sections = db.scalars(
        select(BoqSection)
        .where(BoqSection.project_id == project_id)
        .order_by(BoqSection.sort_order, BoqSection.code)
    ).all()

    rows = []
    total_budget = ZERO
    total_actual = ZERO
    for section in sections:
        for item in section.items:
            if item.item_type == BoqItemType.omission:
                continue
            actual = actuals.get(item.id, ZERO)
            variance = actual - item.amount
            rows.append(
                {
                    "section": f"{section.code} {section.title}",
                    "item_code": item.item_code,
                    "description": item.description,
                    "unit": item.unit,
                    "quantity": item.quantity,
                    "rate": item.rate,
                    "budget": item.amount,
                    "actual": actual,
                    "variance": variance,
                    "variance_pct": (
                        float(variance / item.amount) if item.amount else None
                    ),
                }
            )
            total_budget += item.amount
            total_actual += actual
    rows.append(
        {
            "section": "—",
            "item_code": "",
            "description": "Unallocated costs",
            "actual": unallocated,
            "variance": unallocated,
        }
    )
    total_actual += unallocated

    return ReportTable(
        title=f"Cost report {project.code}",
        columns=[
            ReportColumn("section", "Section", "text", 24),
            ReportColumn("item_code", "Item", "text", 10),
            ReportColumn("description", "Description", "text", 42),
            ReportColumn("unit", "Unit", "text", 8),
            ReportColumn("quantity", "Qty", "qty", 12),
            ReportColumn("rate", "Rate", "money", 12),
            ReportColumn("budget", "Budget", "money", 14),
            ReportColumn("actual", "Actual", "money", 14),
            ReportColumn("variance", "Variance", "money", 14),
            ReportColumn("variance_pct", "Var %", "pct", 10),
        ],
        rows=rows,
        totals={"budget": total_budget, "actual": total_actual,
                "variance": total_actual - total_budget},
    )


def procurement_register(db: Session, project_id: uuid.UUID | None) -> ReportTable:
    rows = []

    rfq_query = select(Rfq).options(joinedload(Rfq.project))
    if project_id:
        rfq_query = rfq_query.where(Rfq.project_id == project_id)
    for rfq in db.scalars(rfq_query.order_by(Rfq.created_at)).unique():
        rows.append(
            {
                "doc_type": "RFQ",
                "doc_number": rfq.doc_number,
                "project": rfq.project.code if rfq.project else "",
                "supplier": "",
                "status": rfq.status.value,
                "doc_date": rfq.created_at.date(),
                "amount": None,
                "linked_doc": "",
                "received_to": "",
            }
        )

    quote_query = (
        select(Quote)
        .options(joinedload(Quote.supplier), joinedload(Quote.rfq).joinedload(Rfq.project))
    )
    if project_id:
        quote_query = quote_query.join(Rfq, Rfq.id == Quote.rfq_id).where(
            Rfq.project_id == project_id
        )
    for quote in db.scalars(quote_query.order_by(Quote.created_at)).unique():
        rows.append(
            {
                "doc_type": "Quote",
                "doc_number": (
                    f"{quote.rfq.doc_number} / "
                    f"{quote.supplier.name if quote.supplier else '?'}"
                ),
                "project": quote.rfq.project.code if quote.rfq and quote.rfq.project else "",
                "supplier": quote.supplier.name if quote.supplier else "",
                "status": quote.status.value,
                "doc_date": quote.received_date,
                "amount": quote.total_amount,
                "linked_doc": quote.rfq.doc_number if quote.rfq else "",
                "received_to": "",
            }
        )

    po_query = select(PurchaseOrder).options(
        joinedload(PurchaseOrder.supplier), joinedload(PurchaseOrder.project)
    )
    if project_id:
        po_query = po_query.where(PurchaseOrder.project_id == project_id)
    total_po = ZERO
    for po in db.scalars(po_query.order_by(PurchaseOrder.created_at)).unique():
        rows.append(
            {
                "doc_type": "PO",
                "doc_number": po.doc_number,
                "project": po.project.code if po.project else "",
                "supplier": po.supplier.name if po.supplier else "",
                "status": po.status.value,
                "doc_date": po.order_date,
                "amount": po.total_amount,
                "linked_doc": "",
                "received_to": po.received_to.value if po.received_to else "",
            }
        )
        total_po += po.total_amount

    return ReportTable(
        title="Procurement register",
        columns=[
            ReportColumn("doc_type", "Type", "text", 8),
            ReportColumn("doc_number", "Document", "text", 30),
            ReportColumn("project", "Project", "text", 14),
            ReportColumn("supplier", "Supplier", "text", 28),
            ReportColumn("status", "Status", "text", 12),
            ReportColumn("doc_date", "Date", "date", 12),
            ReportColumn("amount", "Amount", "money", 14),
            ReportColumn("linked_doc", "Linked", "text", 14),
            ReportColumn("received_to", "Received to", "text", 12),
        ],
        rows=rows,
        totals={"amount": total_po},
    )


def expense_register(
    db: Session, project_id: uuid.UUID | None, status: ExpenseStatus | None
) -> ReportTable:
    query = select(ExpenseClaim)
    if project_id:
        query = query.where(ExpenseClaim.project_id == project_id)
    if status:
        query = query.where(ExpenseClaim.status == status)
    claims = db.scalars(query.order_by(ExpenseClaim.created_at)).all()

    users = {
        u.id: u.full_name
        for u in db.scalars(select(User)).all()
    }
    from app.modules.projects.models import Project

    projects = {p.id: p.code for p in db.scalars(select(Project)).all()}

    rows = []
    total = ZERO
    approved_total = ZERO
    for claim in claims:
        rows.append(
            {
                "doc_number": claim.doc_number,
                "project": projects.get(claim.project_id, ""),
                "claimant": users.get(claim.created_by, ""),
                "category": claim.category.value,
                "expense_date": claim.expense_date,
                "description": claim.description,
                "amount": claim.amount,
                "status": claim.status.value,
                "approver": users.get(claim.approved_by, ""),
            }
        )
        total += claim.amount
        if claim.status == ExpenseStatus.approved:
            approved_total += claim.amount

    return ReportTable(
        title="Expense register",
        columns=[
            ReportColumn("doc_number", "Claim", "text", 14),
            ReportColumn("project", "Project", "text", 14),
            ReportColumn("claimant", "Claimant", "text", 20),
            ReportColumn("category", "Category", "text", 14),
            ReportColumn("expense_date", "Date", "date", 12),
            ReportColumn("description", "Description", "text", 40),
            ReportColumn("amount", "Amount", "money", 14),
            ReportColumn("status", "Status", "text", 12),
            ReportColumn("approver", "Decided by", "text", 20),
        ],
        rows=rows,
        totals={"amount": total, "description": f"(approved: {approved_total})"},
    )


def stock_valuation(db: Session, low_stock_only: bool) -> ReportTable:
    query = select(StockItem).where(StockItem.is_active.is_(True))
    if low_stock_only:
        query = query.where(StockItem.qty_on_hand <= StockItem.reorder_level)
    items = db.scalars(query.order_by(StockItem.code)).all()

    rows = []
    total_value = ZERO
    for item in items:
        value = (item.qty_on_hand * item.unit_cost).quantize(Decimal("0.01"))
        rows.append(
            {
                "code": item.code,
                "name": item.name,
                "category": item.category or "",
                "unit": item.unit,
                "qty_on_hand": item.qty_on_hand,
                "unit_cost": item.unit_cost,
                "value": value,
                "reorder_level": item.reorder_level,
                "low_stock": "YES" if item.qty_on_hand <= item.reorder_level else "",
            }
        )
        total_value += value

    return ReportTable(
        title="Stock valuation",
        columns=[
            ReportColumn("code", "Code", "text", 12),
            ReportColumn("name", "Item", "text", 32),
            ReportColumn("category", "Category", "text", 14),
            ReportColumn("unit", "Unit", "text", 8),
            ReportColumn("qty_on_hand", "On hand", "qty", 12),
            ReportColumn("unit_cost", "Avg cost", "money", 12),
            ReportColumn("value", "Value", "money", 14),
            ReportColumn("reorder_level", "Reorder", "qty", 12),
            ReportColumn("low_stock", "Low", "text", 6),
        ],
        rows=rows,
        totals={"value": total_value},
    )


def cost_ledger(
    db: Session,
    project_id: uuid.UUID,
    source: CostSource | None,
    date_from: date | None,
    date_to: date | None,
) -> ReportTable:
    project = get_project(db, project_id)
    query = select(CostEntry).where(CostEntry.project_id == project_id)
    if source:
        query = query.where(CostEntry.source == source)
    if date_from:
        query = query.where(CostEntry.entry_date >= date_from)
    if date_to:
        query = query.where(CostEntry.entry_date <= date_to)
    entries = db.scalars(query.order_by(CostEntry.entry_date, CostEntry.created_at)).all()

    boq_codes = {
        item.id: item.item_code
        for item in db.scalars(select(BoqItem).where(BoqItem.project_id == project_id))
    }

    rows = []
    total = ZERO
    for entry in entries:
        rows.append(
            {
                "entry_date": entry.entry_date,
                "source": entry.source.value,
                "reference": entry.reference or "",
                "boq_item": boq_codes.get(entry.boq_item_id, ""),
                "description": entry.description or "",
                "quantity": entry.quantity,
                "amount": entry.amount,
            }
        )
        total += entry.amount

    return ReportTable(
        title=f"Cost ledger {project.code}",
        columns=[
            ReportColumn("entry_date", "Date", "date", 12),
            ReportColumn("source", "Source", "text", 16),
            ReportColumn("reference", "Reference", "text", 16),
            ReportColumn("boq_item", "BOQ item", "text", 10),
            ReportColumn("description", "Description", "text", 46),
            ReportColumn("quantity", "Qty", "qty", 12),
            ReportColumn("amount", "Amount", "money", 14),
        ],
        rows=rows,
        totals={"amount": total},
    )
