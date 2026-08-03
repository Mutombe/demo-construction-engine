import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import ExpenseCategory, ExpenseStatus


class ExpenseClaimBase(BaseModel):
    category: ExpenseCategory
    expense_date: date
    amount: Decimal = Field(gt=0)
    description: str = Field(min_length=1)
    receipt_ref: str | None = Field(default=None, max_length=60)
    boq_item_id: uuid.UUID | None = None


class ExpenseClaimCreate(ExpenseClaimBase):
    pass


class ExpenseClaimUpdate(BaseModel):
    category: ExpenseCategory | None = None
    expense_date: date | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, min_length=1)
    receipt_ref: str | None = Field(default=None, max_length=60)
    boq_item_id: uuid.UUID | None = None


class ExpenseClaimReject(BaseModel):
    reason: str = Field(min_length=1)


class ExpenseClaimRead(ExpenseClaimBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    doc_number: str
    status: ExpenseStatus
    created_by: uuid.UUID | None
    claimant_name: str | None = None
    project_name: str | None = None
    project_code: str | None = None
    approved_by: uuid.UUID | None
    approver_name: str | None = None
    decided_at: datetime | None
    rejection_reason: str | None
    cost_entry_id: uuid.UUID | None
    created_at: datetime
