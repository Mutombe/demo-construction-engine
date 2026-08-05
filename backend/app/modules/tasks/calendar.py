"""Everything with a date on it, in one window.

A tasks-only calendar answers half the question. What actually causes a
bottleneck on a construction job is that a delivery, a valuation cut-off and
three task deadlines all land in the same week — so deliveries, valuations and
material requests are on here alongside the programme.
"""

import uuid
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common.enums import PoStatus, RequisitionStatus, ValuationStatus, WorkStatus
from app.modules.procurement.models import PurchaseOrder
from app.modules.projects.models import Project
from app.modules.requisitions.models import Requisition
from app.modules.tasks.models import Task
from app.modules.valuations.models import Valuation

OPEN_STATUSES = (WorkStatus.not_started, WorkStatus.in_progress, WorkStatus.blocked)


def calendar(
    db: Session,
    start: date,
    end: date,
    project_id: uuid.UUID | None = None,
) -> dict:
    events: list[dict] = []
    events += _task_events(db, start, end, project_id)
    events += _delivery_events(db, start, end, project_id)
    events += _valuation_events(db, start, end, project_id)
    events += _requisition_events(db, start, end, project_id)
    events.sort(key=lambda e: (e["day"], e["kind"], e["title"]))
    return {"start": start, "end": end, "events": events}


def _in_window(column, start: date, end: date):
    return (column >= start) & (column <= end)


def _task_events(db, start, end, project_id) -> list[dict]:
    stmt = (
        select(Task, Project.code)
        .join(Project, Project.id == Task.project_id)
        .where(
            Task.status.in_(OPEN_STATUSES),
            or_(
                _in_window(Task.planned_start, start, end),
                _in_window(Task.planned_end, start, end),
            ),
        )
    )
    if project_id is not None:
        stmt = stmt.where(Task.project_id == project_id)

    out: list[dict] = []
    for task, code in db.execute(stmt).all():
        # A milestone is a single point, not a bar with two ends.
        if task.is_milestone and task.planned_end and start <= task.planned_end <= end:
            out.append(_event("milestone", task.planned_end, task.name, task, code))
            continue
        if task.planned_start and start <= task.planned_start <= end:
            out.append(_event("task_start", task.planned_start, f"Start {task.name}", task, code))
        if task.planned_end and start <= task.planned_end <= end:
            out.append(_event("task_end", task.planned_end, f"Finish {task.name}", task, code))
    return out


def _event(kind, day, title, task, code) -> dict:
    return {
        "kind": kind,
        "day": day,
        "title": title,
        "project_id": task.project_id,
        "project_code": code,
        "link": f"/projects/{task.project_id}/tasks",
        "priority": task.priority.value,
        "overdue": bool(day < date.today() and kind != "task_start"),
    }


def _delivery_events(db, start, end, project_id) -> list[dict]:
    """Only issued orders: a draft has not been promised to anyone yet."""
    stmt = (
        select(PurchaseOrder, Project.code)
        .join(Project, Project.id == PurchaseOrder.project_id)
        .where(
            PurchaseOrder.status == PoStatus.issued,
            _in_window(PurchaseOrder.expected_delivery, start, end),
        )
    )
    if project_id is not None:
        stmt = stmt.where(PurchaseOrder.project_id == project_id)
    return [
        {
            "kind": "delivery",
            "day": po.expected_delivery,
            "title": f"{po.doc_number} due from {po.supplier.name}",
            "project_id": po.project_id,
            "project_code": code,
            "link": f"/procurement/purchase-orders/{po.id}",
            "priority": None,
            "overdue": po.expected_delivery < date.today(),
        }
        for po, code in db.execute(stmt).all()
    ]


def _valuation_events(db, start, end, project_id) -> list[dict]:
    stmt = (
        select(Valuation, Project.code)
        .join(Project, Project.id == Valuation.project_id)
        .where(
            Valuation.status.in_((ValuationStatus.draft, ValuationStatus.issued)),
            _in_window(Valuation.period_end, start, end),
        )
    )
    if project_id is not None:
        stmt = stmt.where(Valuation.project_id == project_id)
    return [
        {
            "kind": "valuation",
            "day": v.period_end,
            "title": f"{v.doc_number} period ends",
            "project_id": v.project_id,
            "project_code": code,
            "link": f"/valuations/{v.id}",
            "priority": None,
            "overdue": False,
        }
        for v, code in db.execute(stmt).all()
    ]


def _requisition_events(db, start, end, project_id) -> list[dict]:
    stmt = (
        select(Requisition, Project.code)
        .join(Project, Project.id == Requisition.project_id)
        .where(
            # Actioned ones have become an RFQ or PO, which carries its own
            # delivery date; only still-open requests are a site deadline.
            Requisition.status == RequisitionStatus.open,
            _in_window(Requisition.needed_by, start, end),
        )
    )
    if project_id is not None:
        stmt = stmt.where(Requisition.project_id == project_id)
    return [
        {
            "kind": "requisition",
            "day": r.needed_by,
            "title": f"{r.doc_number} needed on site",
            "project_id": r.project_id,
            "project_code": code,
            "link": f"/procurement/requisitions/{r.id}",
            "priority": None,
            "overdue": r.needed_by < date.today(),
        }
        for r, code in db.execute(stmt).all()
    ]
