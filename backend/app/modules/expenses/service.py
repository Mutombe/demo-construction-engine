import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.doc_numbers import next_doc_number
from app.common.enums import CostSource, ExpenseStatus, UserRole
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationFailedError
from app.modules.boq.models import BoqItem
from app.modules.costs.models import CostEntry
from app.modules.expenses.models import ExpenseClaim
from app.modules.expenses.schemas import ExpenseClaimCreate, ExpenseClaimRead, ExpenseClaimUpdate
from app.modules.notifications import service as notifications
from app.modules.projects.models import Project
from app.modules.projects.service import get_project
from app.modules.users.models import User


def claim_read(db: Session, claim: ExpenseClaim) -> ExpenseClaimRead:
    read = ExpenseClaimRead.model_validate(claim)
    if claim.created_by:
        claimant = db.get(User, claim.created_by)
        read.claimant_name = claimant.full_name if claimant else None
    if claim.approved_by:
        approver = db.get(User, claim.approved_by)
        read.approver_name = approver.full_name if approver else None
    project = db.get(Project, claim.project_id)
    if project:
        read.project_name = project.name
        read.project_code = project.code
    return read


def list_claims(
    db: Session,
    page: int,
    page_size: int,
    status: ExpenseStatus | None = None,
    project_id: uuid.UUID | None = None,
    claimant_id: uuid.UUID | None = None,
) -> tuple[list[ExpenseClaim], int]:
    query = select(ExpenseClaim)
    if status is not None:
        query = query.where(ExpenseClaim.status == status)
    if project_id is not None:
        query = query.where(ExpenseClaim.project_id == project_id)
    if claimant_id is not None:
        query = query.where(ExpenseClaim.created_by == claimant_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    claims = list(
        db.scalars(
            query.order_by(ExpenseClaim.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return claims, total


def get_claim(db: Session, claim_id: uuid.UUID) -> ExpenseClaim:
    claim = db.get(ExpenseClaim, claim_id)
    if claim is None:
        raise NotFoundError("Expense claim not found")
    return claim


def _validate_boq_item(db: Session, project_id: uuid.UUID, boq_item_id: uuid.UUID) -> None:
    item = db.get(BoqItem, boq_item_id)
    if item is None or item.project_id != project_id:
        raise ValidationFailedError("BOQ item does not exist in this project")


def create_claim(
    db: Session, project_id: uuid.UUID, data: ExpenseClaimCreate, created_by: uuid.UUID
) -> ExpenseClaim:
    get_project(db, project_id)
    if data.boq_item_id is not None:
        _validate_boq_item(db, project_id, data.boq_item_id)
    claim = ExpenseClaim(
        **data.model_dump(),
        project_id=project_id,
        doc_number=next_doc_number(db, ExpenseClaim, "EXP"),
        created_by=created_by,
    )
    db.add(claim)
    db.flush()
    notifications.notify_roles(
        db,
        [UserRole.admin, UserRole.project_manager],
        "expense_submitted",
        f"Expense {claim.doc_number} awaiting approval",
        f"{claim.description} — {claim.amount}",
        link="/expenses",
        exclude=created_by,
    )
    return claim


def _require_pending(claim: ExpenseClaim) -> None:
    if claim.status != ExpenseStatus.pending:
        raise ConflictError("Only pending claims can be modified or decided")


def _require_claimant(claim: ExpenseClaim, user: User) -> None:
    if user.role != UserRole.admin and claim.created_by != user.id:
        raise ForbiddenError("Only the claimant can modify this claim")


def update_claim(
    db: Session, claim_id: uuid.UUID, data: ExpenseClaimUpdate, user: User
) -> ExpenseClaim:
    claim = get_claim(db, claim_id)
    _require_pending(claim)
    _require_claimant(claim, user)
    updates = data.model_dump(exclude_unset=True)
    if updates.get("boq_item_id") is not None:
        _validate_boq_item(db, claim.project_id, updates["boq_item_id"])
    for field, value in updates.items():
        setattr(claim, field, value)
    return claim


def cancel_claim(db: Session, claim_id: uuid.UUID, user: User) -> ExpenseClaim:
    claim = get_claim(db, claim_id)
    _require_pending(claim)
    _require_claimant(claim, user)
    claim.status = ExpenseStatus.cancelled
    claim.decided_at = datetime.now(UTC)
    return claim


def approve_claim(db: Session, claim_id: uuid.UUID, approver: User) -> ExpenseClaim:
    claim = get_claim(db, claim_id)
    _require_pending(claim)
    if claim.created_by == approver.id:
        raise ConflictError("You cannot approve your own expense claim")
    entry = CostEntry(
        project_id=claim.project_id,
        boq_item_id=claim.boq_item_id,
        entry_date=claim.expense_date,
        description=f"Expense {claim.doc_number}: {claim.description}",
        amount=claim.amount,
        source=CostSource.expense,
        reference=claim.doc_number,
        created_by=approver.id,
    )
    db.add(entry)
    db.flush()
    claim.status = ExpenseStatus.approved
    claim.approved_by = approver.id
    claim.decided_at = datetime.now(UTC)
    claim.cost_entry_id = entry.id
    notifications.notify(
        db,
        [claim.created_by],
        "expense_approved",
        f"Expense {claim.doc_number} approved",
        f"{claim.description} — posted to the project ledger",
        link="/expenses",
        exclude=approver.id,
    )
    return claim


def reject_claim(db: Session, claim_id: uuid.UUID, reason: str, approver: User) -> ExpenseClaim:
    claim = get_claim(db, claim_id)
    _require_pending(claim)
    if claim.created_by == approver.id:
        raise ConflictError("You cannot decide your own expense claim")
    claim.status = ExpenseStatus.rejected
    claim.approved_by = approver.id
    claim.decided_at = datetime.now(UTC)
    claim.rejection_reason = reason
    notifications.notify(
        db,
        [claim.created_by],
        "expense_rejected",
        f"Expense {claim.doc_number} rejected",
        reason,
        link="/expenses",
        exclude=approver.id,
    )
    return claim
