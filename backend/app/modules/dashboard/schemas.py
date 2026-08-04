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
    committed_total: Decimal = Decimal("0")
    budget_used_pct: float | None
    exposure_pct: float | None = None  # (actual + committed) / budget
    planned_end: date | None
    overdue_tasks: int


class CompanyOverview(BaseModel):
    active_projects: int
    total_projects: int
    portfolio_contract_value: Decimal
    portfolio_budget: Decimal
    portfolio_actual: Decimal
    portfolio_committed: Decimal = Decimal("0")
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


class OverdueDelivery(BaseModel):
    po_id: uuid.UUID
    doc_number: str
    supplier_name: str | None
    project_id: uuid.UUID
    project_name: str | None
    expected_delivery: date
    days_overdue: int
    total_amount: Decimal


class ProcurementPulse(BaseModel):
    """The procurement-delay dashboard: what is waiting and what is late."""

    open_requisitions: int
    oldest_requisition_days: int
    overdue_deliveries: int
    overdue_value: Decimal
    low_stock_items: int
    deliveries: list[OverdueDelivery]


class CashflowMonth(BaseModel):
    month: str  # "2026-09"
    inflow_receivable: Decimal  # issued valuations still unpaid
    inflow_forecast: Decimal  # work not yet certified, spread over the programme
    outflow_committed: Decimal  # issued POs, placed in their delivery month
    outflow_payroll: Decimal  # recent payroll run-rate, carried forward
    net: Decimal
    cumulative: Decimal


class CashflowForecast(BaseModel):
    """Forward view built only from commitments already in the system.

    Inflows are money the client owes or will owe for work left in the
    contract; outflows are orders already placed plus the payroll run-rate.
    """

    months: list[CashflowMonth]
    opening_receivables: Decimal  # invoiced but not yet paid, today
    total_inflow: Decimal
    total_outflow: Decimal
    closing_position: Decimal
    worst_month: str | None  # the month with the deepest negative net
