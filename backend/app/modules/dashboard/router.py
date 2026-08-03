from typing import Annotated

from fastapi import APIRouter, Query

from app.core.deps import DbDep
from app.modules.dashboard import service
from app.modules.dashboard.schemas import BudgetAlert, CompanyOverview, DeadlineItem

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=CompanyOverview)
def overview(db: DbDep) -> CompanyOverview:
    return service.company_overview(db)


@router.get("/deadlines", response_model=list[DeadlineItem])
def deadlines(db: DbDep, days: Annotated[int, Query(ge=1, le=365)] = 30) -> list[DeadlineItem]:
    return service.deadlines(db, days)


@router.get("/budget-alerts", response_model=list[BudgetAlert])
def budget_alerts(
    db: DbDep, threshold_pct: Annotated[float, Query(ge=1, le=200)] = 90.0
) -> list[BudgetAlert]:
    return service.budget_alerts(db, threshold_pct)
