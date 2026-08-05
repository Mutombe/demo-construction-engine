import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import DependencyType, WorkStatus


class TaskBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    phase_id: uuid.UUID | None = None
    wbs_code: str | None = Field(default=None, max_length=30)
    assignee_id: uuid.UUID | None = None
    status: WorkStatus = WorkStatus.not_started
    progress_pct: int = Field(default=0, ge=0, le=100)
    planned_start: date | None = None
    planned_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    weight: Decimal | None = Field(default=None, ge=0)
    is_milestone: bool = False
    sort_order: int = 0


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    phase_id: uuid.UUID | None = None
    wbs_code: str | None = Field(default=None, max_length=30)
    assignee_id: uuid.UUID | None = None
    status: WorkStatus | None = None
    progress_pct: int | None = Field(default=None, ge=0, le=100)
    planned_start: date | None = None
    planned_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    weight: Decimal | None = Field(default=None, ge=0)
    is_milestone: bool | None = None
    sort_order: int | None = None


class DependencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    predecessor_id: uuid.UUID
    successor_id: uuid.UUID
    dep_type: DependencyType
    lag_days: int


class TaskRead(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class TaskListItem(TaskRead):
    assignee_name: str | None = None
    phase_name: str | None = None
    predecessor_ids: list[uuid.UUID] = []


class DependencyCreate(BaseModel):
    predecessor_id: uuid.UUID
    dep_type: DependencyType = DependencyType.FS
    lag_days: int = 0


# --- Gantt payload ---------------------------------------------------------


class GanttTask(BaseModel):
    id: uuid.UUID
    phase_id: uuid.UUID | None
    name: str
    wbs_code: str | None
    status: WorkStatus
    progress_pct: int
    planned_start: date | None
    planned_end: date | None
    actual_start: date | None
    actual_end: date | None
    baseline_start: date | None = None
    baseline_end: date | None = None
    # Days the planned finish has moved since the baseline was set (+ is late)
    slippage_days: int | None = None
    is_milestone: bool
    sort_order: int
    assignee_name: str | None
    # Critical path analysis (null when the task has no planned dates)
    total_float: int | None = None
    is_critical: bool = False
    early_start: date | None = None
    early_finish: date | None = None
    late_start: date | None = None
    late_finish: date | None = None


class GanttPhase(BaseModel):
    id: uuid.UUID
    name: str
    sequence: int
    status: WorkStatus
    planned_start: date | None
    planned_end: date | None
    actual_start: date | None
    actual_end: date | None


class GanttPayload(BaseModel):
    project_id: uuid.UUID
    phases: list[GanttPhase]
    tasks: list[GanttTask]
    dependencies: list[DependencyRead]
    critical_path_length: int = 0  # tasks with zero or negative float
    project_finish: date | None = None  # earliest finish across the network
    has_baseline: bool = False
    worst_slippage_days: int | None = None


class WorkloadTask(BaseModel):
    id: uuid.UUID
    name: str
    project_id: uuid.UUID
    project_name: str
    project_code: str
    status: str
    planned_start: date | None
    planned_end: date | None
    progress_pct: int
    is_scheduled: bool


class WorkloadDay(BaseModel):
    day: date
    task_count: int
    over: bool


class WorkloadPerson(BaseModel):
    user_id: uuid.UUID | None
    full_name: str
    role: str | None
    open_tasks: int
    busy_days: int
    peak_concurrency: int
    overloaded_days: int
    hours_booked: float
    next_free_day: date | None
    days: list[WorkloadDay]
    tasks: list[WorkloadTask]


class Workload(BaseModel):
    start: date
    end: date
    concurrency_limit: int
    people: list[WorkloadPerson]
