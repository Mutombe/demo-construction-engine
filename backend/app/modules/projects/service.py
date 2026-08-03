import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.common.enums import BoqItemType, ProjectStatus, WorkStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.boq.models import BoqItem
from app.modules.clients.models import Client
from app.modules.costs.models import CostEntry
from app.modules.projects.models import Phase, Project
from app.modules.projects.schemas import (
    PhaseCreate,
    PhaseUpdate,
    ProjectCreate,
    ProjectSummary,
    ProjectUpdate,
)
from app.modules.tasks.models import Task


def generate_project_code(db: Session) -> str:
    year = date.today().year
    prefix = f"PRJ-{year}-"
    last = db.scalar(
        select(Project.code)
        .where(Project.code.like(f"{prefix}%"))
        .order_by(Project.code.desc())
        .limit(1)
    )
    seq = int(last.removeprefix(prefix)) + 1 if last else 1
    return f"{prefix}{seq:03d}"


def list_projects(
    db: Session,
    page: int,
    page_size: int,
    status: ProjectStatus | None = None,
    client_id: uuid.UUID | None = None,
    project_manager_id: uuid.UUID | None = None,
    search: str | None = None,
) -> tuple[list[Project], int]:
    query = select(Project).options(joinedload(Project.client), joinedload(Project.project_manager))
    if status is not None:
        query = query.where(Project.status == status)
    if client_id is not None:
        query = query.where(Project.client_id == client_id)
    if project_manager_id is not None:
        query = query.where(Project.project_manager_id == project_manager_id)
    if search:
        query = query.where(Project.name.ilike(f"%{search}%") | Project.code.ilike(f"%{search}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    projects = list(
        db.scalars(
            query.order_by(Project.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return projects, total


def get_project(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(
        Project,
        project_id,
        options=[joinedload(Project.client), joinedload(Project.project_manager)],
    )
    if project is None:
        raise NotFoundError("Project not found")
    return project


def create_project(db: Session, data: ProjectCreate, created_by: uuid.UUID) -> Project:
    if db.get(Client, data.client_id) is None:
        raise ValidationFailedError("Client does not exist")
    _validate_dates(data.planned_start, data.planned_end)
    project = Project(**data.model_dump(), code=generate_project_code(db), created_by=created_by)
    db.add(project)
    db.flush()
    return get_project(db, project.id)


def update_project(db: Session, project_id: uuid.UUID, data: ProjectUpdate) -> Project:
    project = get_project(db, project_id)
    updates = data.model_dump(exclude_unset=True)
    if "client_id" in updates and db.get(Client, updates["client_id"]) is None:
        raise ValidationFailedError("Client does not exist")
    planned_start = updates.get("planned_start", project.planned_start)
    planned_end = updates.get("planned_end", project.planned_end)
    _validate_dates(planned_start, planned_end)
    for field, value in updates.items():
        setattr(project, field, value)
    return project


def delete_project(db: Session, project_id: uuid.UUID) -> None:
    project = get_project(db, project_id)
    task_count = (
        db.scalar(select(func.count()).select_from(Task).where(Task.project_id == project_id)) or 0
    )
    boq_count = (
        db.scalar(select(func.count()).select_from(BoqItem).where(BoqItem.project_id == project_id))
        or 0
    )
    if task_count > 0 or boq_count > 0:
        raise ConflictError(
            "Project has tasks or BOQ data. Cancel it instead of deleting, "
            "or remove its contents first."
        )
    db.delete(project)


def _validate_dates(start: date | None, end: date | None) -> None:
    if start and end and end < start:
        raise ValidationFailedError("planned_end cannot be before planned_start")


# --- Progress rollup -------------------------------------------------------


def project_progress_pct(db: Session, project_id: uuid.UUID) -> float:
    """Weighted rollup: sum(progress * weight) / sum(weight).

    Weight precedence: explicit task.weight, else planned duration in days,
    else 1. Cancelled tasks are excluded. Never an unweighted average.
    """
    rows = db.execute(
        select(
            Task.progress_pct,
            Task.weight,
            Task.planned_start,
            Task.planned_end,
        ).where(Task.project_id == project_id, Task.status != WorkStatus.cancelled)
    ).all()
    if not rows:
        return 0.0
    total_weight = 0.0
    weighted = 0.0
    for progress, weight, start, end in rows:
        if weight is not None:
            w = float(weight)
        elif start and end:
            w = max((end - start).days + 1, 1)
        else:
            w = 1.0
        total_weight += w
        weighted += float(progress) * w
    return round(weighted / total_weight, 1) if total_weight else 0.0


def project_summary(db: Session, project_id: uuid.UUID) -> ProjectSummary:
    project = get_project(db, project_id)

    budget_total = db.scalar(
        select(func.coalesce(func.sum(BoqItem.amount), 0)).where(
            BoqItem.project_id == project_id, BoqItem.item_type != BoqItemType.omission
        )
    )
    actual_total = db.scalar(
        select(func.coalesce(func.sum(CostEntry.amount), 0)).where(
            CostEntry.project_id == project_id
        )
    )

    status_counts = dict(
        db.execute(
            select(Task.status, func.count())
            .where(Task.project_id == project_id)
            .group_by(Task.status)
        ).all()
    )
    overdue = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.project_id == project_id,
                Task.planned_end < date.today(),
                Task.status.notin_([WorkStatus.done, WorkStatus.cancelled]),
            )
        )
        or 0
    )

    variance_pct = (
        round((float(actual_total) - float(budget_total)) / float(budget_total) * 100, 1)
        if budget_total
        else None
    )
    days_remaining = (project.planned_end - date.today()).days if project.planned_end else None

    return ProjectSummary(
        id=project.id,
        code=project.code,
        name=project.name,
        status=project.status,
        progress_pct=project_progress_pct(db, project_id),
        budget_total=budget_total,
        actual_total=actual_total,
        budget_variance_pct=variance_pct,
        task_counts={status.value: count for status, count in status_counts.items()},
        overdue_tasks=overdue,
        days_remaining=days_remaining,
    )


# --- Phases ----------------------------------------------------------------


def list_phases(db: Session, project_id: uuid.UUID) -> list[Phase]:
    get_project(db, project_id)
    return list(
        db.scalars(select(Phase).where(Phase.project_id == project_id).order_by(Phase.sequence))
    )


def get_phase(db: Session, phase_id: uuid.UUID) -> Phase:
    phase = db.get(Phase, phase_id)
    if phase is None:
        raise NotFoundError("Phase not found")
    return phase


def create_phase(
    db: Session, project_id: uuid.UUID, data: PhaseCreate, created_by: uuid.UUID
) -> Phase:
    get_project(db, project_id)
    existing = db.scalar(
        select(Phase).where(Phase.project_id == project_id, Phase.sequence == data.sequence)
    )
    if existing:
        raise ConflictError(f"A phase with sequence {data.sequence} already exists")
    phase = Phase(**data.model_dump(), project_id=project_id, created_by=created_by)
    db.add(phase)
    db.flush()
    return phase


def update_phase(db: Session, phase_id: uuid.UUID, data: PhaseUpdate) -> Phase:
    phase = get_phase(db, phase_id)
    updates = data.model_dump(exclude_unset=True)
    if "sequence" in updates and updates["sequence"] != phase.sequence:
        clash = db.scalar(
            select(Phase).where(
                Phase.project_id == phase.project_id,
                Phase.sequence == updates["sequence"],
                Phase.id != phase.id,
            )
        )
        if clash:
            raise ConflictError(f"A phase with sequence {updates['sequence']} already exists")
    for field, value in updates.items():
        setattr(phase, field, value)
    return phase


def delete_phase(db: Session, phase_id: uuid.UUID) -> None:
    db.delete(get_phase(db, phase_id))


def reorder_phases(db: Session, project_id: uuid.UUID, phase_ids: list[uuid.UUID]) -> list[Phase]:
    phases = list_phases(db, project_id)
    by_id = {p.id: p for p in phases}
    if set(phase_ids) != set(by_id.keys()):
        raise ValidationFailedError("phase_ids must contain exactly the project's phases")
    # Two-pass update to avoid transient unique-constraint collisions
    for i, pid in enumerate(phase_ids):
        by_id[pid].sequence = -(i + 1)
    db.flush()
    for i, pid in enumerate(phase_ids):
        by_id[pid].sequence = i + 1
    db.flush()
    return list_phases(db, project_id)
