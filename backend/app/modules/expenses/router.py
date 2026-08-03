import uuid

from fastapi import APIRouter, Depends

from app.common.enums import ExpenseStatus, UserRole
from app.common.pagination import PageParamsDep
from app.common.schemas import Page
from app.core.deps import CurrentUser, DbDep, require_roles
from app.modules.expenses import service
from app.modules.expenses.schemas import (
    ExpenseClaimCreate,
    ExpenseClaimRead,
    ExpenseClaimReject,
    ExpenseClaimUpdate,
)

router = APIRouter(tags=["expenses"])

expense_submit = require_roles(
    UserRole.site_manager, UserRole.project_manager, UserRole.procurement_officer
)
expense_approve = require_roles(UserRole.project_manager)


@router.get("/expenses", response_model=Page[ExpenseClaimRead])
def list_expense_claims(
    db: DbDep,
    params: PageParamsDep,
    user: CurrentUser,
    status: ExpenseStatus | None = None,
    project_id: uuid.UUID | None = None,
    mine: bool = False,
) -> Page[ExpenseClaimRead]:
    claims, total = service.list_claims(
        db,
        params.page,
        params.page_size,
        status,
        project_id,
        claimant_id=user.id if mine else None,
    )
    return Page(
        items=[service.claim_read(db, c) for c in claims],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/projects/{project_id}/expenses", response_model=ExpenseClaimRead, status_code=201)
def create_expense_claim(
    project_id: uuid.UUID,
    body: ExpenseClaimCreate,
    db: DbDep,
    user=Depends(expense_submit),
) -> ExpenseClaimRead:
    return service.claim_read(db, service.create_claim(db, project_id, body, user.id))


@router.get("/expenses/{claim_id}", response_model=ExpenseClaimRead)
def get_expense_claim(claim_id: uuid.UUID, db: DbDep) -> ExpenseClaimRead:
    return service.claim_read(db, service.get_claim(db, claim_id))


@router.patch("/expenses/{claim_id}", response_model=ExpenseClaimRead)
def update_expense_claim(
    claim_id: uuid.UUID,
    body: ExpenseClaimUpdate,
    db: DbDep,
    user=Depends(expense_submit),
) -> ExpenseClaimRead:
    return service.claim_read(db, service.update_claim(db, claim_id, body, user))


@router.post("/expenses/{claim_id}/cancel", response_model=ExpenseClaimRead)
def cancel_expense_claim(
    claim_id: uuid.UUID, db: DbDep, user=Depends(expense_submit)
) -> ExpenseClaimRead:
    return service.claim_read(db, service.cancel_claim(db, claim_id, user))


@router.post("/expenses/{claim_id}/approve", response_model=ExpenseClaimRead)
def approve_expense_claim(
    claim_id: uuid.UUID, db: DbDep, user=Depends(expense_approve)
) -> ExpenseClaimRead:
    return service.claim_read(db, service.approve_claim(db, claim_id, user))


@router.post("/expenses/{claim_id}/reject", response_model=ExpenseClaimRead)
def reject_expense_claim(
    claim_id: uuid.UUID,
    body: ExpenseClaimReject,
    db: DbDep,
    user=Depends(expense_approve),
) -> ExpenseClaimRead:
    return service.claim_read(db, service.reject_claim(db, claim_id, body.reason, user))
