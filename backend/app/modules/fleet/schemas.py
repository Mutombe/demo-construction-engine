import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import (
    EquipmentCategory,
    EquipmentStatus,
    MeterSource,
    MeterType,
    Ownership,
)


class EquipmentBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: EquipmentCategory = EquipmentCategory.other
    make: str | None = Field(default=None, max_length=60)
    model: str | None = Field(default=None, max_length=60)
    registration: str | None = Field(default=None, max_length=30)
    serial_number: str | None = Field(default=None, max_length=60)
    year: int | None = Field(default=None, ge=1950, le=2100)
    ownership: Ownership = Ownership.owned
    hourly_rate: Decimal | None = Field(default=None, ge=0)
    supplier_id: uuid.UUID | None = None
    meter_type: MeterType = MeterType.hours
    expected_burn_rate: Decimal | None = Field(default=None, ge=0)
    purchase_date: date | None = None
    purchase_cost: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class EquipmentCreate(EquipmentBase):
    code: str = Field(min_length=1, max_length=20)
    current_meter: Decimal = Field(default=Decimal("0"), ge=0)


class EquipmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: EquipmentCategory | None = None
    make: str | None = Field(default=None, max_length=60)
    model: str | None = Field(default=None, max_length=60)
    registration: str | None = Field(default=None, max_length=30)
    serial_number: str | None = Field(default=None, max_length=60)
    year: int | None = Field(default=None, ge=1950, le=2100)
    ownership: Ownership | None = None
    hourly_rate: Decimal | None = Field(default=None, ge=0)
    supplier_id: uuid.UUID | None = None
    status: EquipmentStatus | None = None
    expected_burn_rate: Decimal | None = Field(default=None, ge=0)
    purchase_cost: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None
    is_active: bool | None = None


class EquipmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    category: EquipmentCategory
    make: str | None
    model: str | None
    registration: str | None
    serial_number: str | None
    year: int | None
    ownership: Ownership
    hourly_rate: Decimal | None
    supplier_id: uuid.UUID | None
    supplier_name: str | None = None
    status: EquipmentStatus
    current_project_id: uuid.UUID | None
    current_project_name: str | None = None
    meter_type: MeterType
    current_meter: Decimal
    expected_burn_rate: Decimal | None
    purchase_date: date | None
    purchase_cost: Decimal | None
    is_active: bool


class MeterReadingCreate(BaseModel):
    reading_date: date | None = None
    meter: Decimal = Field(ge=0)
    source: MeterSource = MeterSource.manual
    project_id: uuid.UUID | None = None
    idle_hours: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class MeterReadingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    equipment_id: uuid.UUID
    reading_date: date
    meter: Decimal
    source: MeterSource
    project_id: uuid.UUID | None
    idle_hours: Decimal | None
    notes: str | None


class FuelLogCreate(BaseModel):
    log_date: date | None = None
    litres: Decimal = Field(gt=0)
    meter: Decimal | None = Field(default=None, ge=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)
    total_cost: Decimal | None = Field(default=None, ge=0)
    project_id: uuid.UUID | None = None
    stock_item_id: uuid.UUID | None = None
    reference: str | None = Field(default=None, max_length=60)
    operator: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class FuelLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    equipment_id: uuid.UUID
    log_date: date
    litres: Decimal
    meter: Decimal | None
    unit_cost: Decimal | None
    total_cost: Decimal | None
    project_id: uuid.UUID | None
    reference: str | None
    operator: str | None


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    interval_meter: Decimal | None = Field(default=None, gt=0)
    interval_days: int | None = Field(default=None, gt=0)
    last_done_meter: Decimal | None = Field(default=None, ge=0)
    last_done_date: date | None = None


class ScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    equipment_id: uuid.UUID
    name: str
    interval_meter: Decimal | None
    interval_days: int | None
    last_done_meter: Decimal | None
    last_done_date: date | None
    is_active: bool


class MaintenanceCreate(BaseModel):
    schedule_id: uuid.UUID | None = None
    service_date: date | None = None
    meter: Decimal | None = Field(default=None, ge=0)
    description: str = Field(min_length=1)
    cost: Decimal | None = Field(default=None, ge=0)
    downtime_hours: Decimal | None = Field(default=None, ge=0)
    supplier_id: uuid.UUID | None = None
    reference: str | None = Field(default=None, max_length=60)


class MaintenanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    equipment_id: uuid.UUID
    schedule_id: uuid.UUID | None
    service_date: date
    meter: Decimal | None
    description: str
    cost: Decimal | None
    downtime_hours: Decimal | None
    reference: str | None


class AssignmentCreate(BaseModel):
    project_id: uuid.UUID
    started_on: date | None = None
    notes: str | None = None


class AssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    equipment_id: uuid.UUID
    project_id: uuid.UUID
    started_on: date
    ended_on: date | None
    notes: str | None
