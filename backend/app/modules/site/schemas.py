import uuid
from datetime import date, datetime

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


class DiaryEntryRead(DiaryEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    created_at: datetime


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
