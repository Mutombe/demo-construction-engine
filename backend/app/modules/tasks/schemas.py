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
    is_milestone: bool
    sort_order: int
    assignee_name: str | None


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
