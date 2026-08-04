import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import (
    StockLocationKind,
    StockMovementType,
    StocktakeStatus,
    TrackingMode,
)


class StockItemBase(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    tracking_mode: TrackingMode = TrackingMode.none
    expiry_warning_days: int = Field(default=30, ge=0, le=365)
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
    tracking_mode: TrackingMode | None = None
    expiry_warning_days: int | None = Field(default=None, ge=0, le=365)
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
    # Omit to use the default location — keeps single-store callers unchanged
    location_id: uuid.UUID | None = None
    # Required for batch/serial-tracked items; ignored for untracked ones
    batch_number: str | None = Field(default=None, max_length=60)
    expiry_date: date | None = None
    supplier_ref: str | None = Field(default=None, max_length=60)
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)
    movement_date: date | None = None
    reference: str | None = Field(default=None, max_length=60)
    notes: str | None = None


class IssueRequest(BaseModel):
    location_id: uuid.UUID | None = None
    # Name a lot to force it; otherwise the earliest expiry goes first
    batch_id: uuid.UUID | None = None
    project_id: uuid.UUID
    boq_item_id: uuid.UUID | None = None
    quantity: Decimal = Field(gt=0)
    movement_date: date | None = None
    notes: str | None = None


class AdjustRequest(BaseModel):
    location_id: uuid.UUID | None = None
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
    location_id: uuid.UUID | None = None
    location_name: str | None = None
    project_id: uuid.UUID | None
    project_name: str | None = None
    reference: str | None
    notes: str | None
    created_at: datetime


# --- Stocktake ---------------------------------------------------------------


class StocktakeCreate(BaseModel):
    location_id: uuid.UUID | None = None
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
    location_id: uuid.UUID | None
    location_name: str | None = None
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


# --- Locations and transfers -------------------------------------------------


class StockLocationBase(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=120)
    kind: StockLocationKind = StockLocationKind.store
    project_id: uuid.UUID | None = None
    address: str | None = None


class StockLocationCreate(StockLocationBase):
    pass


class StockLocationUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=20)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: StockLocationKind | None = None
    project_id: uuid.UUID | None = None
    address: str | None = None
    is_active: bool | None = None


class StockLocationRead(StockLocationBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_default: bool
    is_active: bool
    project_name: str | None = None
    item_count: int = 0  # distinct items holding stock here
    stock_value: Decimal = Decimal("0")
    created_at: datetime


class StockLevelRead(BaseModel):
    """One item's balance at one location."""

    location_id: uuid.UUID
    location_code: str
    location_name: str
    quantity: Decimal
    value: Decimal


class TransferRequest(BaseModel):
    stock_item_id: uuid.UUID
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    quantity: Decimal = Field(gt=0)
    transfer_date: date | None = None
    notes: str | None = None


class StockTransferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doc_number: str
    stock_item_id: uuid.UUID
    item_code: str = ""
    item_name: str = ""
    from_location_id: uuid.UUID
    from_location_name: str = ""
    to_location_id: uuid.UUID
    to_location_name: str = ""
    transfer_date: date
    quantity: Decimal
    unit_cost: Decimal
    value: Decimal = Decimal("0")
    notes: str | None
    created_at: datetime


# --- Batches -----------------------------------------------------------------


class StockBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    stock_item_id: uuid.UUID
    item_code: str = ""
    item_name: str = ""
    location_id: uuid.UUID
    location_name: str = ""
    batch_number: str
    expiry_date: date | None
    received_date: date
    quantity: Decimal
    supplier_ref: str | None
    notes: str | None
    # Derived
    days_to_expiry: int | None = None
    is_expired: bool = False
    is_expiring_soon: bool = False
    value: Decimal = Decimal("0")


class ExpiryReport(BaseModel):
    """Stock that is past its date or heading there, worst first."""

    expired: list[StockBatchRead]
    expiring_soon: list[StockBatchRead]
    expired_value: Decimal
    expiring_value: Decimal


class RecallUsage(BaseModel):
    """One place a recalled lot ended up."""

    movement_id: uuid.UUID
    doc_number: str
    movement_date: date
    quantity: Decimal
    location_name: str | None
    project_id: uuid.UUID | None
    project_name: str | None


class RecallTrace(BaseModel):
    batch_number: str
    batches: list[StockBatchRead]
    remaining_quantity: Decimal
    issued_quantity: Decimal
    usages: list[RecallUsage]


# --- Analytics and forecasting ------------------------------------------------


class InventoryAnalyticsRow(BaseModel):
    stock_item_id: uuid.UUID
    code: str
    name: str
    category: str | None
    unit: str
    qty_on_hand: Decimal
    stock_value: Decimal
    average_stock_value: Decimal
    issued_quantity: Decimal
    issued_value: Decimal
    # None when there was no movement to judge by, rather than a fake zero
    turnover_ratio: Decimal | None = None
    days_on_hand: int | None = None
    annual_carrying_cost: Decimal
    last_movement: date | None = None
    last_issue: date | None = None
    days_since_issue: int | None = None
    is_dead_stock: bool = False


class InventoryAnalytics(BaseModel):
    window_days: int
    carrying_rate: Decimal
    total_stock_value: Decimal
    total_issued_value: Decimal
    annual_carrying_cost: Decimal
    dead_stock_value: Decimal
    dead_stock_count: int
    rows: list[InventoryAnalyticsRow]


class DemandForecastRow(BaseModel):
    stock_item_id: uuid.UUID
    code: str
    name: str
    unit: str
    qty_on_hand: Decimal
    reorder_level: Decimal
    lead_time_days: int
    # False when there is too little history to say anything honest
    has_enough_history: bool
    daily_usage: Decimal | None = None
    monthly_usage: Decimal | None = None
    days_of_cover: int | None = None
    projected_stockout: date | None = None
    suggested_reorder_point: Decimal | None = None
    suggested_order_quantity: Decimal | None = None
    reorder_level_is_low: bool = False
    needs_ordering: bool = False


class DemandForecast(BaseModel):
    window_days: int
    lead_time_days: int
    safety_days: int
    rows: list[DemandForecastRow]
    needs_ordering_count: int
    forecastable_count: int


class ConsumptionMonth(BaseModel):
    month: str
    quantity: Decimal


class ConsumptionTrend(BaseModel):
    stock_item_id: uuid.UUID
    months: list[ConsumptionMonth]
    total: Decimal
