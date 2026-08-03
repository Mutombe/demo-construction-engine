import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import ProjectStatus, ValuationStatus, WorkStatus

# --- Staff-side link management ---------------------------------------------


class PortalLinkCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    expires_in_days: int = Field(default=90, ge=1, le=365)


class PortalLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    label: str
    expires_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class PortalLinkCreated(PortalLinkRead):
    """Returned exactly once, at creation — the only time the raw token exists."""

    token: str
    url: str


# --- Portal (client-facing) --------------------------------------------------


class PortalProjectSummary(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    status: ProjectStatus
    city: str | None
    planned_start: date | None
    planned_end: date | None
    contract_value: Decimal | None
    progress_pct: float


class PortalSummary(BaseModel):
    client_name: str
    company_name: str
    projects: list[PortalProjectSummary]


class PortalPhase(BaseModel):
    name: str
    sequence: int
    status: WorkStatus
    planned_start: date | None
    planned_end: date | None


class PortalProjectDetail(PortalProjectSummary):
    description: str | None
    site_address: str | None
    actual_start: date | None
    phases: list[PortalPhase]


class PortalValuation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doc_number: str
    valuation_number: int
    status: ValuationStatus
    period_end: date
    gross_valuation: Decimal
    retention_amount: Decimal
    net_certified: Decimal
    issued_date: date | None
    paid_date: date | None
