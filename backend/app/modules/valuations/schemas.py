import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import ValuationStatus


class ValuationCreate(BaseModel):
    period_end: date
    gross_valuation: Decimal = Field(gt=0)
    notes: str | None = None


class ValuationUpdate(BaseModel):
    period_end: date | None = None
    gross_valuation: Decimal | None = Field(default=None, gt=0)
    notes: str | None = None


class ValuationIssue(BaseModel):
    issued_date: date | None = None


class ValuationPay(BaseModel):
    paid_date: date | None = None


class ValuationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    doc_number: str
    valuation_number: int
    status: ValuationStatus
    period_end: date
    gross_valuation: Decimal
    retention_amount: Decimal
    previous_certified: Decimal
    net_certified: Decimal
    issued_date: date | None
    paid_date: date | None
    notes: str | None
    is_measured: bool = False
    created_at: datetime


class ValuationLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    boq_item_id: uuid.UUID | None
    item_code: str
    description: str
    unit: str
    rate: Decimal
    boq_quantity: Decimal
    qty_to_date: Decimal
    amount: Decimal


class ValuationDetail(ValuationRead):
    project_name: str | None = None
    project_code: str | None = None
    lines: list[ValuationLineRead] = []


# --- Measurement sheet --------------------------------------------------------


class MeasurementLineIn(BaseModel):
    boq_item_id: uuid.UUID
    qty_to_date: Decimal = Field(ge=0)


class MeasurementSet(BaseModel):
    lines: list[MeasurementLineIn]


class MeasurementItem(BaseModel):
    boq_item_id: uuid.UUID
    item_code: str
    description: str
    unit: str
    boq_quantity: Decimal
    rate: Decimal
    previous_qty: Decimal
    current_qty: Decimal | None  # qty on this draft's sheet, if measured


class MeasurementSection(BaseModel):
    code: str
    title: str
    items: list[MeasurementItem]


class MeasurementContext(BaseModel):
    valuation_id: uuid.UUID
    sections: list[MeasurementSection]


class RevenueSummary(BaseModel):
    project_id: uuid.UUID
    contract_value: Decimal | None
    retention_pct: Decimal | None
    certified_gross: Decimal
    retention_held: Decimal
    invoiced_to_date: Decimal
    paid_to_date: Decimal
    outstanding: Decimal
    suggested_gross: Decimal | None
    valuation_count: int
