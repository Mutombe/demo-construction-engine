import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import PayBasis, PayItemKind, PayRunStatus

# --- Workers ----------------------------------------------------------------


class PayItemCreate(BaseModel):
    kind: PayItemKind
    label: str = Field(min_length=1, max_length=60)
    amount: Decimal = Field(gt=0)


class PayItemUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=60)
    amount: Decimal | None = Field(default=None, gt=0)
    is_active: bool | None = None


class PayItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: PayItemKind
    label: str
    amount: Decimal
    is_active: bool


class WorkerBase(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    trade: str = Field(min_length=1, max_length=60)
    national_id: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=40)
    pay_basis: PayBasis = PayBasis.daily
    rate: Decimal = Field(gt=0)


class WorkerCreate(WorkerBase):
    pass


class WorkerUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    trade: str | None = Field(default=None, min_length=1, max_length=60)
    national_id: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=40)
    pay_basis: PayBasis | None = None
    rate: Decimal | None = Field(default=None, gt=0)
    is_active: bool | None = None


class WorkerRead(WorkerBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_active: bool
    pay_items: list[PayItemRead] = []
    created_at: datetime


# --- Timesheets -------------------------------------------------------------


class TimesheetCreate(BaseModel):
    worker_id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID | None = None
    work_date: date
    quantity: Decimal = Field(gt=0)
    overtime_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = None


class TimesheetUpdate(BaseModel):
    task_id: uuid.UUID | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    overtime_quantity: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class BulkEntry(BaseModel):
    worker_id: uuid.UUID
    quantity: Decimal = Field(ge=0)  # zero rows are skipped, letting the grid submit everyone
    overtime_quantity: Decimal = Field(default=Decimal("0"), ge=0)


class TimesheetBulkCreate(BaseModel):
    project_id: uuid.UUID
    work_date: date
    entries: list[BulkEntry] = Field(min_length=1)


class TimesheetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    worker_id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID | None = None
    work_date: date
    quantity: Decimal
    overtime_quantity: Decimal
    notes: str | None
    pay_run_id: uuid.UUID | None
    worker_name: str | None = None
    worker_trade: str | None = None
    pay_basis: PayBasis | None = None
    project_code: str | None = None


# --- Pay runs ---------------------------------------------------------------


class PayRunCreate(BaseModel):
    period_start: date
    period_end: date
    notes: str | None = None


class ProjectAllocation(BaseModel):
    project_id: str
    project_code: str
    amount: str


class PayItemSnapshot(BaseModel):
    kind: str
    label: str
    amount: str


class PayRunLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    worker_id: uuid.UUID
    worker_name: str
    trade: str
    pay_basis: PayBasis
    rate: Decimal
    quantity: Decimal
    overtime_quantity: Decimal
    base_pay: Decimal
    overtime_pay: Decimal
    allowance_total: Decimal
    deduction_total: Decimal
    gross_pay: Decimal
    net_pay: Decimal
    pay_items: list[PayItemSnapshot] | None
    project_allocation: list[ProjectAllocation] | None


class PayRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doc_number: str
    period_start: date
    period_end: date
    status: PayRunStatus
    notes: str | None
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    base_total: Decimal
    overtime_total: Decimal
    allowance_total: Decimal
    deduction_total: Decimal
    gross_total: Decimal
    net_total: Decimal
    created_at: datetime
    line_count: int = 0


class PayRunDetail(PayRunRead):
    lines: list[PayRunLineRead] = []
