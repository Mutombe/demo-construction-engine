import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import PoDestination, PoStatus, QuoteStatus, RfqStatus
from app.modules.inventory.schemas import StockItemCreate

# --- Suppliers --------------------------------------------------------------


class SupplierBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = None
    tax_id: str | None = Field(default=None, max_length=60)
    categories: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = None
    tax_id: str | None = Field(default=None, max_length=60)
    categories: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    is_active: bool | None = None


class SupplierRead(SupplierBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_active: bool
    created_at: datetime


# --- RFQs -------------------------------------------------------------------


class RfqItemCreate(BaseModel):
    boq_item_id: uuid.UUID
    quantity: Decimal | None = Field(default=None, gt=0)  # default: BOQ quantity


class RfqItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    boq_item_id: uuid.UUID | None
    description: str
    unit: str
    quantity: Decimal
    sort_order: int


class RfqCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str | None = None
    due_date: date | None = None
    ai_generated: bool = False
    items: list[RfqItemCreate] = Field(min_length=1)


class RfqUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = None
    due_date: date | None = None


class RfqRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    doc_number: str
    title: str
    status: RfqStatus
    due_date: date | None
    ai_generated: bool
    created_at: datetime
    item_count: int = 0
    quote_count: int = 0


class RfqDetail(RfqRead):
    body: str | None
    items: list[RfqItemRead] = []
    project_name: str | None = None
    project_code: str | None = None


class RfqItemsReplace(BaseModel):
    items: list[RfqItemCreate] = Field(min_length=1)


# --- Quotes -----------------------------------------------------------------


class QuoteItemCreate(BaseModel):
    rfq_item_id: uuid.UUID | None = None
    description: str = Field(min_length=1)
    unit: str | None = Field(default=None, max_length=20)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)


class QuoteItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rfq_item_id: uuid.UUID | None
    description: str
    unit: str | None
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    unit_mismatch: bool = False
    quantity_mismatch: bool = False


class QuoteCreate(BaseModel):
    supplier_id: uuid.UUID
    received_date: date | None = None
    valid_until: date | None = None
    payment_terms: str | None = Field(default=None, max_length=255)
    delivery_terms: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    raw_text: str | None = None
    ai_extracted: bool = False
    items: list[QuoteItemCreate] = Field(min_length=1)


class QuoteUpdate(BaseModel):
    valid_until: date | None = None
    payment_terms: str | None = Field(default=None, max_length=255)
    delivery_terms: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class QuoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rfq_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: str | None = None
    status: QuoteStatus
    received_date: date
    valid_until: date | None
    payment_terms: str | None
    delivery_terms: str | None
    notes: str | None
    ai_extracted: bool
    total_amount: Decimal
    coverage_pct: float = 100.0
    items: list[QuoteItemRead] = []


# --- Purchase orders --------------------------------------------------------


class PoItemCreate(BaseModel):
    boq_item_id: uuid.UUID | None = None
    description: str = Field(min_length=1)
    unit: str | None = Field(default=None, max_length=20)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)


class PoItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    boq_item_id: uuid.UUID | None
    description: str
    unit: str | None
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


class PoCreate(BaseModel):
    supplier_id: uuid.UUID | None = None  # required when no quote_id
    quote_id: uuid.UUID | None = None  # lines derived from quote when set
    expected_delivery: date | None = None
    terms: str | None = None
    notes: str | None = None
    ai_generated: bool = False
    items: list[PoItemCreate] | None = None  # ignored when quote_id set


class PoUpdate(BaseModel):
    expected_delivery: date | None = None
    terms: str | None = None
    notes: str | None = None


class PoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: str | None = None
    quote_id: uuid.UUID | None
    doc_number: str
    status: PoStatus
    order_date: date
    expected_delivery: date | None
    received_date: date | None
    received_to: PoDestination | None
    ai_generated: bool
    total_amount: Decimal
    created_at: datetime
    project_code: str | None = None
    # Delivery tracking: issued and past its expected delivery date
    is_overdue: bool = False
    days_overdue: int = 0


class PoDetail(PoRead):
    terms: str | None
    notes: str | None
    items: list[PoItemRead] = []
    project_name: str | None = None
    project_code: str | None = None


class PoStoreLineMapping(BaseModel):
    po_item_id: uuid.UUID
    stock_item_id: uuid.UUID | None = None
    new_item: StockItemCreate | None = None  # exactly one of the two


class PoReceive(BaseModel):
    received_date: date | None = None
    destination: PoDestination = PoDestination.project
    # Which store took delivery; omitted means the default location
    location_id: uuid.UUID | None = None
    store_lines: list[PoStoreLineMapping] | None = None


class SupplierQuoteActivity(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rfq_id: uuid.UUID
    rfq_doc_number: str | None = None
    rfq_title: str | None = None
    status: QuoteStatus
    received_date: date
    total_amount: Decimal


class SupplierActivityTotals(BaseModel):
    po_count: int
    po_value: Decimal
    quote_count: int


class SupplierScorecard(BaseModel):
    """Performance metrics derived from this supplier's own order history."""

    # Delivery reliability
    delivered_count: int  # received POs that had an expected date
    on_time_count: int
    on_time_pct: Decimal | None  # None when there is nothing to judge yet
    avg_delay_days: Decimal | None  # mean lateness across delivered POs
    open_overdue_count: int
    # Responsiveness: RFQ issued -> quote received
    quoted_rfq_count: int
    avg_quote_response_days: Decimal | None
    # Price behaviour: PO line price vs the quote line it came from
    priced_line_count: int
    avg_price_variance_pct: Decimal | None


class SupplierActivity(BaseModel):
    supplier: SupplierRead
    purchase_orders: list[PoRead]
    quotes: list[SupplierQuoteActivity]
    totals: SupplierActivityTotals
    scorecard: SupplierScorecard


# --- Supplier-facing RFQ portal ---------------------------------------------


class RfqSendRequest(BaseModel):
    supplier_ids: list[uuid.UUID] = Field(min_length=1)
    expires_in_days: int = Field(default=21, ge=1, le=120)


class RfqInviteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: str | None = None
    expires_at: datetime
    sent_at: datetime | None
    opened_at: datetime | None
    responded_at: datetime | None
    status: str = "sent"


class RfqInviteCreated(RfqInviteRead):
    """The link is returned once here and cannot be recovered afterwards."""

    url: str


class SupplierRfqItem(BaseModel):
    id: uuid.UUID
    description: str
    unit: str
    quantity: Decimal


class SupplierRfqView(BaseModel):
    rfq_id: uuid.UUID
    doc_number: str
    title: str
    body: str | None
    due_date: date | None
    buyer_name: str
    supplier_name: str
    already_responded: bool
    items: list[SupplierRfqItem]


class SupplierQuoteLine(BaseModel):
    rfq_item_id: uuid.UUID
    quantity: Decimal | None = Field(default=None, gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)


class SupplierQuoteSubmit(BaseModel):
    items: list[SupplierQuoteLine] = Field(min_length=1)
    valid_until: date | None = None
    payment_terms: str | None = Field(default=None, max_length=255)
    delivery_terms: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class SupplierQuoteReceipt(BaseModel):
    quote_id: uuid.UUID
    doc_number: str
    total_amount: Decimal
    received_date: date
