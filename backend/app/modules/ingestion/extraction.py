"""Structured-output schema for the single classify+extract vision call."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

Confidence = Literal["high", "medium", "low"]


class StrField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str | None
    confidence: Confidence


class NumField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: float | None
    confidence: Confidence


class InvoiceLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str
    quantity: float | None
    unit_price: float | None
    amount: float | None


class InvoiceExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_name: StrField
    invoice_number: StrField
    invoice_date: StrField
    total_amount: NumField
    currency: StrField
    project_match: StrField
    lines: list[InvoiceLine]


class ReceiptExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vendor_name: StrField
    receipt_date: StrField
    total_amount: NumField
    currency: StrField
    category: StrField
    description: StrField
    project_match: StrField


class DeliveryLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str
    quantity: float | None
    unit: str | None


class DeliveryExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_name: StrField
    po_match: StrField
    delivery_date: StrField
    delivery_note_number: StrField
    lines: list[DeliveryLine]


class QuoteLineExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rfq_item_id: str | None
    description: str
    unit: str | None
    quantity: float
    unit_price: float
    match_confidence: Literal["exact", "probable", "unmatched"]


class QuoteFileExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rfq_match: StrField
    supplier_name: StrField
    valid_until: StrField
    payment_terms: StrField
    delivery_terms: StrField
    currency: StrField
    lines: list[QuoteLineExtraction]


class DocumentExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_type: Literal[
        "supplier_invoice", "expense_receipt", "delivery_note", "supplier_quote", "unknown"
    ]
    classification_confidence: Confidence
    summary: str
    invoice: InvoiceExtraction | None
    receipt: ReceiptExtraction | None
    delivery_note: DeliveryExtraction | None
    quote: QuoteFileExtraction | None
