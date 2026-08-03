import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import CostSource


class CostEntryBase(BaseModel):
    boq_item_id: uuid.UUID | None = None
    entry_date: date
    description: str | None = None
    amount: Decimal
    quantity: Decimal | None = Field(default=None, ge=0)
    reference: str | None = Field(default=None, max_length=60)


class CostEntryCreate(CostEntryBase):
    pass


class CostEntryUpdate(BaseModel):
    boq_item_id: uuid.UUID | None = None
    entry_date: date | None = None
    description: str | None = None
    amount: Decimal | None = None
    quantity: Decimal | None = Field(default=None, ge=0)
    reference: str | None = Field(default=None, max_length=60)


class CostEntryRead(CostEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    source: CostSource
    created_at: datetime
    boq_item_code: str | None = None
    boq_item_description: str | None = None
