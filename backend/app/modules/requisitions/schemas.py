import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import RequisitionStatus


class RequisitionItemCreate(BaseModel):
    boq_item_id: uuid.UUID | None = None
    description: str = Field(min_length=1)
    unit: str = Field(min_length=1, max_length=20)
    quantity: Decimal = Field(gt=0)


class RequisitionCreate(BaseModel):
    needed_by: date | None = None
    notes: str | None = None
    items: list[RequisitionItemCreate] = Field(min_length=1)


class RequisitionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    boq_item_id: uuid.UUID | None
    description: str
    unit: str
    quantity: Decimal


class RequisitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    doc_number: str
    status: RequisitionStatus
    needed_by: date | None
    notes: str | None
    actioned_at: datetime | None
    rfq_id: uuid.UUID | None
    po_id: uuid.UUID | None
    created_by: uuid.UUID | None
    created_at: datetime
    # Derived for the aging queue
    age_days: int = 0
    is_urgent: bool = False
    item_count: int = 0
    project_name: str | None = None
    project_code: str | None = None
    requested_by_name: str | None = None


class RequisitionDetail(RequisitionRead):
    items: list[RequisitionItemRead] = []


class ConvertToPo(BaseModel):
    supplier_id: uuid.UUID
    expected_delivery: date | None = None
    notes: str | None = None
