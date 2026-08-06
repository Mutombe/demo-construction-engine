"""Cost value reconciliation.

The report a contractor runs to find out whether a job is actually making
money, rather than whether it has been billed. Two numbers that people
routinely confuse:

    value   what has been certified — what the client agrees is owed
    cost    what the job has actually consumed

Margin is the gap. The trap the report exists to catch is a job that looks
healthy because it has been billed ahead of the work: cash is fine, the
margin is imaginary, and it reverses the moment the certificate catches up.

Everything here is measured, not estimated. Where a real CVR would carry a
surveyor's forecast of final cost, this carries cost to date plus what has
been committed, and says so — a forecast nobody entered is not a forecast,
and inventing one would make the most important column on the page fiction.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import BoqItemType, CostCategory, PoStatus, ValuationStatus
from app.core.exceptions import NotFoundError
from app.modules.boq.models import BoqItem
from app.modules.costs.models import CostEntry
from app.modules.procurement.models import PurchaseOrder
from app.modules.projects.models import Project
from app.modules.valuations.models import Valuation

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

CATEGORY_LABELS = {
    CostCategory.material: "Materials",
    CostCategory.labour: "Labour",
    CostCategory.plant: "Plant",
    CostCategory.subcontract: "Subcontract",
    CostCategory.preliminaries: "Preliminaries",
    CostCategory.other: "Other",
}


def cost_value_reconciliation(db: Session, project_id: uuid.UUID) -> dict:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError("Project not found")

    budget = _budget_by_category(db, project_id)
    cost = _cost_by_category(db, project_id)
    committed = _committed_by_category(db, project_id)

    categories = sorted(set(budget) | set(cost) | set(committed), key=lambda c: c.value)
    rows = []
    for category in categories:
        budget_amount = budget.get(category, ZERO)
        cost_amount = cost.get(category, ZERO)
        committed_amount = committed.get(category, ZERO)
        # What the job is known to be heading for: spent, plus ordered and not
        # yet delivered. It excludes work nobody has ordered.
        expected = (cost_amount + committed_amount).quantize(CENT)
        rows.append(
            {
                "category": category.value,
                "label": CATEGORY_LABELS.get(category, category.value.title()),
                "budget": budget_amount,
                "cost_to_date": cost_amount,
                "committed": committed_amount,
                "known_cost": expected,
                "variance": (budget_amount - expected).quantize(CENT),
                "spent_pct": _pct(cost_amount, budget_amount),
            }
        )

    certified = _certified_to_date(db, project_id)
    cost_total = sum((r["cost_to_date"] for r in rows), ZERO).quantize(CENT)
    committed_total = sum((r["committed"] for r in rows), ZERO).quantize(CENT)
    budget_total = sum((r["budget"] for r in rows), ZERO).quantize(CENT)
    known_total = (cost_total + committed_total).quantize(CENT)

    margin = (certified - cost_total).quantize(CENT)
    contract = _effective_contract_value(db, project)
    forecast_margin = (contract - known_total).quantize(CENT)

    return {
        "project_id": project.id,
        "project_code": project.code,
        "project_name": project.name,
        "as_at": date.today(),
        "contract_value": contract,
        "budget_total": budget_total,
        "certified_to_date": certified,
        "cost_to_date": cost_total,
        "committed": committed_total,
        "known_cost": known_total,
        "margin_to_date": margin,
        "margin_pct": _pct(margin, certified),
        "forecast_margin": forecast_margin,
        "forecast_margin_pct": _pct(forecast_margin, contract),
        "rows": rows,
        **_billing_position(db, project_id, certified, cost_total, contract),
    }


def _billing_position(
    db: Session,
    project_id: uuid.UUID,
    certified: Decimal,
    cost: Decimal,
    contract: Decimal,
) -> dict:
    """Whether the job has been billed ahead of the work, or behind it.

    Earned value is the share of the contract the spend implies has been done.
    Certified above that is money taken early: the cash is real, the margin is
    not, and it unwinds as the work catches up. Certified below it is work done
    and not yet billed, which is the opposite problem and just as worth seeing.
    """
    budget = db.scalar(
        select(func.coalesce(func.sum(BoqItem.amount), 0)).where(
            BoqItem.project_id == project_id
        )
    ) or ZERO
    budget = Decimal(budget).quantize(CENT)
    if budget <= 0 or contract <= 0:
        return {
            "earned_value": ZERO,
            "billing_position": ZERO,
            "billing_status": "unknown",
        }

    progress = min(cost / budget, Decimal("1")) if budget else ZERO
    earned = (contract * progress).quantize(CENT)
    position = (certified - earned).quantize(CENT)
    if position > 0:
        status = "over_billed"
    elif position < 0:
        status = "under_billed"
    else:
        status = "in_line"
    return {
        "earned_value": earned,
        "billing_position": position,
        "billing_status": status,
    }


def _budget_by_category(db: Session, project_id: uuid.UUID) -> dict:
    rows = db.execute(
        select(BoqItem.cost_category, func.coalesce(func.sum(BoqItem.amount), 0))
        .where(
            BoqItem.project_id == project_id,
            # Omissions reduce the job rather than being something to spend.
            BoqItem.item_type != BoqItemType.omission,
        )
        .group_by(BoqItem.cost_category)
    ).all()
    return {row[0]: Decimal(row[1]).quantize(CENT) for row in rows}


def _cost_by_category(db: Session, project_id: uuid.UUID) -> dict:
    """Costs booked to a BOQ line carry that line's category; the rest land in
    Other, because guessing which trade an unbooked cost belongs to is how a
    CVR stops being evidence."""
    # Grouped on the raw column and the null folded in Python: coalescing a
    # native enum against a string literal is a type mismatch in Postgres, and
    # casting round it is more noise than the fold is worth.
    rows = db.execute(
        select(BoqItem.cost_category, func.coalesce(func.sum(CostEntry.amount), 0))
        .select_from(CostEntry)
        .join(BoqItem, BoqItem.id == CostEntry.boq_item_id, isouter=True)
        .where(CostEntry.project_id == project_id)
        .group_by(BoqItem.cost_category)
    ).all()
    return _fold_unbooked(rows)


def _committed_by_category(db: Session, project_id: uuid.UUID) -> dict:
    """Only issued orders. A draft is not a commitment, and a received one is
    already in the cost — counting either would double it."""
    from app.modules.procurement.models import PoItem

    rows = db.execute(
        select(
            BoqItem.cost_category,
            func.coalesce(func.sum(PoItem.quantity * PoItem.unit_price), 0),
        )
        .select_from(PoItem)
        .join(PurchaseOrder, PurchaseOrder.id == PoItem.po_id)
        .join(BoqItem, BoqItem.id == PoItem.boq_item_id, isouter=True)
        .where(
            PurchaseOrder.project_id == project_id,
            PurchaseOrder.status == PoStatus.issued,
        )
        .group_by(BoqItem.cost_category)
    ).all()
    return _fold_unbooked(rows)


def _fold_unbooked(rows) -> dict:
    """Anything with no BOQ line lands in Other rather than being guessed at."""
    totals: dict[CostCategory, Decimal] = {}
    for category, amount in rows:
        key = category or CostCategory.other
        totals[key] = (totals.get(key, ZERO) + Decimal(amount)).quantize(CENT)
    return totals


def _certified_to_date(db: Session, project_id: uuid.UUID) -> Decimal:
    """The latest certificate's cumulative gross, not the sum of them: gross
    is already cumulative, so adding them up counts the early work again."""
    latest = db.scalar(
        select(Valuation)
        .where(
            Valuation.project_id == project_id,
            Valuation.status.in_((ValuationStatus.issued, ValuationStatus.paid)),
        )
        .order_by(Valuation.valuation_number.desc())
    )
    return Decimal(latest.gross_valuation).quantize(CENT) if latest else ZERO


def _effective_contract_value(db: Session, project: Project) -> Decimal:
    """Contract plus approved variations less approved omissions — the ceiling
    the job can actually certify to."""
    rows = db.execute(
        select(BoqItem.item_type, func.coalesce(func.sum(BoqItem.amount), 0))
        .where(
            BoqItem.project_id == project.id,
            BoqItem.item_type != BoqItemType.original,
            BoqItem.variation_status == "approved",
        )
        .group_by(BoqItem.item_type)
    ).all()
    totals = {row[0]: Decimal(row[1]) for row in rows}
    base = Decimal(project.contract_value or 0)
    return (
        base
        + totals.get(BoqItemType.variation, ZERO)
        - totals.get(BoqItemType.omission, ZERO)
    ).quantize(CENT)


def _pct(part: Decimal, whole: Decimal) -> Decimal | None:
    """None rather than zero when there is nothing to divide by: 0% and "no
    basis to say" are different answers."""
    if not whole:
        return None
    return ((part / whole) * 100).quantize(Decimal("0.1"))


def portfolio(db: Session) -> list[dict]:
    """Every live job on one page, worst margin first."""
    from app.common.enums import ProjectStatus

    # Everything that has not finished, rather than only what is on site: a
    # job still in planning can already carry committed cost, and leaving it
    # off the page is how that gets missed.
    projects = db.scalars(
        select(Project).where(
            Project.status.notin_((ProjectStatus.completed, ProjectStatus.cancelled))
        )
    )
    rows = [cost_value_reconciliation(db, project.id) for project in projects]
    return sorted(rows, key=lambda r: (r["margin_pct"] is None, r["margin_pct"] or 0))
