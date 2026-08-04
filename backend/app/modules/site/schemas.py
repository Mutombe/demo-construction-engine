import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import IssueSeverity, IssueStatus, WeatherCondition


class DiaryEntryBase(BaseModel):
    entry_date: date
    weather: WeatherCondition = WeatherCondition.sunny
    labour_headcount: int = Field(default=0, ge=0)
    plant_equipment: str | None = None
    work_done: str = Field(min_length=1)
    delays: str | None = None
    notes: str | None = None


class DiaryEntryCreate(DiaryEntryBase):
    pass


class DiaryEntryUpdate(BaseModel):
    entry_date: date | None = None
    weather: WeatherCondition | None = None
    labour_headcount: int | None = Field(default=None, ge=0)
    plant_equipment: str | None = None
    work_done: str | None = Field(default=None, min_length=1)
    delays: str | None = None
    notes: str | None = None


class DiaryLabourLine(BaseModel):
    worker_id: uuid.UUID
    quantity: Decimal = Field(ge=0)
    overtime_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = None


class DiaryLabourSet(BaseModel):
    lines: list[DiaryLabourLine]


class DiaryLabourRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    worker_id: uuid.UUID
    worker_name: str | None = None
    trade: str | None = None
    quantity: Decimal
    overtime_quantity: Decimal
    notes: str | None


class DiaryEntryRead(DiaryEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    created_at: datetime
    labour: list[DiaryLabourRead] = []
    # True once these labour lines exist as timesheets for the same day
    timesheets_pushed: bool = False


class TimesheetPushResult(BaseModel):
    diary_entry_id: uuid.UUID
    created: int
    updated: int
    skipped_locked: list[str]  # workers whose time is already in an approved pay run


class SiteIssueBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    severity: IssueSeverity = IssueSeverity.medium
    raised_date: date | None = None


class SiteIssueCreate(SiteIssueBase):
    pass


class SiteIssueUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    severity: IssueSeverity | None = None


class SiteIssueResolve(BaseModel):
    resolution_notes: str | None = None
    resolved_date: date | None = None


class SiteIssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None
    severity: IssueSeverity
    status: IssueStatus
    raised_date: date
    resolved_date: date | None
    resolution_notes: str | None
    created_at: datetime
