import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# --- Embedded action: RFQ generation ---------------------------------------


class RfqGenerateRequest(BaseModel):
    project_id: uuid.UUID
    boq_item_ids: list[uuid.UUID] = Field(min_length=1)
    title: str | None = None
    instructions: str | None = None


class RfqDraftItem(BaseModel):
    boq_item_id: uuid.UUID
    item_code: str
    description: str
    unit: str
    quantity: Decimal


class RfqDraft(BaseModel):
    title: str
    body: str
    items: list[RfqDraftItem]


# --- Embedded action: quote extraction (structured output) ------------------


class ExtractedLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rfq_item_id: str | None
    description: str
    unit: str | None
    quantity: float
    unit_price: float
    match_confidence: Literal["exact", "probable", "unmatched"]


class QuoteExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_name: str | None
    currency: str | None
    payment_terms: str | None
    delivery_terms: str | None
    valid_until: str | None
    lines: list[ExtractedLine]
    notes: str | None


class QuoteExtractRequest(BaseModel):
    raw_text: str = Field(min_length=10)


class ExtractedLineOut(BaseModel):
    rfq_item_id: uuid.UUID | None
    description: str
    unit: str | None
    quantity: Decimal
    unit_price: Decimal
    match_confidence: Literal["exact", "probable", "unmatched"]
    unit_mismatch: bool = False
    quantity_mismatch: bool = False


class QuoteExtractionOut(BaseModel):
    supplier_name: str | None
    currency: str | None
    currency_warning: bool = False
    payment_terms: str | None
    delivery_terms: str | None
    valid_until: str | None
    lines: list[ExtractedLineOut]
    notes: str | None


# --- Embedded action: comparison (structured output) ------------------------


class LineFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rfq_item_id: str | None
    note: str


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: str
    supplier_name: str
    reasoning: str


class QuoteComparisonAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    line_analysis: list[LineFinding]
    risk_flags: list[str]
    recommendation: Recommendation


class MatrixCell(BaseModel):
    quote_item_id: uuid.UUID | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    unit_mismatch: bool = False
    quantity_mismatch: bool = False
    is_cheapest: bool = False


class MatrixRow(BaseModel):
    rfq_item_id: uuid.UUID
    description: str
    unit: str
    quantity: Decimal
    cells: dict[str, MatrixCell]  # keyed by quote id (str)


class MatrixSupplier(BaseModel):
    quote_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: str
    status: str
    total_amount: Decimal
    comparable_total: Decimal  # sum over lines every compared supplier quoted
    coverage_pct: float
    cheapest_line_count: int
    payment_terms: str | None
    delivery_terms: str | None
    valid_until: str | None


class ComparisonMatrix(BaseModel):
    rfq_id: uuid.UUID
    suppliers: list[MatrixSupplier]
    rows: list[MatrixRow]


class QuoteComparisonResponse(BaseModel):
    matrix: ComparisonMatrix
    analysis: QuoteComparisonAnalysis | None = None


# --- Embedded action: PO terms ----------------------------------------------


class PoTermsRequest(BaseModel):
    quote_id: uuid.UUID


class PoTermsDraft(BaseModel):
    terms: str
    notes: str


# --- Weekly site report -----------------------------------------------------


class WeeklyReportRequest(BaseModel):
    project_id: uuid.UUID
    week_start: date
    week_end: date | None = None  # defaults to week_start + 6 days


class WeeklyReportDraft(BaseModel):
    project_id: uuid.UUID
    period_start: date
    period_end: date
    markdown: str


# --- Chat -------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=60)
    project_id: uuid.UUID | None = None


class AiStatus(BaseModel):
    available: bool
