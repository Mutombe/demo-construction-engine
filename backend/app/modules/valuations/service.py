import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.common.doc_numbers import next_doc_number
from app.common.enums import ValuationStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.projects.models import Project
from app.modules.projects.service import get_project, project_progress_pct
from app.modules.valuations.models import Valuation
from app.modules.valuations.schemas import (
    RevenueSummary,
    ValuationCreate,
    ValuationDetail,
    ValuationUpdate,
)

ZERO = Decimal("0")
CENT = Decimal("0.01")

CERTIFIED = (ValuationStatus.issued, ValuationStatus.paid)


def _compute(project: Project, gross: Decimal, previous: Decimal) -> tuple[Decimal, Decimal]:
    retention = (
        (gross * project.retention_pct / 100).quantize(CENT)
        if project.retention_pct
        else ZERO
    )
    net = (gross - retention - previous).quantize(CENT)
    return retention, net


def _previous_certified(db: Session, project_id: uuid.UUID) -> Decimal:
    return db.scalar(
        select(func.coalesce(func.sum(Valuation.net_certified), 0)).where(
            Valuation.project_id == project_id, Valuation.status.in_(CERTIFIED)
        )
    ) or ZERO


def _latest_certified(db: Session, project_id: uuid.UUID) -> Valuation | None:
    return db.scalar(
        select(Valuation)
        .where(Valuation.project_id == project_id, Valuation.status.in_(CERTIFIED))
        .order_by(Valuation.valuation_number.desc())
        .limit(1)
    )


def _check_gross(db: Session, project: Project, gross: Decimal) -> None:
    latest = _latest_certified(db, project.id)
    if latest and gross < latest.gross_valuation:
        raise ValidationFailedError(
            f"Gross valuation cannot be below the last certified gross "
            f"({latest.gross_valuation})"
        )
    if project.contract_value and gross > project.contract_value:
        raise ValidationFailedError(
            "Gross valuation exceeds the contract value; capture variations by "
            "updating the contract value first"
        )


def list_valuations(
    db: Session, project_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[Valuation], int]:
    get_project(db, project_id)
    query = select(Valuation).where(Valuation.project_id == project_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    valuations = list(
        db.scalars(
            query.order_by(Valuation.valuation_number.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return valuations, total


def get_valuation(db: Session, valuation_id: uuid.UUID) -> Valuation:
    valuation = db.get(Valuation, valuation_id, options=[joinedload(Valuation.project)])
    if valuation is None:
        raise NotFoundError("Valuation not found")
    return valuation


def valuation_detail(db: Session, valuation_id: uuid.UUID) -> ValuationDetail:
    valuation = get_valuation(db, valuation_id)
    detail = ValuationDetail.model_validate(valuation)
    if valuation.project:
        detail.project_name = valuation.project.name
        detail.project_code = valuation.project.code
    return detail


def create_valuation(
    db: Session, project_id: uuid.UUID, data: ValuationCreate, created_by: uuid.UUID
) -> Valuation:
    project = get_project(db, project_id)
    existing_draft = db.scalar(
        select(Valuation).where(
            Valuation.project_id == project_id, Valuation.status == ValuationStatus.draft
        )
    )
    if existing_draft:
        raise ConflictError(
            f"A draft valuation ({existing_draft.doc_number}) already exists — "
            "issue or delete it first"
        )
    _check_gross(db, project, data.gross_valuation)

    # No FOR UPDATE (not allowed on aggregates); the unique constraint on
    # (project_id, valuation_number) is the concurrency backstop.
    max_number = db.scalar(
        select(func.max(Valuation.valuation_number)).where(
            Valuation.project_id == project_id
        )
    ) or 0
    previous = _previous_certified(db, project_id)
    retention, net = _compute(project, data.gross_valuation, previous)
    valuation = Valuation(
        project_id=project_id,
        doc_number=next_doc_number(db, Valuation, "INV"),
        valuation_number=max_number + 1,
        period_end=data.period_end,
        gross_valuation=data.gross_valuation,
        retention_amount=retention,
        previous_certified=previous,
        net_certified=net,
        notes=data.notes,
        created_by=created_by,
    )
    db.add(valuation)
    db.flush()
    return valuation


def _require_status(valuation: Valuation, status: ValuationStatus, action: str) -> None:
    if valuation.status != status:
        raise ConflictError(f"Only {status.value} valuations can be {action}")


def update_valuation(
    db: Session, valuation_id: uuid.UUID, data: ValuationUpdate
) -> Valuation:
    valuation = get_valuation(db, valuation_id)
    _require_status(valuation, ValuationStatus.draft, "edited")
    updates = data.model_dump(exclude_unset=True)
    if "gross_valuation" in updates:
        _check_gross(db, valuation.project, updates["gross_valuation"])
        valuation.gross_valuation = updates.pop("gross_valuation")
    for field, value in updates.items():
        setattr(valuation, field, value)
    previous = _previous_certified(db, valuation.project_id)
    valuation.previous_certified = previous
    valuation.retention_amount, valuation.net_certified = _compute(
        valuation.project, valuation.gross_valuation, previous
    )
    return valuation


def delete_valuation(db: Session, valuation_id: uuid.UUID) -> None:
    valuation = get_valuation(db, valuation_id)
    _require_status(valuation, ValuationStatus.draft, "deleted")
    db.delete(valuation)


def issue_valuation(
    db: Session, valuation_id: uuid.UUID, issued_date: date | None
) -> Valuation:
    valuation = get_valuation(db, valuation_id)
    _require_status(valuation, ValuationStatus.draft, "issued")
    _check_gross(db, valuation.project, valuation.gross_valuation)
    # Recompute defensively at issue time
    previous = _previous_certified(db, valuation.project_id)
    valuation.previous_certified = previous
    valuation.retention_amount, valuation.net_certified = _compute(
        valuation.project, valuation.gross_valuation, previous
    )
    valuation.status = ValuationStatus.issued
    valuation.issued_date = issued_date or date.today()
    return valuation


def pay_valuation(db: Session, valuation_id: uuid.UUID, paid_date: date | None) -> Valuation:
    valuation = get_valuation(db, valuation_id)
    _require_status(valuation, ValuationStatus.issued, "marked paid")
    valuation.status = ValuationStatus.paid
    valuation.paid_date = paid_date or date.today()
    return valuation


def cancel_valuation(db: Session, valuation_id: uuid.UUID) -> Valuation:
    valuation = get_valuation(db, valuation_id)
    if valuation.status not in (ValuationStatus.draft, ValuationStatus.issued):
        raise ConflictError("Paid or cancelled valuations cannot be cancelled")
    latest_active = db.scalar(
        select(func.max(Valuation.valuation_number)).where(
            Valuation.project_id == valuation.project_id,
            Valuation.status != ValuationStatus.cancelled,
        )
    )
    if valuation.valuation_number != latest_active:
        raise ConflictError(
            "Only the latest valuation can be cancelled — later certificates "
            "depend on this one"
        )
    valuation.status = ValuationStatus.cancelled
    return valuation


def revenue_summary(db: Session, project_id: uuid.UUID) -> RevenueSummary:
    project = get_project(db, project_id)
    latest = _latest_certified(db, project_id)
    invoiced = _previous_certified(db, project_id)
    paid = db.scalar(
        select(func.coalesce(func.sum(Valuation.net_certified), 0)).where(
            Valuation.project_id == project_id, Valuation.status == ValuationStatus.paid
        )
    ) or ZERO
    count = db.scalar(
        select(func.count()).select_from(Valuation).where(Valuation.project_id == project_id)
    ) or 0

    suggested = None
    if project.contract_value:
        progress = project_progress_pct(db, project_id)
        suggested = (project.contract_value * Decimal(str(progress)) / 100).quantize(CENT)

    return RevenueSummary(
        project_id=project_id,
        contract_value=project.contract_value,
        retention_pct=project.retention_pct,
        certified_gross=latest.gross_valuation if latest else ZERO,
        retention_held=latest.retention_amount if latest else ZERO,
        invoiced_to_date=invoiced,
        paid_to_date=paid,
        outstanding=(invoiced - paid).quantize(CENT),
        suggested_gross=suggested,
        valuation_count=count,
    )
