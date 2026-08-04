import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.common.enums import BoqItemType, ProjectStatus, WorkStatus
from app.modules.boq.models import BoqItem
from app.modules.costs.models import CostEntry
from app.modules.dashboard.schemas import (
    BudgetAlert,
    CompanyOverview,
    DeadlineItem,
    FinancialTotals,
    FinancialTrend,
    OverdueDelivery,
    ProcurementPulse,
    ProjectHealth,
    TrendMonth,
)
from app.modules.projects.models import Phase, Project
from app.modules.projects.service import project_progress_pct
from app.modules.tasks.models import Task
from app.modules.users.models import User

ZERO = Decimal("0")
OPEN_STATUSES = [WorkStatus.not_started, WorkStatus.in_progress, WorkStatus.blocked]


def _budget_by_project(db: Session) -> dict[uuid.UUID, Decimal]:
    return dict(
        db.execute(
            select(BoqItem.project_id, func.sum(BoqItem.amount))
            .where(BoqItem.item_type != BoqItemType.omission)
            .group_by(BoqItem.project_id)
        ).all()
    )


def _actual_by_project(db: Session) -> dict[uuid.UUID, Decimal]:
    return dict(
        db.execute(
            select(CostEntry.project_id, func.sum(CostEntry.amount)).group_by(CostEntry.project_id)
        ).all()
    )


def _overdue_by_project(db: Session) -> dict[uuid.UUID, int]:
    return dict(
        db.execute(
            select(Task.project_id, func.count())
            .where(Task.planned_end < date.today(), Task.status.in_(OPEN_STATUSES))
            .group_by(Task.project_id)
        ).all()
    )


def company_overview(db: Session) -> CompanyOverview:
    projects = db.scalars(
        select(Project)
        .options(joinedload(Project.client))
        .where(
            Project.status.in_(
                [ProjectStatus.planning, ProjectStatus.active, ProjectStatus.on_hold]
            )
        )
        .order_by(Project.planned_end.nulls_last())
    ).all()

    budgets = _budget_by_project(db)
    actuals = _actual_by_project(db)
    overdue = _overdue_by_project(db)

    items: list[ProjectHealth] = []
    for p in projects:
        budget = budgets.get(p.id, ZERO)
        actual = actuals.get(p.id, ZERO)
        items.append(
            ProjectHealth(
                id=p.id,
                code=p.code,
                name=p.name,
                status=p.status,
                client_name=p.client.name if p.client else None,
                progress_pct=project_progress_pct(db, p.id),
                budget_total=budget,
                actual_total=actual,
                budget_used_pct=round(float(actual) / float(budget) * 100, 1) if budget else None,
                planned_end=p.planned_end,
                overdue_tasks=overdue.get(p.id, 0),
            )
        )

    total_projects = db.scalar(select(func.count()).select_from(Project)) or 0
    active = sum(1 for p in projects if p.status == ProjectStatus.active)
    contract_total = db.scalar(
        select(func.coalesce(func.sum(Project.contract_value), 0)).where(
            Project.status.in_(
                [ProjectStatus.planning, ProjectStatus.active, ProjectStatus.on_hold]
            )
        )
    )

    return CompanyOverview(
        active_projects=active,
        total_projects=total_projects,
        portfolio_contract_value=contract_total,
        portfolio_budget=sum((i.budget_total for i in items), ZERO),
        portfolio_actual=sum((i.actual_total for i in items), ZERO),
        overdue_tasks=sum(i.overdue_tasks for i in items),
        projects=items,
    )


def deadlines(db: Session, days: int = 30) -> list[DeadlineItem]:
    horizon = date.today() + timedelta(days=days)
    rows = db.execute(
        select(Task, Project.code, Project.name, Phase.name, User.full_name)
        .join(Project, Project.id == Task.project_id)
        .outerjoin(Phase, Phase.id == Task.phase_id)
        .outerjoin(User, User.id == Task.assignee_id)
        .where(
            Task.status.in_(OPEN_STATUSES),
            Task.planned_end.is_not(None),
            Task.planned_end <= horizon,
            Project.status == ProjectStatus.active,
        )
        .order_by(Task.planned_end)
    ).all()
    today = date.today()
    return [
        DeadlineItem(
            task_id=task.id,
            task_name=task.name,
            wbs_code=task.wbs_code,
            project_id=task.project_id,
            project_code=project_code,
            project_name=project_name,
            phase_name=phase_name,
            assignee_name=assignee_name,
            status=task.status,
            planned_end=task.planned_end,
            days_left=(task.planned_end - today).days,
            is_overdue=task.planned_end < today,
        )
        for task, project_code, project_name, phase_name, assignee_name in rows
    ]


def budget_alerts(db: Session, threshold_pct: float = 90.0) -> list[BudgetAlert]:
    alerts: list[BudgetAlert] = []

    budgets = _budget_by_project(db)
    actuals = _actual_by_project(db)
    projects = {
        p.id: p
        for p in db.scalars(
            select(Project).where(
                Project.status.in_(
                    [ProjectStatus.planning, ProjectStatus.active, ProjectStatus.on_hold]
                )
            )
        )
    }
    for pid, project in projects.items():
        budget = budgets.get(pid, ZERO)
        actual = actuals.get(pid, ZERO)
        if budget and float(actual) / float(budget) * 100 >= threshold_pct:
            alerts.append(
                BudgetAlert(
                    project_id=pid,
                    project_code=project.code,
                    project_name=project.name,
                    scope="project",
                    item_code=None,
                    description="Whole-project budget",
                    budget=budget,
                    actual=actual,
                    used_pct=round(float(actual) / float(budget) * 100, 1),
                )
            )

    item_rows = db.execute(
        select(
            BoqItem.id,
            BoqItem.project_id,
            BoqItem.item_code,
            BoqItem.description,
            BoqItem.amount,
            func.sum(CostEntry.amount),
        )
        .join(CostEntry, CostEntry.boq_item_id == BoqItem.id)
        .where(BoqItem.project_id.in_(projects.keys()))
        .group_by(BoqItem.id)
        .having(func.sum(CostEntry.amount) >= BoqItem.amount * threshold_pct / 100)
    ).all()
    for _item_id, pid, code, desc, budget, actual in item_rows:
        if not budget:
            continue
        project = projects[pid]
        alerts.append(
            BudgetAlert(
                project_id=pid,
                project_code=project.code,
                project_name=project.name,
                scope="boq_item",
                item_code=code,
                description=desc,
                budget=budget,
                actual=actual,
                used_pct=round(float(actual) / float(budget) * 100, 1),
            )
        )
    alerts.sort(key=lambda a: a.used_pct, reverse=True)
    return alerts


def financial_trend(
    db: Session, months: int = 6, project_id: uuid.UUID | None = None
) -> FinancialTrend:
    """Monthly cost vs revenue: cost from the ledger (entry_date), certified
    net from valuations (issued_date), receipts from paid_date."""
    from app.common.enums import ValuationStatus
    from app.modules.valuations.models import Valuation

    today = date.today()
    start_month = date(today.year, today.month, 1)
    keys: list[str] = []
    cursor = start_month
    for _ in range(months):
        keys.append(cursor.strftime("%Y-%m"))
        prev_last_day = cursor - timedelta(days=1)
        cursor = date(prev_last_day.year, prev_last_day.month, 1)
    keys.reverse()
    window_start = date(int(keys[0][:4]), int(keys[0][5:]), 1)

    cost_by_month: dict[str, Decimal] = dict.fromkeys(keys, Decimal("0"))
    cost_query = select(CostEntry).where(CostEntry.entry_date >= window_start)
    if project_id is not None:
        cost_query = cost_query.where(CostEntry.project_id == project_id)
    total_cost = Decimal("0")
    for entry in db.scalars(cost_query):
        total_cost += entry.amount
        key = entry.entry_date.strftime("%Y-%m")
        if key in cost_by_month:
            cost_by_month[key] += entry.amount

    certified_by_month: dict[str, Decimal] = dict.fromkeys(keys, Decimal("0"))
    paid_by_month: dict[str, Decimal] = dict.fromkeys(keys, Decimal("0"))
    val_query = select(Valuation).where(
        Valuation.status.in_((ValuationStatus.issued, ValuationStatus.paid))
    )
    if project_id is not None:
        val_query = val_query.where(Valuation.project_id == project_id)
    invoiced = Decimal("0")
    paid_total = Decimal("0")
    for valuation in db.scalars(val_query):
        invoiced += valuation.net_certified
        if valuation.issued_date is not None:
            key = valuation.issued_date.strftime("%Y-%m")
            if key in certified_by_month:
                certified_by_month[key] += valuation.net_certified
        if valuation.status == ValuationStatus.paid and valuation.paid_date is not None:
            paid_total += valuation.net_certified
            key = valuation.paid_date.strftime("%Y-%m")
            if key in paid_by_month:
                paid_by_month[key] += valuation.net_certified

    return FinancialTrend(
        months=[
            TrendMonth(
                month=key,
                cost=cost_by_month[key],
                certified_net=certified_by_month[key],
                paid=paid_by_month[key],
            )
            for key in keys
        ],
        totals=FinancialTotals(
            portfolio_invoiced=invoiced,
            portfolio_paid=paid_total,
            portfolio_outstanding=invoiced - paid_total,
            portfolio_cost=total_cost,
        ),
    )


def procurement_pulse(db: Session) -> ProcurementPulse:
    """Where procurement is losing time: unactioned requests, late deliveries,
    and stock that has fallen through its reorder level."""
    from app.modules.inventory.models import StockItem
    from app.modules.procurement.service import overdue_days, overdue_pos
    from app.modules.requisitions.service import open_requisition_stats

    open_count, oldest_days = open_requisition_stats(db)
    pos = overdue_pos(db)
    low_stock = db.scalar(
        select(func.count())
        .select_from(StockItem)
        .where(
            StockItem.is_active.is_(True),
            StockItem.qty_on_hand <= StockItem.reorder_level,
        )
    ) or 0

    return ProcurementPulse(
        open_requisitions=open_count,
        oldest_requisition_days=oldest_days,
        overdue_deliveries=len(pos),
        overdue_value=sum((po.total_amount for po in pos), ZERO),
        low_stock_items=low_stock,
        deliveries=[
            OverdueDelivery(
                po_id=po.id,
                doc_number=po.doc_number,
                supplier_name=po.supplier.name if po.supplier else None,
                project_id=po.project_id,
                project_name=po.project.name if po.project else None,
                expected_delivery=po.expected_delivery,
                days_overdue=overdue_days(po),
                total_amount=po.total_amount,
            )
            for po in pos
        ],
    )
