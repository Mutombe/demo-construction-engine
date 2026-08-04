import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, DbDep
from app.modules.dashboard import service
from app.modules.dashboard.schemas import (
    BudgetAlert,
    CashflowForecast,
    CompanyOverview,
    DeadlineItem,
    FinancialTrend,
    NavCounts,
    ProcurementPulse,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=CompanyOverview)
def overview(db: DbDep) -> CompanyOverview:
    return service.company_overview(db)


@router.get("/deadlines", response_model=list[DeadlineItem])
def deadlines(db: DbDep, days: Annotated[int, Query(ge=1, le=365)] = 30) -> list[DeadlineItem]:
    return service.deadlines(db, days)


@router.get("/financial-trend", response_model=FinancialTrend)
def financial_trend(
    db: DbDep,
    months: Annotated[int, Query(ge=2, le=24)] = 6,
    project_id: uuid.UUID | None = None,
) -> FinancialTrend:
    return service.financial_trend(db, months, project_id)


@router.get("/nav-counts", response_model=NavCounts)
def nav_counts(db: DbDep, user: CurrentUser) -> NavCounts:
    """Sidebar badges: work waiting for the signed-in user, per destination."""
    return service.nav_counts(db, user)


@router.get("/procurement-pulse", response_model=ProcurementPulse)
def procurement_pulse(db: DbDep) -> ProcurementPulse:
    """Open requisitions, overdue deliveries and low stock in one call.

    Reading it also fires the (deduped) overdue-delivery notifications, so the
    alert lands without needing a scheduler in this deployment.
    """
    from app.modules.procurement.service import notify_overdue_deliveries

    pulse = service.procurement_pulse(db)
    notify_overdue_deliveries(db)
    return pulse


@router.get("/cashflow-forecast", response_model=CashflowForecast)
def cashflow_forecast(
    db: DbDep,
    months: Annotated[int, Query(ge=2, le=24)] = 6,
    project_id: uuid.UUID | None = None,
) -> CashflowForecast:
    return service.cashflow_forecast(db, months, project_id)


@router.get("/budget-alerts", response_model=list[BudgetAlert])
def budget_alerts(
    db: DbDep, threshold_pct: Annotated[float, Query(ge=1, le=200)] = 90.0
) -> list[BudgetAlert]:
    return service.budget_alerts(db, threshold_pct)
