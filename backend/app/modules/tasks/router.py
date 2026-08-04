import uuid

from fastapi import APIRouter, Depends

from app.common.enums import UserRole, WorkStatus
from app.core.deps import CurrentUser, DbDep, require_roles
from app.modules.tasks import service
from app.modules.tasks.schemas import (
    DependencyCreate,
    DependencyRead,
    GanttPayload,
    TaskCreate,
    TaskListItem,
    TaskRead,
    TaskUpdate,
)

router = APIRouter(tags=["tasks"])

task_write = Depends(require_roles(UserRole.project_manager, UserRole.site_manager))


def _to_list_item(db, task, preds: dict | None = None) -> TaskListItem:
    item = TaskListItem.model_validate(task)
    item.assignee_name = task.assignee.full_name if task.assignee else None
    item.phase_name = task.phase.name if task.phase else None
    if preds is not None:
        item.predecessor_ids = preds.get(task.id, [])
    return item


@router.get("/projects/{project_id}/tasks", response_model=list[TaskListItem])
def list_tasks(
    project_id: uuid.UUID,
    db: DbDep,
    phase_id: uuid.UUID | None = None,
    status: WorkStatus | None = None,
    assignee_id: uuid.UUID | None = None,
) -> list[TaskListItem]:
    tasks = service.list_tasks(db, project_id, phase_id, status, assignee_id)
    preds = service.predecessor_map(db, project_id)
    return [_to_list_item(db, t, preds) for t in tasks]


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
def delete_task(task_id: uuid.UUID, db: DbDep) -> None:
    service.delete_task(db, task_id)


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
