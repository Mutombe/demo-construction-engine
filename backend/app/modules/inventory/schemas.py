import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import StockMovementType, StocktakeStatus


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


class ReorderSuggestion(BaseModel):
    """One low-stock item with the supplier and price its last delivery came at."""

    stock_item_id: uuid.UUID
    code: str
    name: str
    unit: str
    qty_on_hand: Decimal
    reorder_level: Decimal
    suggested_quantity: Decimal
    last_unit_cost: Decimal
    estimated_cost: Decimal
    supplier_id: uuid.UUID | None
    supplier_name: str | None
    last_po_number: str | None
    last_ordered: date | None


class ReorderSuggestions(BaseModel):
    items: list[ReorderSuggestion]
    total_estimated_cost: Decimal
    without_supplier: int  # need a supplier picked by hand


class ReorderRequest(BaseModel):
    """Raise draft POs for these stock items, grouped by their usual supplier."""

    project_id: uuid.UUID
    stock_item_ids: list[uuid.UUID] = Field(min_length=1)
    expected_delivery: date | None = None


class ReorderResult(BaseModel):
    po_ids: list[uuid.UUID]
    po_numbers: list[str]
    skipped_items: list[str]  # codes with no known supplier


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


# --- Stocktake ---------------------------------------------------------------


class StocktakeCreate(BaseModel):
    count_date: date | None = None
    notes: str | None = None
    # Empty means "count everything active"
    stock_item_ids: list[uuid.UUID] = Field(default_factory=list)
    category: str | None = None  # cycle-count one category at a time


class StocktakeCountLine(BaseModel):
    stock_item_id: uuid.UUID
    counted_quantity: Decimal = Field(ge=0)
    notes: str | None = None


class StocktakeCountSet(BaseModel):
    lines: list[StocktakeCountLine]


class StocktakeLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    stock_item_id: uuid.UUID
    code: str = ""
    name: str = ""
    unit: str = ""
    expected_quantity: Decimal
    counted_quantity: Decimal | None
    unit_cost: Decimal
    variance_quantity: Decimal = Decimal("0")
    variance_value: Decimal = Decimal("0")
    notes: str | None


class StocktakeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doc_number: str
    status: StocktakeStatus
    count_date: date
    notes: str | None
    approved_at: datetime | None
    created_by: uuid.UUID | None
    created_at: datetime
    line_count: int = 0
    counted_count: int = 0
    variance_value: Decimal = Decimal("0")


class StocktakeDetail(StocktakeRead):
    lines: list[StocktakeLineRead] = []
