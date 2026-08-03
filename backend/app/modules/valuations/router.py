import uuid

from fastapi import APIRouter, Depends

from app.common.enums import UserRole
from app.common.pagination import PageParamsDep
from app.common.schemas import Page
from app.core.deps import DbDep, require_roles
from app.modules.valuations import service
from app.modules.valuations.schemas import (
    RevenueSummary,
    ValuationCreate,
    ValuationDetail,
    ValuationIssue,
    ValuationPay,
    ValuationRead,
    ValuationUpdate,
)

router = APIRouter(tags=["valuations"])

val_write = Depends(require_roles(UserRole.project_manager))
val_user = require_roles(UserRole.project_manager)


@router.get("/projects/{project_id}/valuations", response_model=Page[ValuationRead])
def list_valuations(
    project_id: uuid.UUID, db: DbDep, params: PageParamsDep
) -> Page[ValuationRead]:
    valuations, total = service.list_valuations(db, project_id, params.page, params.page_size)
    return Page(
        items=[ValuationRead.model_validate(v) for v in valuations],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post(
    "/projects/{project_id}/valuations", response_model=ValuationDetail, status_code=201
)
def create_valuation(
    project_id: uuid.UUID, body: ValuationCreate, db: DbDep, user=Depends(val_user)
) -> ValuationDetail:
    valuation = service.create_valuation(db, project_id, body, user.id)
    return service.valuation_detail(db, valuation.id)


@router.get("/projects/{project_id}/revenue-summary", response_model=RevenueSummary)
def get_revenue_summary(project_id: uuid.UUID, db: DbDep) -> RevenueSummary:
    return service.revenue_summary(db, project_id)


@router.get("/valuations/{valuation_id}", response_model=ValuationDetail)
def get_valuation(valuation_id: uuid.UUID, db: DbDep) -> ValuationDetail:
    return service.valuation_detail(db, valuation_id)


@router.patch(
    "/valuations/{valuation_id}", response_model=ValuationDetail, dependencies=[val_write]
)
def update_valuation(valuation_id: uuid.UUID, body: ValuationUpdate, db: DbDep) -> ValuationDetail:
    service.update_valuation(db, valuation_id, body)
    return service.valuation_detail(db, valuation_id)


@router.delete("/valuations/{valuation_id}", status_code=204, dependencies=[val_write])
def delete_valuation(valuation_id: uuid.UUID, db: DbDep) -> None:
    service.delete_valuation(db, valuation_id)


@router.post(
    "/valuations/{valuation_id}/issue", response_model=ValuationDetail, dependencies=[val_write]
)
def issue_valuation(
    valuation_id: uuid.UUID, body: ValuationIssue, db: DbDep
) -> ValuationDetail:
    service.issue_valuation(db, valuation_id, body.issued_date)
    return service.valuation_detail(db, valuation_id)


@router.post(
    "/valuations/{valuation_id}/pay", response_model=ValuationDetail, dependencies=[val_write]
)
def pay_valuation(valuation_id: uuid.UUID, body: ValuationPay, db: DbDep) -> ValuationDetail:
    service.pay_valuation(db, valuation_id, body.paid_date)
    return service.valuation_detail(db, valuation_id)


@router.post(
    "/valuations/{valuation_id}/cancel", response_model=ValuationDetail, dependencies=[val_write]
)
def cancel_valuation(valuation_id: uuid.UUID, db: DbDep) -> ValuationDetail:
    service.cancel_valuation(db, valuation_id)
    return service.valuation_detail(db, valuation_id)
