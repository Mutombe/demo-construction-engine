import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import StockMovementType


class StockItemBase(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    barcode: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    unit: str = Field(min_length=1, max_length=20)
    reorder_level: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = None


class StockItemCreate(StockItemBase):
    pass


class StockItemUpdate(BaseModel):
    barcode: str | None = Field(default=None, max_length=64)
    # qty_on_hand and unit_cost are deliberately absent — movements only
    code: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    reorder_level: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None
    is_active: bool | None = None


class StockItemRead(StockItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    unit_cost: Decimal
    qty_on_hand: Decimal
    is_active: bool
    low_stock: bool = False
    created_at: datetime


class GoodsInRequest(BaseModel):
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)
    movement_date: date | None = None
    reference: str | None = Field(default=None, max_length=60)
    notes: str | None = None


class IssueRequest(BaseModel):
    project_id: uuid.UUID
    boq_item_id: uuid.UUID | None = None
    quantity: Decimal = Field(gt=0)
    movement_date: date | None = None
    notes: str | None = None


class AdjustRequest(BaseModel):
    quantity: Decimal  # signed; validated non-zero in service
    notes: str = Field(min_length=1)
    movement_date: date | None = None


class StockMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    stock_item_id: uuid.UUID
    doc_number: str
    movement_type: StockMovementType
    movement_date: date
    quantity: Decimal
    unit_cost: Decimal
    project_id: uuid.UUID | None
    project_name: str | None = None
    reference: str | None
    notes: str | None
    created_at: datetime
