import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.common.enums import ProjectStatus, WorkStatus


class ProjectHealth(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    status: ProjectStatus
    client_name: str | None
    progress_pct: float
    budget_total: Decimal
    actual_total: Decimal
    budget_used_pct: float | None
    planned_end: date | None
    overdue_tasks: int


class CompanyOverview(BaseModel):
    active_projects: int
    total_projects: int
    portfolio_contract_value: Decimal
    portfolio_budget: Decimal
    portfolio_actual: Decimal
    overdue_tasks: int
    projects: list[ProjectHealth]


class DeadlineItem(BaseModel):
    task_id: uuid.UUID
    task_name: str
    wbs_code: str | None
    project_id: uuid.UUID
    project_code: str
    project_name: str
    phase_name: str | None
    assignee_name: str | None
    status: WorkStatus
    planned_end: date
    days_left: int
    is_overdue: bool


class BudgetAlert(BaseModel):
    project_id: uuid.UUID
    project_code: str
    project_name: str
    scope: str  # "project" or "boq_item"
    item_code: str | None
    description: str
    budget: Decimal
    actual: Decimal
    used_pct: float


class TrendMonth(BaseModel):
    month: str  # "2026-03"
    cost: Decimal
    certified_net: Decimal
    paid: Decimal


class FinancialTotals(BaseModel):
    portfolio_invoiced: Decimal
    portfolio_paid: Decimal
    portfolio_outstanding: Decimal
    portfolio_cost: Decimal


class FinancialTrend(BaseModel):
    months: list[TrendMonth]
    totals: FinancialTotals
