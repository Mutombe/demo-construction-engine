import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.common.enums import WorkStatus
from app.core.exceptions import (
    ConflictError,
    DependencyCycleError,
    NotFoundError,
    ValidationFailedError,
)
from app.modules.projects.models import Phase
from app.modules.projects.service import get_project
from app.modules.tasks import cpm
from app.modules.tasks.models import Task, TaskDependency
from app.modules.tasks.schemas import (
    DependencyCreate,
    DependencyRead,
    GanttPayload,
    GanttPhase,
    GanttTask,
    TaskCreate,
    TaskUpdate,
)
from app.modules.users.models import User
from app.modules.admin import trash


def list_tasks(
    db: Session,
    project_id: uuid.UUID,
    phase_id: uuid.UUID | None = None,
    status: WorkStatus | None = None,
    assignee_id: uuid.UUID | None = None,
) -> list[Task]:
    get_project(db, project_id)
    query = (
        select(Task)
        .options(joinedload(Task.assignee), joinedload(Task.phase))
        .where(Task.project_id == project_id)
    )
    if phase_id is not None:
        query = query.where(Task.phase_id == phase_id)
    if status is not None:
        query = query.where(Task.status == status)
    if assignee_id is not None:
        query = query.where(Task.assignee_id == assignee_id)
    return list(db.scalars(query.order_by(Task.sort_order, Task.created_at)))


def list_my_tasks(db: Session, user_id: uuid.UUID) -> list[Task]:
    return list(
        db.scalars(
            select(Task)
            .options(joinedload(Task.assignee), joinedload(Task.phase))
            .where(
                Task.assignee_id == user_id,
                Task.status.notin_([WorkStatus.done, WorkStatus.cancelled]),
            )
            .order_by(Task.planned_end.nulls_last())
        )
    )


def get_task(db: Session, task_id: uuid.UUID) -> Task:
    task = db.get(Task, task_id, options=[joinedload(Task.assignee), joinedload(Task.phase)])
    if task is None:
        raise NotFoundError("Task not found")
    return task


def predecessor_map(db: Session, project_id: uuid.UUID) -> dict[uuid.UUID, list[uuid.UUID]]:
    rows = db.execute(
        select(TaskDependency.successor_id, TaskDependency.predecessor_id)
        .join(Task, Task.id == TaskDependency.successor_id)
        .where(Task.project_id == project_id)
    ).all()
    result: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for successor_id, predecessor_id in rows:
        result[successor_id].append(predecessor_id)
    return result


def create_task(
    db: Session, project_id: uuid.UUID, data: TaskCreate, created_by: uuid.UUID
) -> Task:
    get_project(db, project_id)
    _validate_task_refs(db, project_id, data.phase_id, data.assignee_id)
    _validate_wbs_unique(db, project_id, data.wbs_code)
    task = Task(**data.model_dump(), project_id=project_id, created_by=created_by)
    db.add(task)
    db.flush()
    return get_task(db, task.id)


def update_task(db: Session, task_id: uuid.UUID, data: TaskUpdate) -> Task:
    task = get_task(db, task_id)
    updates = data.model_dump(exclude_unset=True)
    if "phase_id" in updates or "assignee_id" in updates:
        _validate_task_refs(
            db,
            task.project_id,
            updates.get("phase_id", task.phase_id),
            updates.get("assignee_id", task.assignee_id),
        )
    if "wbs_code" in updates and updates["wbs_code"] != task.wbs_code:
        _validate_wbs_unique(db, task.project_id, updates["wbs_code"], exclude_id=task.id)
    # Keep status and progress coherent when only one of them is sent
    if updates.get("status") == WorkStatus.done and "progress_pct" not in updates:
        updates["progress_pct"] = 100
    if updates.get("progress_pct") == 100 and "status" not in updates:
        updates["status"] = WorkStatus.done
    for field, value in updates.items():
        setattr(task, field, value)
    return task


def delete_task(db: Session, task_id: uuid.UUID, user=None) -> None:
    task = get_task(db, task_id)
    trash.archive(db, task, entity_type="task", label=task.name, user=user)
    db.delete(task)


def _validate_task_refs(
    db: Session,
    project_id: uuid.UUID,
    phase_id: uuid.UUID | None,
    assignee_id: uuid.UUID | None,
) -> None:
    if phase_id is not None:
        phase = db.get(Phase, phase_id)
        if phase is None or phase.project_id != project_id:
            raise ValidationFailedError("Phase does not exist in this project")
    if assignee_id is not None and db.get(User, assignee_id) is None:
        raise ValidationFailedError("Assignee does not exist")


def _validate_wbs_unique(
    db: Session,
    project_id: uuid.UUID,
    wbs_code: str | None,
    exclude_id: uuid.UUID | None = None,
) -> None:
    if not wbs_code:
        return
    query = select(Task.id).where(Task.project_id == project_id, Task.wbs_code == wbs_code)
    if exclude_id is not None:
        query = query.where(Task.id != exclude_id)
    if db.scalar(query):
        raise ConflictError(f"WBS code {wbs_code} is already used in this project")


# --- Dependencies ----------------------------------------------------------


def add_dependency(db: Session, task_id: uuid.UUID, data: DependencyCreate) -> TaskDependency:
    successor = get_task(db, task_id)
    predecessor = get_task(db, data.predecessor_id)

    if predecessor.id == successor.id:
        raise ValidationFailedError("A task cannot depend on itself")
    if predecessor.project_id != successor.project_id:
        raise ValidationFailedError("Cross-project dependencies are not allowed")
    existing = db.get(TaskDependency, (predecessor.id, successor.id))
    if existing:
        raise ConflictError("Dependency already exists")

    if _would_create_cycle(db, successor.project_id, predecessor.id, successor.id):
        raise DependencyCycleError("Adding this dependency would create a cycle in the schedule")

    dep = TaskDependency(
        predecessor_id=predecessor.id,
        successor_id=successor.id,
        dep_type=data.dep_type,
        lag_days=data.lag_days,
    )
    db.add(dep)
    db.flush()
    return dep


def remove_dependency(db: Session, task_id: uuid.UUID, predecessor_id: uuid.UUID) -> None:
    dep = db.get(TaskDependency, (predecessor_id, task_id))
    if dep is None:
        raise NotFoundError("Dependency not found")
    db.delete(dep)


def _would_create_cycle(
    db: Session,
    project_id: uuid.UUID,
    new_predecessor: uuid.UUID,
    new_successor: uuid.UUID,
) -> bool:
    """DFS over the project's dependency graph: if new_predecessor is reachable
    from new_successor via successor edges, adding successor->...->predecessor
    edge closes a cycle (catches transitive cycles A->B->C->A)."""
    edges = db.execute(
        select(TaskDependency.predecessor_id, TaskDependency.successor_id)
        .join(Task, Task.id == TaskDependency.predecessor_id)
        .where(Task.project_id == project_id)
    ).all()
    successors: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for pred, succ in edges:
        successors[pred].append(succ)

    stack = [new_successor]
    visited: set[uuid.UUID] = set()
    while stack:
        current = stack.pop()
        if current == new_predecessor:
            return True
        if current in visited:
            continue
        visited.add(current)
        stack.extend(successors.get(current, ()))
    return False


# --- Gantt -----------------------------------------------------------------


def gantt_payload(db: Session, project_id: uuid.UUID) -> GanttPayload:
    get_project(db, project_id)
    phases = db.scalars(
        select(Phase).where(Phase.project_id == project_id).order_by(Phase.sequence)
    ).all()
    tasks = db.scalars(
        select(Task)
        .options(joinedload(Task.assignee))
        .where(Task.project_id == project_id)
        .order_by(Task.sort_order, Task.created_at)
    ).all()
    deps = db.scalars(
        select(TaskDependency)
        .join(Task, Task.id == TaskDependency.successor_id)
        .where(Task.project_id == project_id)
    ).all()
    # Only dated tasks have a duration, so only they can carry float
    schedulable = [
        cpm.TaskNode(id=t.id, start=t.planned_start, end=t.planned_end)
        for t in tasks
        if t.planned_start and t.planned_end and t.planned_end >= t.planned_start
    ]
    analysis = cpm.compute(
        schedulable,
        [(d.predecessor_id, d.successor_id, d.dep_type, d.lag_days) for d in deps],
    )

    gantt_tasks = []
    slippages: list[int] = []
    for t in tasks:
        slippage = (
            (t.planned_end - t.baseline_end).days
            if t.planned_end and t.baseline_end
            else None
        )
        if slippage is not None:
            slippages.append(slippage)
        gantt_tasks.append(
            GanttTask(
                id=t.id,
                phase_id=t.phase_id,
                name=t.name,
                wbs_code=t.wbs_code,
                status=t.status,
                progress_pct=t.progress_pct,
                planned_start=t.planned_start,
                planned_end=t.planned_end,
                actual_start=t.actual_start,
                actual_end=t.actual_end,
                baseline_start=t.baseline_start,
                baseline_end=t.baseline_end,
                slippage_days=slippage,
                is_milestone=t.is_milestone,
                sort_order=t.sort_order,
                assignee_name=t.assignee.full_name if t.assignee else None,
                total_float=analysis.total_float.get(t.id),
                is_critical=t.id in analysis.critical,
                early_start=analysis.early_start.get(t.id),
                early_finish=analysis.early_finish.get(t.id),
                late_start=analysis.late_start.get(t.id),
                late_finish=analysis.late_finish.get(t.id),
            )
        )

    return GanttPayload(
        project_id=project_id,
        phases=[GanttPhase.model_validate(p, from_attributes=True) for p in phases],
        tasks=gantt_tasks,
        dependencies=[DependencyRead.model_validate(dep) for dep in deps],
        critical_path_length=len(analysis.critical),
        project_finish=analysis.project_finish,
        has_baseline=any(t.baseline_end for t in tasks),
        worst_slippage_days=max(slippages) if slippages else None,
    )


def set_baseline(db: Session, project_id: uuid.UUID) -> int:
    """Freeze the current programme as the baseline to measure slippage against.

    Re-baselining overwrites the previous snapshot — that is the point: it is
    the schedule everyone agreed to, not an audit trail of every edit.
    """
    get_project(db, project_id)
    tasks = db.scalars(select(Task).where(Task.project_id == project_id)).all()
    stamped = 0
    for task in tasks:
        if task.planned_start and task.planned_end:
            task.baseline_start = task.planned_start
            task.baseline_end = task.planned_end
            stamped += 1
    db.flush()
    return stamped


def clear_baseline(db: Session, project_id: uuid.UUID) -> None:
    get_project(db, project_id)
    for task in db.scalars(select(Task).where(Task.project_id == project_id)):
        task.baseline_start = None
        task.baseline_end = None
    db.flush()


def count_overdue(db: Session, project_id: uuid.UUID) -> int:
    from datetime import date

    return (
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
