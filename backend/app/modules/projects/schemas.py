import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import ProjectStatus, WorkStatus


class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    client_id: uuid.UUID
    site_address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    status: ProjectStatus = ProjectStatus.planning
    planned_start: date | None = None
    planned_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    contract_value: Decimal | None = Field(default=None, ge=0)
    retention_pct: Decimal | None = Field(default=None, ge=0, le=100)
    project_manager_id: uuid.UUID | None = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    client_id: uuid.UUID | None = None
    site_address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    status: ProjectStatus | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    contract_value: Decimal | None = Field(default=None, ge=0)
    retention_pct: Decimal | None = Field(default=None, ge=0, le=100)
    project_manager_id: uuid.UUID | None = None


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    created_at: datetime
    updated_at: datetime


class ProjectListItem(ProjectRead):
    client_name: str | None = None
    project_manager_name: str | None = None


class ProjectSummary(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    status: ProjectStatus
    progress_pct: float
    budget_total: Decimal
    actual_total: Decimal
    budget_variance_pct: float | None  # None when there is no budget yet
    task_counts: dict[str, int]
    overdue_tasks: int
    days_remaining: int | None


class PhaseBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sequence: int = Field(ge=0)
    status: WorkStatus = WorkStatus.not_started
    planned_start: date | None = None
    planned_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None


class PhaseCreate(PhaseBase):
    pass


class PhaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sequence: int | None = Field(default=None, ge=0)
    status: WorkStatus | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None


class PhaseRead(PhaseBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID


class PhaseReorder(BaseModel):
    phase_ids: list[uuid.UUID]


class ProjectMapPin(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    status: ProjectStatus
    city: str | None
    site_address: str | None
    latitude: Decimal
    longitude: Decimal
    contract_value: Decimal | None
    client_name: str | None = None
    progress_pct: float = 0.0
