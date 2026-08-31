import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SyncOperationIn(BaseModel):
    """A capture from a device, exactly as it was written on site."""

    # Generated on the device before the record is saved locally, so it is
    # stable across every retry.
    client_op_id: uuid.UUID
    op_type: str = Field(max_length=40)
    payload: dict[str, Any] = {}
    captured_at: datetime | None = None


class SyncPush(BaseModel):
    device_id: str = Field(min_length=1, max_length=80)
    operations: list[SyncOperationIn] = Field(default_factory=list, max_length=500)


class SyncResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    client_op_id: uuid.UUID
    status: str
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    detail: str | None = None


class SyncPushResult(BaseModel):
    applied: int
    merged: int
    duplicate: int
    rejected: int
    results: list[SyncResult]
    server_time: datetime


class BootstrapWorker(BaseModel):
    id: uuid.UUID
    full_name: str
    trade: str | None = None


class BootstrapEquipment(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    meter_type: str
    current_meter: float


class BootstrapIssue(BaseModel):
    id: uuid.UUID
    title: str
    severity: str
    raised_date: date


class Bootstrap(BaseModel):
    """Everything a phone needs to fill in the day's forms with no signal.

    Deliberately small. A pack that tries to mirror the database will not
    finish downloading on the connection the site actually has.
    """

    project_id: uuid.UUID
    project_code: str
    project_name: str
    server_time: datetime
    workers: list[BootstrapWorker]
    equipment: list[BootstrapEquipment]
    open_issues: list[BootstrapIssue]
    diary_dates: list[date]
