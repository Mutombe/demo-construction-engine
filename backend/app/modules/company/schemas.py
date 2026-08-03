import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CompanySettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    currency: str
    vat_rate_pct: Decimal
    fiscal_year_start_month: int
    default_retention_pct: Decimal


class CompanySettingsUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    vat_rate_pct: Decimal | None = Field(default=None, ge=0, le=100)
    fiscal_year_start_month: int | None = Field(default=None, ge=1, le=12)
    default_retention_pct: Decimal | None = Field(default=None, ge=0, le=100)
