import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import BoqItemType, CostCategory, VariationStatus


class BoqItemBase(BaseModel):
    item_code: str = Field(min_length=1, max_length=30)
    description: str = Field(min_length=1)
    unit: str = Field(min_length=1, max_length=10)
    quantity: Decimal = Field(default=Decimal("0"), ge=0)
    rate: Decimal = Field(default=Decimal("0"), ge=0)
    cost_category: CostCategory = CostCategory.material
    item_type: BoqItemType = BoqItemType.original
    variation_ref: str | None = Field(default=None, max_length=30)
    variation_status: VariationStatus = VariationStatus.proposed
    sort_order: int = 0


class BoqItemCreate(BoqItemBase):
    pass


class BoqItemUpdate(BaseModel):
    item_code: str | None = Field(default=None, min_length=1, max_length=30)
    description: str | None = Field(default=None, min_length=1)
    unit: str | None = Field(default=None, min_length=1, max_length=10)
    quantity: Decimal | None = Field(default=None, ge=0)
    rate: Decimal | None = Field(default=None, ge=0)
    cost_category: CostCategory | None = None
    item_type: BoqItemType | None = None
    variation_ref: str | None = Field(default=None, max_length=30)
    variation_status: VariationStatus | None = None
    sort_order: int | None = None


class BoqItemRead(BoqItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    section_id: uuid.UUID
    project_id: uuid.UUID
    amount: Decimal
    actual_total: Decimal = Decimal("0")  # filled by service from cost_entries
    committed_total: Decimal = Decimal("0")  # issued POs not yet received


class BoqSectionBase(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=200)
    parent_id: uuid.UUID | None = None
    sort_order: int = 0


class BoqSectionCreate(BoqSectionBase):
    pass


class BoqSectionUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=20)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: uuid.UUID | None = None
    sort_order: int | None = None


class BoqSectionRead(BoqSectionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    items: list[BoqItemRead] = []
    subtotal: Decimal = Decimal("0")


class BoqTree(BaseModel):
    project_id: uuid.UUID
    sections: list[BoqSectionRead]
    grand_total: Decimal


class CategoryTotal(BaseModel):
    cost_category: CostCategory
    budget: Decimal
    actual: Decimal
    committed: Decimal = Decimal("0")


class SectionTotal(BaseModel):
    section_id: uuid.UUID
    code: str
    title: str
    budget: Decimal
    actual: Decimal
    committed: Decimal = Decimal("0")


class BoqSummary(BaseModel):
    project_id: uuid.UUID
    original_total: Decimal
    variation_total: Decimal
    omission_total: Decimal
    budget_total: Decimal  # original + variation (omissions excluded)
    actual_total: Decimal
    committed_total: Decimal = Decimal("0")
    unallocated_actual: Decimal
    by_category: list[CategoryTotal]
    by_section: list[SectionTotal]


class VariationDecision(BaseModel):
    status: VariationStatus
    approved_date: date | None = None


class VariationRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    section_code: str | None = None
    item_code: str
    description: str
    unit: str
    quantity: Decimal
    rate: Decimal
    amount: Decimal
    item_type: BoqItemType
    variation_ref: str | None
    variation_status: VariationStatus
    variation_approved_date: date | None


class VariationRegister(BaseModel):
    """Every variation and omission on a project with its approval state.

    Only the approved totals move the certifiable contract value; proposed
    work is visible but not yet money.
    """

    project_id: uuid.UUID
    contract_value: Decimal | None
    rows: list[VariationRow]
    approved_additions: Decimal
    approved_omissions: Decimal
    proposed_additions: Decimal
    proposed_omissions: Decimal
    rejected_total: Decimal
    effective_contract_value: Decimal | None
