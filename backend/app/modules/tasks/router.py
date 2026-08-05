import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from app.common.enums import TaskPriority, UserRole, WorkStatus
from app.core.deps import CurrentUser, DbDep, require_roles
from app.core.exceptions import ValidationFailedError
from app.modules.comments import service as comment_service
from app.modules.tasks import service
from app.modules.tasks import calendar as calendar_service
from app.modules.tasks import workload as workload_service
from app.modules.tasks.workload import DEFAULT_CONCURRENCY_LIMIT
from app.modules.tasks.schemas import (
    DependencyCreate,
    DependencyRead,
    GanttPayload,
    TaskCreate,
    TaskListItem,
    TaskRead,
    TaskUpdate,
    CalendarPayload,
    Workload,
)

router = APIRouter(tags=["tasks"])

task_write = Depends(require_roles(UserRole.project_manager, UserRole.site_manager))


def _to_list_item(
    db,
    task,
    preds: dict | None = None,
    subtasks: dict | None = None,
    comments: dict | None = None,
) -> TaskListItem:
    item = TaskListItem.model_validate(task)
    item.assignee_name = task.assignee.full_name if task.assignee else None
    item.phase_name = task.phase.name if task.phase else None
    if preds is not None:
        item.predecessor_ids = preds.get(task.id, [])
    if subtasks is not None:
        total, done = subtasks.get(task.id, (0, 0))
        item.subtask_count, item.subtasks_done = total, done
    if comments is not None:
        item.comment_count = comments.get(task.id, 0)
    return item


@router.get("/projects/{project_id}/tasks", response_model=list[TaskListItem])
def list_tasks(
    project_id: uuid.UUID,
    db: DbDep,
    phase_id: uuid.UUID | None = None,
    status: WorkStatus | None = None,
    assignee_id: uuid.UUID | None = None,
    priority: TaskPriority | None = None,
    tag: str | None = None,
    parent_id: uuid.UUID | None = None,
    top_level_only: bool = False,
) -> list[TaskListItem]:
    tasks = service.list_tasks(
        db, project_id, phase_id, status, assignee_id, priority, tag, parent_id, top_level_only
    )
    preds = service.predecessor_map(db, project_id)
    subtasks = service.subtask_rollup(db, project_id)
    comments = comment_service.counts_for(db, "task", [t.id for t in tasks])
    return [_to_list_item(db, t, preds, subtasks, comments) for t in tasks]


@router.get("/projects/{project_id}/tags", response_model=list[str])
def list_project_tags(project_id: uuid.UUID, db: DbDep) -> list[str]:
    """Every tag in use on this project, so filters offer real options rather
    than asking people to remember what they typed."""
    return service.project_tags(db, project_id)


@router.post("/projects/{project_id}/tasks", response_model=TaskRead, status_code=201)
def create_task(
    project_id: uuid.UUID,
    body: TaskCreate,
    db: DbDep,
    user=Depends(require_roles(UserRole.project_manager, UserRole.site_manager)),
) -> TaskRead:
    return TaskRead.model_validate(service.create_task(db, project_id, body, user.id))


@router.get("/projects/{project_id}/gantt", response_model=GanttPayload)
def get_gantt(project_id: uuid.UUID, db: DbDep) -> GanttPayload:
    return service.gantt_payload(db, project_id)


@router.post("/projects/{project_id}/baseline", response_model=GanttPayload)
def set_baseline(
    project_id: uuid.UUID,
    db: DbDep,
    _=Depends(require_roles(UserRole.project_manager)),
) -> GanttPayload:
    service.set_baseline(db, project_id)
    return service.gantt_payload(db, project_id)


@router.delete("/projects/{project_id}/baseline", response_model=GanttPayload)
def clear_baseline(
    project_id: uuid.UUID,
    db: DbDep,
    _=Depends(require_roles(UserRole.project_manager)),
) -> GanttPayload:
    service.clear_baseline(db, project_id)
    return service.gantt_payload(db, project_id)


@router.get("/tasks/my", response_model=list[TaskListItem])
def my_tasks(db: DbDep, user: CurrentUser) -> list[TaskListItem]:
    return [_to_list_item(db, t) for t in service.list_my_tasks(db, user.id)]


@router.get("/tasks/{task_id}", response_model=TaskListItem)
def get_task(task_id: uuid.UUID, db: DbDep) -> TaskListItem:
    task = service.get_task(db, task_id)
    preds = service.predecessor_map(db, task.project_id)
    return _to_list_item(db, task, preds)


@router.patch("/tasks/{task_id}", response_model=TaskRead, dependencies=[task_write])
def update_task(task_id: uuid.UUID, body: TaskUpdate, db: DbDep) -> TaskRead:
    return TaskRead.model_validate(service.update_task(db, task_id, body))


@router.delete("/tasks/{task_id}", status_code=204, dependencies=[task_write])
def delete_task(task_id: uuid.UUID, db: DbDep, user: CurrentUser) -> None:
    service.delete_task(db, task_id, user)


@router.post(
    "/tasks/{task_id}/dependencies",
    response_model=DependencyRead,
    status_code=201,
    dependencies=[task_write],
)
def add_dependency(task_id: uuid.UUID, body: DependencyCreate, db: DbDep) -> DependencyRead:
    return DependencyRead.model_validate(service.add_dependency(db, task_id, body))


@router.delete(
    "/tasks/{task_id}/dependencies/{predecessor_id}",
    status_code=204,
    dependencies=[task_write],
)
def remove_dependency(task_id: uuid.UUID, predecessor_id: uuid.UUID, db: DbDep) -> None:
    service.remove_dependency(db, task_id, predecessor_id)


@router.get("/workload", response_model=Workload)
def get_workload(
    db: DbDep,
    start: date | None = None,
    end: date | None = None,
    project_id: uuid.UUID | None = None,
    limit: int = Query(default=DEFAULT_CONCURRENCY_LIMIT, ge=1, le=10),
) -> Workload:
    """Defaults to the next four weeks, which is the horizon a site actually
    reschedules within."""
    today = date.today()
    start = start or today
    end = end or (start + timedelta(days=27))
    if end < start:
        raise ValidationFailedError("The end of the window cannot precede its start")
    if (end - start).days > 120:
        raise ValidationFailedError("Windows longer than 120 days are not supported")
    return Workload.model_validate(
        workload_service.workload(db, start, end, project_id, limit), from_attributes=True
    )


@router.get("/calendar", response_model=CalendarPayload)
def get_calendar(
    db: DbDep,
    start: date | None = None,
    end: date | None = None,
    project_id: uuid.UUID | None = None,
) -> CalendarPayload:
    """Defaults to the current calendar month."""
    today = date.today()
    start = start or today.replace(day=1)
    if end is None:
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    if end < start:
        raise ValidationFailedError("The end of the window cannot precede its start")
    if (end - start).days > 366:
        raise ValidationFailedError("Windows longer than a year are not supported")
    return CalendarPayload.model_validate(
        calendar_service.calendar(db, start, end, project_id), from_attributes=True
    )
