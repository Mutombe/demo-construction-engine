import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import BoqItemType, PoStatus, VariationStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.boq.models import BoqItem, BoqSection
from app.modules.boq.schemas import (
    BoqItemCreate,
    BoqItemRead,
    BoqItemUpdate,
    BoqSectionCreate,
    BoqSectionRead,
    BoqSectionUpdate,
    BoqSummary,
    BoqTree,
    CategoryTotal,
    SectionTotal,
    VariationDecision,
    VariationRegister,
    VariationRow,
)
from app.modules.costs import service as costs_service
from app.modules.costs.models import CostEntry
from app.modules.procurement.models import PoItem, PurchaseOrder
from app.modules.projects.service import get_project

ZERO = Decimal("0")


def _item_actuals(db: Session, project_id: uuid.UUID) -> dict[uuid.UUID, Decimal]:
    rows = db.execute(
        select(CostEntry.boq_item_id, func.sum(CostEntry.amount))
        .where(CostEntry.project_id == project_id, CostEntry.boq_item_id.is_not(None))
        .group_by(CostEntry.boq_item_id)
    ).all()
    return {item_id: total for item_id, total in rows}


def get_boq_tree(db: Session, project_id: uuid.UUID) -> BoqTree:
    get_project(db, project_id)
    sections = db.scalars(
        select(BoqSection)
        .where(BoqSection.project_id == project_id)
        .order_by(BoqSection.sort_order, BoqSection.code)
    ).all()
    actuals = _item_actuals(db, project_id)
    committed = costs_service.committed_by_boq_item(db, project_id)

    section_reads: list[BoqSectionRead] = []
    grand_total = ZERO
    for section in sections:
        item_reads = []
        subtotal = ZERO
        for item in section.items:
            read = BoqItemRead.model_validate(item)
            read.actual_total = actuals.get(item.id, ZERO)
            read.committed_total = committed.get(item.id, ZERO)
            item_reads.append(read)
            if item.item_type != BoqItemType.omission:
                subtotal += item.amount
        sr = BoqSectionRead.model_validate(section)
        sr.items = item_reads
        sr.subtotal = subtotal
        section_reads.append(sr)
        grand_total += subtotal
    return BoqTree(project_id=project_id, sections=section_reads, grand_total=grand_total)


# --- Sections --------------------------------------------------------------


def get_section(db: Session, section_id: uuid.UUID) -> BoqSection:
    section = db.get(BoqSection, section_id)
    if section is None:
        raise NotFoundError("BOQ section not found")
    return section


def create_section(
    db: Session, project_id: uuid.UUID, data: BoqSectionCreate, created_by: uuid.UUID
) -> BoqSection:
    get_project(db, project_id)
    if db.scalar(
        select(BoqSection).where(BoqSection.project_id == project_id, BoqSection.code == data.code)
    ):
        raise ConflictError(f"Section code {data.code} already exists in this project")
    if data.parent_id is not None:
        parent = get_section(db, data.parent_id)
        if parent.project_id != project_id:
            raise ValidationFailedError("Parent section belongs to another project")
    section = BoqSection(**data.model_dump(), project_id=project_id, created_by=created_by)
    db.add(section)
    db.flush()
    return section


def update_section(db: Session, section_id: uuid.UUID, data: BoqSectionUpdate) -> BoqSection:
    section = get_section(db, section_id)
    updates = data.model_dump(exclude_unset=True)
    if "code" in updates and updates["code"] != section.code:
        clash = db.scalar(
            select(BoqSection).where(
                BoqSection.project_id == section.project_id,
                BoqSection.code == updates["code"],
                BoqSection.id != section.id,
            )
        )
        if clash:
            raise ConflictError(f"Section code {updates['code']} already exists")
    if updates.get("parent_id") is not None:
        parent = get_section(db, updates["parent_id"])
        if parent.project_id != section.project_id:
            raise ValidationFailedError("Parent section belongs to another project")
        if parent.id == section.id:
            raise ValidationFailedError("A section cannot be its own parent")
    for field, value in updates.items():
        setattr(section, field, value)
    return section


def delete_section(db: Session, section_id: uuid.UUID) -> None:
    db.delete(get_section(db, section_id))


# --- Items -----------------------------------------------------------------


def get_item(db: Session, item_id: uuid.UUID) -> BoqItem:
    item = db.get(BoqItem, item_id)
    if item is None:
        raise NotFoundError("BOQ item not found")
    return item


def create_item(
    db: Session, section_id: uuid.UUID, data: BoqItemCreate, created_by: uuid.UUID
) -> BoqItem:
    section = get_section(db, section_id)
    if db.scalar(
        select(BoqItem).where(BoqItem.section_id == section_id, BoqItem.item_code == data.item_code)
    ):
        raise ConflictError(f"Item code {data.item_code} already exists in this section")
    item = BoqItem(
        **data.model_dump(),
        section_id=section_id,
        project_id=section.project_id,
        created_by=created_by,
    )
    db.add(item)
    db.flush()
    db.refresh(item)  # load the DB-generated amount
    return item


def update_item(db: Session, item_id: uuid.UUID, data: BoqItemUpdate) -> BoqItem:
    item = get_item(db, item_id)
    updates = data.model_dump(exclude_unset=True)
    if "item_code" in updates and updates["item_code"] != item.item_code:
        clash = db.scalar(
            select(BoqItem).where(
                BoqItem.section_id == item.section_id,
                BoqItem.item_code == updates["item_code"],
                BoqItem.id != item.id,
            )
        )
        if clash:
            raise ConflictError(f"Item code {updates['item_code']} already exists")
    for field, value in updates.items():
        setattr(item, field, value)
    db.flush()
    db.refresh(item)
    return item


def delete_item(db: Session, item_id: uuid.UUID) -> None:
    db.delete(get_item(db, item_id))


# --- Summary ---------------------------------------------------------------


def boq_summary(db: Session, project_id: uuid.UUID) -> BoqSummary:
    get_project(db, project_id)

    type_totals = dict(
        db.execute(
            select(BoqItem.item_type, func.coalesce(func.sum(BoqItem.amount), 0))
            .where(BoqItem.project_id == project_id)
            .group_by(BoqItem.item_type)
        ).all()
    )
    original = type_totals.get(BoqItemType.original, ZERO)
    variation = type_totals.get(BoqItemType.variation, ZERO)
    omission = type_totals.get(BoqItemType.omission, ZERO)

    actual_total = db.scalar(
        select(func.coalesce(func.sum(CostEntry.amount), 0)).where(
            CostEntry.project_id == project_id
        )
    )
    unallocated = db.scalar(
        select(func.coalesce(func.sum(CostEntry.amount), 0)).where(
            CostEntry.project_id == project_id, CostEntry.boq_item_id.is_(None)
        )
    )

    category_budget = dict(
        db.execute(
            select(BoqItem.cost_category, func.sum(BoqItem.amount))
            .where(
                BoqItem.project_id == project_id,
                BoqItem.item_type != BoqItemType.omission,
            )
            .group_by(BoqItem.cost_category)
        ).all()
    )
    category_committed = dict(
        db.execute(
            select(BoqItem.cost_category, func.sum(PoItem.amount))
            .join(PoItem, PoItem.boq_item_id == BoqItem.id)
            .join(PurchaseOrder, PoItem.po_id == PurchaseOrder.id)
            .where(
                PurchaseOrder.project_id == project_id,
                PurchaseOrder.status == PoStatus.issued,
            )
            .group_by(BoqItem.cost_category)
        ).all()
    )
    category_actual = dict(
        db.execute(
            select(BoqItem.cost_category, func.sum(CostEntry.amount))
            .join(BoqItem, BoqItem.id == CostEntry.boq_item_id)
            .where(CostEntry.project_id == project_id)
            .group_by(BoqItem.cost_category)
        ).all()
    )
    by_category = [
        CategoryTotal(
            cost_category=cat,
            budget=category_budget.get(cat, ZERO),
            actual=category_actual.get(cat, ZERO),
            committed=category_committed.get(cat, ZERO),
        )
        for cat in sorted(
            set(category_budget) | set(category_actual) | set(category_committed),
            key=lambda c: c.value,
        )
    ]

    section_rows = db.execute(
        select(
            BoqSection.id,
            BoqSection.code,
            BoqSection.title,
            func.coalesce(func.sum(BoqItem.amount), 0),
        )
        .outerjoin(
            BoqItem,
            (BoqItem.section_id == BoqSection.id) & (BoqItem.item_type != BoqItemType.omission),
        )
        .where(BoqSection.project_id == project_id)
        .group_by(BoqSection.id, BoqSection.code, BoqSection.title)
        .order_by(BoqSection.code)
    ).all()
    section_actual = dict(
        db.execute(
            select(BoqItem.section_id, func.sum(CostEntry.amount))
            .join(BoqItem, BoqItem.id == CostEntry.boq_item_id)
            .where(CostEntry.project_id == project_id)
            .group_by(BoqItem.section_id)
        ).all()
    )
    section_committed = dict(
        db.execute(
            select(BoqItem.section_id, func.sum(PoItem.amount))
            .join(PoItem, PoItem.boq_item_id == BoqItem.id)
            .join(PurchaseOrder, PoItem.po_id == PurchaseOrder.id)
            .where(
                PurchaseOrder.project_id == project_id,
                PurchaseOrder.status == PoStatus.issued,
            )
            .group_by(BoqItem.section_id)
        ).all()
    )
    by_section = [
        SectionTotal(
            section_id=sid,
            code=code,
            title=title,
            budget=budget,
            actual=section_actual.get(sid, ZERO),
            committed=section_committed.get(sid, ZERO),
        )
        for sid, code, title, budget in section_rows
    ]

    return BoqSummary(
        project_id=project_id,
        original_total=original,
        variation_total=variation,
        omission_total=omission,
        budget_total=original + variation,
        actual_total=actual_total,
        committed_total=costs_service.committed_total(db, project_id),
        unallocated_actual=unallocated,
        by_category=by_category,
        by_section=by_section,
    )


# --- Variation register -----------------------------------------------------


def variation_register(db: Session, project_id: uuid.UUID) -> VariationRegister:
    """Variations and omissions with their approval state and running totals."""
    from app.modules.valuations.service import effective_contract_value

    project = get_project(db, project_id)
    rows_raw = db.execute(
        select(BoqItem, BoqSection.code)
        .join(BoqSection, BoqSection.id == BoqItem.section_id)
        .where(
            BoqItem.project_id == project_id,
            BoqItem.item_type != BoqItemType.original,
        )
        .order_by(BoqItem.variation_ref, BoqSection.code, BoqItem.item_code)
    ).all()

    rows: list[VariationRow] = []
    totals = {
        (VariationStatus.approved, BoqItemType.variation): ZERO,
        (VariationStatus.approved, BoqItemType.omission): ZERO,
        (VariationStatus.proposed, BoqItemType.variation): ZERO,
        (VariationStatus.proposed, BoqItemType.omission): ZERO,
    }
    rejected = ZERO
    for item, section_code in rows_raw:
        read = VariationRow.model_validate(item)
        read.section_code = section_code
        rows.append(read)
        if item.variation_status == VariationStatus.rejected:
            rejected += item.amount
        else:
            totals[(item.variation_status, item.item_type)] += item.amount

    return VariationRegister(
        project_id=project_id,
        contract_value=project.contract_value,
        rows=rows,
        approved_additions=totals[(VariationStatus.approved, BoqItemType.variation)],
        approved_omissions=totals[(VariationStatus.approved, BoqItemType.omission)],
        proposed_additions=totals[(VariationStatus.proposed, BoqItemType.variation)],
        proposed_omissions=totals[(VariationStatus.proposed, BoqItemType.omission)],
        rejected_total=rejected,
        effective_contract_value=effective_contract_value(db, project),
    )


def decide_variation(
    db: Session, item_id: uuid.UUID, data: VariationDecision
) -> BoqItem:
    """Approve or reject a variation. Approving it makes the work certifiable."""
    item = get_item(db, item_id)
    if item.item_type == BoqItemType.original:
        raise ValidationFailedError(
            "Only variation and omission items have an approval state"
        )
    item.variation_status = data.status
    item.variation_approved_date = (
        (data.approved_date or date.today())
        if data.status == VariationStatus.approved
        else None
    )
    db.flush()
    return item
