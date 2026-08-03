import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.common.doc_numbers import next_doc_number
from app.common.enums import BoqItemType, ValuationStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.boq.models import BoqItem, BoqSection
from app.modules.projects.models import Project
from app.modules.projects.service import get_project, project_progress_pct
from app.modules.valuations.models import Valuation, ValuationLine
from app.modules.valuations.schemas import (
    MeasurementContext,
    MeasurementItem,
    MeasurementSection,
    MeasurementSet,
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
        if valuation.lines:
            raise ConflictError(
                "This valuation is measured — edit the measurement sheet instead"
            )
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


def _notify_valuation(db: Session, valuation: Valuation, event: str, actor_id) -> None:
    from app.common.enums import UserRole
    from app.modules.notifications import service as notifications

    project = valuation.project
    recipients = {project.project_manager_id} if project else set()
    notifications.notify(
        db,
        recipients,
        f"valuation_{event}",
        f"{valuation.doc_number} {event} — {project.name if project else ''}".strip(),
        f"Net certified {valuation.net_certified}",
        link=f"/projects/{valuation.project_id}/valuations",
        exclude=actor_id,
    )
    notifications.notify_roles(
        db,
        [UserRole.admin],
        f"valuation_{event}",
        f"{valuation.doc_number} {event} — {project.name if project else ''}".strip(),
        f"Net certified {valuation.net_certified}",
        link=f"/projects/{valuation.project_id}/valuations",
        exclude=actor_id,
    )


def issue_valuation(
    db: Session, valuation_id: uuid.UUID, issued_date: date | None, actor_id=None
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
    _notify_valuation(db, valuation, "issued", actor_id)
    return valuation


def pay_valuation(
    db: Session, valuation_id: uuid.UUID, paid_date: date | None, actor_id=None
) -> Valuation:
    valuation = get_valuation(db, valuation_id)
    _require_status(valuation, ValuationStatus.issued, "marked paid")
    valuation.status = ValuationStatus.paid
    valuation.paid_date = paid_date or date.today()
    _notify_valuation(db, valuation, "paid", actor_id)
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


# --- Measurement sheet --------------------------------------------------------


def set_measurement(db: Session, valuation_id: uuid.UUID, data: MeasurementSet) -> Valuation:
    """Replace the measurement sheet; gross becomes the sum of measured lines.

    Zero-quantity lines are dropped; sending an empty list reverts the
    valuation to single-figure mode (gross keeps its current value).
    """
    valuation = get_valuation(db, valuation_id)
    _require_status(valuation, ValuationStatus.draft, "measured")
    project = valuation.project

    valuation.lines.clear()
    db.flush()  # delete old rows before re-inserting the same (valuation, boq_item) keys
    seen: set[uuid.UUID] = set()
    total = ZERO
    for spec in data.lines:
        if spec.boq_item_id in seen:
            raise ValidationFailedError("Duplicate BOQ item on the measurement sheet")
        seen.add(spec.boq_item_id)
        if spec.qty_to_date == 0:
            continue
        item = db.get(BoqItem, spec.boq_item_id)
        if item is None or item.project_id != valuation.project_id:
            raise ValidationFailedError("BOQ item does not exist in this project")
        if item.item_type == BoqItemType.omission:
            raise ValidationFailedError("Omission items cannot be measured")
        amount = (spec.qty_to_date * item.rate).quantize(CENT)
        valuation.lines.append(
            ValuationLine(
                boq_item_id=item.id,
                item_code=item.item_code,
                description=item.description,
                unit=item.unit,
                rate=item.rate,
                boq_quantity=item.quantity,
                qty_to_date=spec.qty_to_date,
                amount=amount,
            )
        )
        total += amount

    if valuation.lines:
        _check_gross(db, project, total)
        valuation.gross_valuation = total
    previous = _previous_certified(db, valuation.project_id)
    valuation.previous_certified = previous
    valuation.retention_amount, valuation.net_certified = _compute(
        project, valuation.gross_valuation, previous
    )
    db.flush()
    return valuation


def measurement_context(db: Session, valuation_id: uuid.UUID) -> MeasurementContext:
    """The sheet the UI renders: every measurable BOQ line with its BOQ qty,
    the cumulative qty certified on the latest certificate, and the qty on
    this draft (if any)."""
    valuation = get_valuation(db, valuation_id)
    latest = _latest_certified(db, valuation.project_id)
    previous_qty = (
        {line.boq_item_id: line.qty_to_date for line in latest.lines} if latest else {}
    )
    current_qty = {line.boq_item_id: line.qty_to_date for line in valuation.lines}

    sections = db.scalars(
        select(BoqSection)
        .where(BoqSection.project_id == valuation.project_id)
        .order_by(BoqSection.sort_order)
    )
    out: list[MeasurementSection] = []
    for section in sections:
        items = [
            MeasurementItem(
                boq_item_id=item.id,
                item_code=item.item_code,
                description=item.description,
                unit=item.unit,
                boq_quantity=item.quantity,
                rate=item.rate,
                previous_qty=previous_qty.get(item.id, ZERO),
                current_qty=current_qty.get(item.id),
            )
            for item in section.items
            if item.item_type != BoqItemType.omission
        ]
        if items:
            out.append(MeasurementSection(code=section.code, title=section.title, items=items))
    return MeasurementContext(valuation_id=valuation.id, sections=out)
