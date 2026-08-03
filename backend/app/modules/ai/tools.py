"""Read-only chat tools. Definitions are module-level constants in a fixed order
so the request tool list stays byte-stable for prompt caching."""

import json
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import BoqItemType
from app.modules.boq.models import BoqItem
from app.modules.boq.service import boq_summary
from app.modules.costs.models import CostEntry
from app.modules.procurement.models import PurchaseOrder, Supplier
from app.modules.procurement.service import list_quotes, rfq_detail
from app.modules.projects.models import Project
from app.modules.projects.service import project_summary

ROW_CAP = 50


def _obj(schema_props: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": schema_props,
        "required": required,
        "additionalProperties": False,
    }


_PROJECT_ID = {"project_id": {"type": "string", "description": "Project UUID"}}

CHAT_TOOLS = [
    {
        "name": "list_projects",
        "description": (
            "List all projects with id, code, name, status and client. Call this first "
            "when the user refers to a project by name and you need its id."
        ),
        "input_schema": _obj({}, []),
    },
    {
        "name": "get_project_summary",
        "description": (
            "Progress percentage, budget vs actual spend, overdue task count and dates "
            "for one project. Call when asked about a project's health, progress or budget."
        ),
        "input_schema": _obj(_PROJECT_ID, ["project_id"]),
    },
    {
        "name": "get_boq_summary",
        "description": (
            "Bill of Quantities totals by section and cost category for a project, "
            "including budget vs actual and variation totals."
        ),
        "input_schema": _obj(_PROJECT_ID, ["project_id"]),
    },
    {
        "name": "list_boq_items",
        "description": (
            "BOQ line items for a project (code, description, unit, qty, rate, amount). "
            "Call before answering questions about specific bill items or rates. "
            "Optional text filter."
        ),
        "input_schema": _obj(
            {**_PROJECT_ID, "search": {"type": "string", "description": "Filter text"}},
            ["project_id"],
        ),
    },
    {
        "name": "get_budget_status",
        "description": (
            "Per-BOQ-item budget vs actual spend for a project, flagging overspent "
            "lines. Call when asked which items are over budget or where money went."
        ),
        "input_schema": _obj(_PROJECT_ID, ["project_id"]),
    },
    {
        "name": "list_rfqs",
        "description": "RFQs for a project with doc number, title, status and quote count.",
        "input_schema": _obj(_PROJECT_ID, ["project_id"]),
    },
    {
        "name": "get_rfq",
        "description": "One RFQ in detail: line items and its quotes with totals and status.",
        "input_schema": _obj({"rfq_id": {"type": "string", "description": "RFQ UUID"}}, ["rfq_id"]),
    },
    {
        "name": "list_quotes",
        "description": ("Supplier quotes on an RFQ: totals, coverage of RFQ lines, terms, status."),
        "input_schema": _obj({"rfq_id": {"type": "string", "description": "RFQ UUID"}}, ["rfq_id"]),
    },
    {
        "name": "list_purchase_orders",
        "description": "Purchase orders for a project with doc number, supplier, status, total.",
        "input_schema": _obj(_PROJECT_ID, ["project_id"]),
    },
    {
        "name": "list_suppliers",
        "description": "The supplier registry with contact info and categories. Optional search.",
        "input_schema": _obj({"search": {"type": "string", "description": "Filter text"}}, []),
    },
    # M3 tools appended at the end so the existing prefix stays cache-stable
    {
        "name": "get_site_diary",
        "description": (
            "Recent daily site diary entries for a project: date, weather, labour "
            "headcount, plant on site, work done, delays. Call when asked what happened "
            "on site or about weather/labour history."
        ),
        "input_schema": _obj(
            {
                **_PROJECT_ID,
                "days": {"type": "integer", "description": "Days back to look (default 14)"},
            },
            ["project_id"],
        ),
    },
    {
        "name": "list_site_issues",
        "description": (
            "Site issues/incidents for a project with severity, status and dates. "
            "Defaults to open issues; pass status 'resolved' or 'all' for history."
        ),
        "input_schema": _obj(
            {
                **_PROJECT_ID,
                "status": {
                    "type": "string",
                    "enum": ["open", "resolved", "all"],
                    "description": "Filter by status (default open)",
                },
            },
            ["project_id"],
        ),
    },
    {
        "name": "list_expense_claims",
        "description": (
            "Expense claims with doc number, claimant, category, amount and status. "
            "Optional project and status filters; defaults to pending claims."
        ),
        "input_schema": _obj(
            {
                "project_id": {"type": "string", "description": "Optional project UUID"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "approved", "rejected", "cancelled", "all"],
                    "description": "Filter by status (default pending)",
                },
            },
            [],
        ),
    },
    {
        "name": "get_stock_levels",
        "description": (
            "Store stock items with quantity on hand, unit cost, reorder level and a "
            "low_stock flag. Call when asked about stock, inventory value or reordering."
        ),
        "input_schema": _obj(
            {
                "search": {"type": "string", "description": "Filter by code/name/category"},
                "low_stock_only": {
                    "type": "boolean",
                    "description": "Only items at or below reorder level",
                },
            },
            [],
        ),
    },
    # NOTE: append-only past this point — the tool list must stay byte-stable
    # as a prefix for prompt caching.
    {
        "name": "get_ingestion_history",
        "description": (
            "Documents that came through the AI inbox: filename, detected type, status "
            "(needs_info/drafted/posted/rejected), summary, confidence and what was posted. "
            "Call when asked what came through the inbox, what was scanned/uploaded, or "
            "what documents are awaiting review."
        ),
        "input_schema": _obj(
            {
                "days": {"type": "integer", "description": "Days back to look (default 7)"},
                "status": {
                    "type": "string",
                    "description": "Filter: received|failed|needs_info|drafted|posted|rejected",
                },
                "doc_type": {
                    "type": "string",
                    "description": (
                        "Filter: supplier_invoice|expense_receipt|delivery_note|supplier_quote"
                    ),
                },
            },
            [],
        ),
    },
]


@dataclass
class ToolOutput:
    text: str
    is_error: bool = False


def _dump(data) -> str:
    def default(value):
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(value)

    return json.dumps(data, default=default)


def _uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value)


def _tool_list_projects(db: Session, args: dict) -> str:
    rows = db.execute(
        select(Project.id, Project.code, Project.name, Project.status).limit(ROW_CAP)
    ).all()
    return _dump(
        [{"id": r.id, "code": r.code, "name": r.name, "status": r.status.value} for r in rows]
    )


def _tool_get_project_summary(db: Session, args: dict) -> str:
    return project_summary(db, _uuid(args["project_id"])).model_dump_json()


def _tool_get_boq_summary(db: Session, args: dict) -> str:
    return boq_summary(db, _uuid(args["project_id"])).model_dump_json()


def _tool_list_boq_items(db: Session, args: dict) -> str:
    query = select(BoqItem).where(BoqItem.project_id == _uuid(args["project_id"]))
    if args.get("search"):
        query = query.where(
            BoqItem.description.ilike(f"%{args['search']}%")
            | BoqItem.item_code.ilike(f"%{args['search']}%")
        )
    items = db.scalars(query.order_by(BoqItem.item_code).limit(ROW_CAP)).all()
    return _dump(
        [
            {
                "id": i.id,
                "code": i.item_code,
                "description": i.description,
                "unit": i.unit,
                "quantity": i.quantity,
                "rate": i.rate,
                "amount": i.amount,
                "category": i.cost_category.value,
            }
            for i in items
        ]
    )


def _tool_get_budget_status(db: Session, args: dict) -> str:
    project_id = _uuid(args["project_id"])
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
    )
    items = db.scalars(
        select(BoqItem)
        .where(BoqItem.project_id == project_id, BoqItem.item_type != BoqItemType.omission)
        .order_by(BoqItem.item_code)
        .limit(ROW_CAP)
    ).all()
    rows = []
    for i in items:
        actual = actuals.get(i.id, Decimal("0"))
        rows.append(
            {
                "code": i.item_code,
                "description": i.description,
                "budget": i.amount,
                "actual": actual,
                "over_budget": actual > i.amount,
            }
        )
    return _dump({"items": rows, "unallocated_actual": unallocated})


def _tool_list_rfqs(db: Session, args: dict) -> str:
    from app.modules.procurement.service import list_rfqs as svc_list_rfqs

    rfqs, _total = svc_list_rfqs(db, _uuid(args["project_id"]), 1, ROW_CAP)
    return _dump([r.model_dump() for r in rfqs])


def _tool_get_rfq(db: Session, args: dict) -> str:
    return rfq_detail(db, _uuid(args["rfq_id"])).model_dump_json()


def _tool_list_quotes(db: Session, args: dict) -> str:
    quotes = list_quotes(db, _uuid(args["rfq_id"]))
    return _dump([q.model_dump(exclude={"items"}) | {"line_count": len(q.items)} for q in quotes])


def _tool_list_purchase_orders(db: Session, args: dict) -> str:
    pos = db.scalars(
        select(PurchaseOrder)
        .where(PurchaseOrder.project_id == _uuid(args["project_id"]))
        .order_by(PurchaseOrder.created_at.desc())
        .limit(ROW_CAP)
    ).all()
    return _dump(
        [
            {
                "id": p.id,
                "doc_number": p.doc_number,
                "supplier": p.supplier.name if p.supplier else None,
                "status": p.status.value,
                "total_amount": p.total_amount,
                "order_date": str(p.order_date),
            }
            for p in pos
        ]
    )


def _tool_list_suppliers(db: Session, args: dict) -> str:
    query = select(Supplier)
    if args.get("search"):
        query = query.where(
            Supplier.name.ilike(f"%{args['search']}%")
            | Supplier.categories.ilike(f"%{args['search']}%")
        )
    suppliers = db.scalars(query.order_by(Supplier.name).limit(ROW_CAP)).all()
    return _dump(
        [
            {
                "id": s.id,
                "name": s.name,
                "contact": s.contact_name,
                "email": s.email,
                "phone": s.phone,
                "categories": s.categories,
                "active": s.is_active,
            }
            for s in suppliers
        ]
    )


def _tool_get_site_diary(db: Session, args: dict) -> str:
    from datetime import date, timedelta

    from app.modules.site.models import SiteDiaryEntry

    days = int(args.get("days") or 14)
    cutoff = date.today() - timedelta(days=days)
    entries = db.scalars(
        select(SiteDiaryEntry)
        .where(
            SiteDiaryEntry.project_id == _uuid(args["project_id"]),
            SiteDiaryEntry.entry_date >= cutoff,
        )
        .order_by(SiteDiaryEntry.entry_date.desc())
        .limit(ROW_CAP)
    ).all()
    return _dump(
        [
            {
                "date": str(e.entry_date),
                "weather": e.weather.value,
                "labour": e.labour_headcount,
                "plant": e.plant_equipment,
                "work_done": e.work_done,
                "delays": e.delays,
            }
            for e in entries
        ]
    )


def _tool_list_site_issues(db: Session, args: dict) -> str:
    from app.common.enums import IssueStatus
    from app.modules.site.models import SiteIssue

    query = select(SiteIssue).where(SiteIssue.project_id == _uuid(args["project_id"]))
    status = args.get("status") or "open"
    if status != "all":
        query = query.where(SiteIssue.status == IssueStatus(status))
    issues = db.scalars(query.order_by(SiteIssue.raised_date.desc()).limit(ROW_CAP)).all()
    return _dump(
        [
            {
                "title": i.title,
                "severity": i.severity.value,
                "status": i.status.value,
                "raised": str(i.raised_date),
                "resolved": str(i.resolved_date) if i.resolved_date else None,
                "description": i.description,
            }
            for i in issues
        ]
    )


def _tool_list_expense_claims(db: Session, args: dict) -> str:
    from app.common.enums import ExpenseStatus
    from app.modules.expenses.models import ExpenseClaim
    from app.modules.users.models import User

    query = select(ExpenseClaim, User.full_name).outerjoin(User, User.id == ExpenseClaim.created_by)
    if args.get("project_id"):
        query = query.where(ExpenseClaim.project_id == _uuid(args["project_id"]))
    status = args.get("status") or "pending"
    if status != "all":
        query = query.where(ExpenseClaim.status == ExpenseStatus(status))
    rows = db.execute(query.order_by(ExpenseClaim.created_at.desc()).limit(ROW_CAP)).all()
    return _dump(
        [
            {
                "doc_number": c.doc_number,
                "claimant": name,
                "category": c.category.value,
                "amount": c.amount,
                "status": c.status.value,
                "date": str(c.expense_date),
                "description": c.description,
            }
            for c, name in rows
        ]
    )


def _tool_get_stock_levels(db: Session, args: dict) -> str:
    from app.modules.inventory.models import StockItem

    query = select(StockItem).where(StockItem.is_active.is_(True))
    if args.get("search"):
        term = f"%{args['search']}%"
        query = query.where(
            StockItem.code.ilike(term) | StockItem.name.ilike(term) | StockItem.category.ilike(term)
        )
    if args.get("low_stock_only"):
        query = query.where(StockItem.qty_on_hand <= StockItem.reorder_level)
    items = db.scalars(query.order_by(StockItem.code).limit(ROW_CAP)).all()
    return _dump(
        [
            {
                "code": i.code,
                "name": i.name,
                "unit": i.unit,
                "qty_on_hand": i.qty_on_hand,
                "unit_cost": i.unit_cost,
                "stock_value": (i.qty_on_hand * i.unit_cost),
                "reorder_level": i.reorder_level,
                "low_stock": i.qty_on_hand <= i.reorder_level,
            }
            for i in items
        ]
    )


def _tool_get_ingestion_history(db: Session, args: dict) -> str:
    from datetime import UTC, datetime, timedelta

    from app.common.enums import IngestionDocType, IngestionStatus
    from app.modules.ingestion.models import IngestionItem

    days = int(args.get("days") or 7)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    query = select(IngestionItem).where(IngestionItem.created_at >= cutoff)
    if args.get("status"):
        query = query.where(IngestionItem.status == IngestionStatus(args["status"]))
    if args.get("doc_type"):
        query = query.where(IngestionItem.doc_type == IngestionDocType(args["doc_type"]))
    items = db.scalars(query.order_by(IngestionItem.created_at.desc()).limit(ROW_CAP)).all()

    rows = []
    for item in items:
        action = item.proposed_action or {}
        lineage = action.get("lineage") or {}
        rows.append(
            {
                "filename": item.original_filename,
                "doc_type": item.doc_type.value if item.doc_type else None,
                "status": item.status.value,
                "summary": (action.get("display") or {}).get("summary"),
                "confidence": action.get("confidence_score"),
                "posted_as": lineage.get("posted_type"),
                "posted_reference": lineage.get("reference"),
                "uploaded": str(item.created_at.date()),
            }
        )
    return _dump(rows)


_REGISTRY = {
    "list_projects": _tool_list_projects,
    "get_project_summary": _tool_get_project_summary,
    "get_boq_summary": _tool_get_boq_summary,
    "list_boq_items": _tool_list_boq_items,
    "get_budget_status": _tool_get_budget_status,
    "list_rfqs": _tool_list_rfqs,
    "get_rfq": _tool_get_rfq,
    "list_quotes": _tool_list_quotes,
    "list_purchase_orders": _tool_list_purchase_orders,
    "list_suppliers": _tool_list_suppliers,
    "get_site_diary": _tool_get_site_diary,
    "list_site_issues": _tool_list_site_issues,
    "list_expense_claims": _tool_list_expense_claims,
    "get_stock_levels": _tool_get_stock_levels,
    "get_ingestion_history": _tool_get_ingestion_history,
}


def run_tool(db: Session, name: str, args: dict) -> ToolOutput:
    handler = _REGISTRY.get(name)
    if handler is None:
        return ToolOutput(f"Unknown tool: {name}", is_error=True)
    try:
        return ToolOutput(handler(db, args or {}))
    except (ValueError, KeyError) as exc:
        return ToolOutput(f"Invalid tool input: {exc}", is_error=True)
    except Exception as exc:  # tool errors must never kill the stream
        return ToolOutput(f"Tool failed: {type(exc).__name__}: {exc}", is_error=True)
