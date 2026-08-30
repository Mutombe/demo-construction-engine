import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import (
    ComplianceDocType,
    MilestoneStatus,
    SubcontractStatus,
    VendorStatus,
)


class ComplianceDocumentCreate(BaseModel):
    doc_type: ComplianceDocType
    reference: str | None = Field(default=None, max_length=80)
    issued_on: date | None = None
    # Null means it does not expire, such as a company registration.
    expires_on: date | None = None
    media_id: uuid.UUID | None = None
    notes: str | None = None


class ComplianceDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    supplier_id: uuid.UUID
    doc_type: ComplianceDocType
    reference: str | None
    issued_on: date | None
    expires_on: date | None
    media_id: uuid.UUID | None
    notes: str | None


class RequirementUpdate(BaseModel):
    doc_type: ComplianceDocType
    is_mandatory: bool
    warn_days: int = Field(default=30, ge=0, le=365)


class VendorStatusUpdate(BaseModel):
    vendor_status: VendorStatus


class MilestoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    value: Decimal = Field(gt=0)
    due_date: date | None = None


class SubcontractCreate(BaseModel):
    supplier_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    scope: str | None = None
    value: Decimal = Field(default=Decimal("0"), ge=0)
    retention_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    starts_on: date | None = None
    ends_on: date | None = None
    notes: str | None = None
    milestones: list[MilestoneCreate] = []


class MilestoneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subcontract_id: uuid.UUID
    name: str
    description: str | None
    value: Decimal
    due_date: date | None
    status: MilestoneStatus
    submitted_at: datetime | None
    certified_amount: Decimal | None
    retention_held: Decimal | None
    certified_on: date | None
    rejection_reason: str | None


class SubcontractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doc_number: str
    project_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: str | None = None
    title: str
    scope: str | None
    value: Decimal
    retention_pct: Decimal
    status: SubcontractStatus
    starts_on: date | None
    ends_on: date | None
    awarded_at: datetime | None


class SubcontractDetail(SubcontractRead):
    milestones: list[MilestoneRead] = []
    certified: Decimal = Decimal("0")
    retention_held: Decimal = Decimal("0")
    net_payable: Decimal = Decimal("0")
    remaining: Decimal = Decimal("0")


class CertifyRequest(BaseModel):
    # Omit to certify the stage at the price it was set at.
    certified_amount: Decimal | None = Field(default=None, gt=0)
    certified_on: date | None = None
    notes: str | None = None


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1)
