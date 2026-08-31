"""Vendor compliance, and work let out in stages.

Two jobs that belong together because one gates the other: you should not be
able to award a package to a subcontractor whose insurance lapsed last month,
and the only way to enforce that is for the system to know when it lapses.

Compliance here is a date, not a tick. A tax clearance that was valid when the
vendor was approved and expired six months later is precisely what an audit
finds, and a "verified" checkbox would have said yes throughout.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.doc_numbers import next_doc_number
from app.common.enums import (
    ComplianceDocType,
    CostSource,
    JournalSource,
    MilestoneStatus,
    SubcontractStatus,
    VendorStatus,
)
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.procurement.models import Supplier
from app.modules.subcontracts.models import (
    ComplianceDocument,
    ComplianceRequirement,
    Subcontract,
    SubcontractMilestone,
)

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

# What this company asks for by default. Stored as rows so it can be changed
# without a deploy, but seeded so a fresh install is not silently demanding
# nothing.
DEFAULT_REQUIREMENTS: list[tuple[ComplianceDocType, bool, int]] = [
    (ComplianceDocType.company_registration, True, 30),
    (ComplianceDocType.tax_clearance, True, 30),
    (ComplianceDocType.public_liability, True, 30),
    (ComplianceDocType.workmans_compensation, True, 30),
    (ComplianceDocType.bank_confirmation, False, 30),
    (ComplianceDocType.safety_certificate, False, 30),
]


def ensure_requirements(db: Session) -> int:
    """Seeds the default list once. Additive: it fills an empty table rather
    than resetting a list somebody has since edited."""
    if db.scalar(select(ComplianceRequirement).limit(1)) is not None:
        return 0
    for doc_type, mandatory, warn in DEFAULT_REQUIREMENTS:
        db.add(
            ComplianceRequirement(
                doc_type=doc_type, is_mandatory=mandatory, warn_days=warn
            )
        )
    db.flush()
    return len(DEFAULT_REQUIREMENTS)


def compliance_status(db: Session, supplier_id: uuid.UUID, as_at: date | None = None) -> dict:
    """Where a supplier stands on paperwork, document by document.

    Each requirement resolves to one of four states, and they are deliberately
    distinct: `missing` means nobody ever supplied it, `expired` means they did
    and it lapsed. Those need different conversations.
    """
    ensure_requirements(db)
    as_at = as_at or date.today()
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise NotFoundError("Supplier not found")

    held = {}
    for doc in db.scalars(
        select(ComplianceDocument)
        .where(ComplianceDocument.supplier_id == supplier_id)
        .order_by(ComplianceDocument.expires_on.desc().nullsfirst())
    ):
        # Keep the best copy of each type: the one that expires latest, or a
        # non-expiring one. Re-uploading a renewed certificate should not leave
        # the old one deciding the answer.
        held.setdefault(doc.doc_type, doc)

    items = []
    blocking = []
    for requirement in db.scalars(select(ComplianceRequirement)):
        doc = held.get(requirement.doc_type)
        if doc is None:
            state, days = "missing", None
        elif doc.expires_on is None:
            state, days = "valid", None
        else:
            days = (doc.expires_on - as_at).days
            if days < 0:
                state = "expired"
            elif days <= requirement.warn_days:
                state = "expiring"
            else:
                state = "valid"

        items.append(
            {
                "doc_type": requirement.doc_type.value,
                "is_mandatory": requirement.is_mandatory,
                "state": state,
                "document_id": doc.id if doc else None,
                "reference": doc.reference if doc else None,
                "expires_on": doc.expires_on if doc else None,
                "days_to_expiry": days,
                "media_id": doc.media_id if doc else None,
            }
        )
        if requirement.is_mandatory and state in ("missing", "expired"):
            blocking.append(requirement.doc_type.value)

    return {
        "supplier_id": supplier_id,
        "supplier_name": supplier.name,
        "vendor_status": supplier.vendor_status.value,
        "is_compliant": not blocking,
        "blocking": blocking,
        "documents": items,
    }


def expiring_soon(db: Session, days: int = 30) -> list[dict]:
    """Everything about to lapse across every vendor, so it is chased before it
    stops a job rather than after."""
    ensure_requirements(db)
    today = date.today()
    rows = db.execute(
        select(ComplianceDocument, Supplier.name)
        .join(Supplier, Supplier.id == ComplianceDocument.supplier_id)
        .where(
            ComplianceDocument.expires_on.is_not(None),
            Supplier.is_active.is_(True),
        )
        .order_by(ComplianceDocument.expires_on)
    ).all()

    out = []
    for doc, supplier_name in rows:
        remaining = (doc.expires_on - today).days
        if remaining > days:
            continue
        out.append(
            {
                "supplier_id": doc.supplier_id,
                "supplier_name": supplier_name,
                "doc_type": doc.doc_type.value,
                "reference": doc.reference,
                "expires_on": doc.expires_on,
                "days_to_expiry": remaining,
                "state": "expired" if remaining < 0 else "expiring",
            }
        )
    return out


def set_vendor_status(db: Session, supplier_id: uuid.UUID, status: VendorStatus, user=None):
    """Approval is a decision about the relationship. It does not override the
    paperwork: an approved vendor with lapsed insurance is still blocked."""
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise NotFoundError("Supplier not found")
    supplier.vendor_status = status
    if status is VendorStatus.approved:
        supplier.approved_at = datetime.now(UTC)
        supplier.approved_by = getattr(user, "id", None)
    db.flush()
    return supplier


def require_tradeable(db: Session, supplier_id: uuid.UUID) -> None:
    """The gate. Refuses to let work be awarded to a vendor who is not approved
    or whose mandatory papers are missing or lapsed.

    This is where "prevents audit non-compliance" stops being a claim: the
    system will not create the commitment in the first place.
    """
    status = compliance_status(db, supplier_id)
    if status["vendor_status"] in ("suspended", "blacklisted"):
        raise ConflictError(
            f"{status['supplier_name']} is {status['vendor_status']} and cannot be awarded work"
        )
    if status["vendor_status"] == "pending":
        raise ConflictError(
            f"{status['supplier_name']} has not been approved as a vendor yet"
        )
    if status["blocking"]:
        readable = ", ".join(item.replace("_", " ") for item in status["blocking"])
        raise ConflictError(
            f"{status['supplier_name']} cannot be awarded work: {readable} missing or expired"
        )


# --- Subcontracts ------------------------------------------------------------


def get_subcontract(db: Session, subcontract_id: uuid.UUID) -> Subcontract:
    row = db.get(Subcontract, subcontract_id)
    if row is None:
        raise NotFoundError("Subcontract not found")
    return row


def create_subcontract(db: Session, project_id: uuid.UUID, data, user=None) -> Subcontract:
    from app.modules.projects.service import get_project

    get_project(db, project_id)
    if db.get(Supplier, data.supplier_id) is None:
        raise NotFoundError("Supplier not found")

    contract = Subcontract(
        doc_number=next_doc_number(db, Subcontract, "SC"),
        project_id=project_id,
        supplier_id=data.supplier_id,
        title=data.title,
        scope=data.scope,
        value=data.value or ZERO,
        retention_pct=data.retention_pct or ZERO,
        starts_on=data.starts_on,
        ends_on=data.ends_on,
        notes=data.notes,
        created_by=getattr(user, "id", None),
    )
    db.add(contract)
    db.flush()

    for index, milestone in enumerate(data.milestones or []):
        db.add(
            SubcontractMilestone(
                subcontract_id=contract.id,
                name=milestone.name,
                description=milestone.description,
                value=milestone.value,
                due_date=milestone.due_date,
                sort_order=index,
                created_by=getattr(user, "id", None),
            )
        )
    db.flush()
    _check_milestones_against_value(db, contract)
    return contract


def _check_milestones_against_value(db: Session, contract: Subcontract) -> None:
    """Milestones may not add up to more than the contract.

    Under is normal — not every package is fully staged up front. Over is
    always a mistake, and catching it here is cheaper than discovering it when
    the last stage cannot be paid.
    """
    total = db.scalar(
        select(func.coalesce(func.sum(SubcontractMilestone.value), 0)).where(
            SubcontractMilestone.subcontract_id == contract.id
        )
    ) or ZERO
    if Decimal(total) > Decimal(contract.value):
        raise ValidationFailedError(
            f"Milestones come to {Decimal(total)} against a contract of {Decimal(contract.value)}"
        )


def award(db: Session, subcontract_id: uuid.UUID, user=None) -> Subcontract:
    """Commits the package, once the vendor is actually allowed to have it."""
    contract = get_subcontract(db, subcontract_id)
    if contract.status is not SubcontractStatus.draft:
        raise ConflictError("Only a draft subcontract can be awarded")
    if not contract.milestones:
        raise ValidationFailedError(
            "A subcontract needs at least one milestone before it can be awarded"
        )
    require_tradeable(db, contract.supplier_id)

    contract.status = SubcontractStatus.awarded
    contract.awarded_at = datetime.now(UTC)
    contract.awarded_by = getattr(user, "id", None)
    db.flush()
    return contract


def submit_milestone(db: Session, milestone_id: uuid.UUID, user=None) -> SubcontractMilestone:
    """The subcontractor says a stage is done. It is a claim, not a payment."""
    milestone = _get_milestone(db, milestone_id)
    contract = get_subcontract(db, milestone.subcontract_id)
    if contract.status is not SubcontractStatus.awarded:
        raise ConflictError("This subcontract is not live")
    if milestone.status is MilestoneStatus.certified:
        raise ConflictError("That milestone has already been certified")

    milestone.status = MilestoneStatus.submitted
    milestone.submitted_at = datetime.now(UTC)
    db.flush()
    return milestone


def certify_milestone(db: Session, milestone_id: uuid.UUID, data, user=None):
    """Signs a stage off, books the cost, and holds the retention.

    Three entries in one act, which is the point: the job carries the full
    certified cost, the subcontractor is owed the net, and what is held back
    sits in Retention Payable where it can be seen and released later, rather
    than being quietly netted off and forgotten.
    """
    from app.modules.accounting import service as accounting
    from app.modules.accounting import subsidiary
    from app.modules.costs.models import CostEntry

    milestone = _get_milestone(db, milestone_id)
    contract = get_subcontract(db, milestone.subcontract_id)
    if contract.status is not SubcontractStatus.awarded:
        raise ConflictError("This subcontract is not live")
    if milestone.status is MilestoneStatus.certified:
        raise ConflictError("That milestone has already been certified")

    amount = Decimal(data.certified_amount if data.certified_amount is not None else milestone.value)
    if amount <= 0:
        raise ValidationFailedError("A certified milestone has to be worth something")
    if amount > Decimal(milestone.value):
        raise ValidationFailedError(
            f"{amount} is more than the {Decimal(milestone.value)} this stage was priced at"
        )

    retention = (amount * Decimal(contract.retention_pct) / 100).quantize(CENT)
    net = (amount - retention).quantize(CENT)

    milestone.status = MilestoneStatus.certified
    milestone.certified_amount = amount
    milestone.retention_held = retention
    milestone.certified_on = data.certified_on or date.today()
    milestone.certified_by = getattr(user, "id", None)

    entry = CostEntry(
        project_id=contract.project_id,
        entry_date=milestone.certified_on,
        description=f"{contract.doc_number} {milestone.name}",
        amount=amount,
        source=CostSource.manual,
        reference=contract.doc_number,
        created_by=getattr(user, "id", None),
    )
    db.add(entry)
    db.flush()
    milestone.cost_entry_id = entry.id

    # Posted here rather than through the usual auto-poster, because that one
    # credits a single account and this has to split the credit between what
    # the subcontractor is owed and what is being held back.
    accounting.ensure_chart(db)
    lines = [
        {
            "account_code": "5300",
            "debit": amount,
            "description": f"{contract.doc_number} {milestone.name}",
        },
        {
            "account_code": accounting.ACCOUNTS_PAYABLE,
            "credit": net,
            "subsidiary_id": subsidiary.pocket_for(db, "supplier", contract.supplier_id).id,
        },
    ]
    if retention > 0:
        lines.append({"account_code": accounting.RETENTION_PAYABLE, "credit": retention})

    journal = accounting.create_journal(
        db,
        journal_date=milestone.certified_on,
        memo=f"{contract.doc_number} {milestone.name} certified",
        # Tagged as the cost entry's journal so the unposted control sees it as
        # accounted for rather than reporting it as a gap.
        source=JournalSource.cost_entry,
        source_id=entry.id,
        project_id=contract.project_id,
        created_by=getattr(user, "id", None),
        lines=lines,
    )
    accounting.post(db, journal.id, user)

    _close_if_complete(db, contract)
    db.flush()
    return milestone


def reject_milestone(db: Session, milestone_id: uuid.UUID, reason: str, user=None):
    milestone = _get_milestone(db, milestone_id)
    if milestone.status is MilestoneStatus.certified:
        raise ConflictError("A certified milestone cannot be rejected; reverse it instead")
    milestone.status = MilestoneStatus.rejected
    milestone.rejection_reason = reason
    db.flush()
    return milestone


def _close_if_complete(db: Session, contract: Subcontract) -> None:
    outstanding = db.scalar(
        select(func.count())
        .select_from(SubcontractMilestone)
        .where(
            SubcontractMilestone.subcontract_id == contract.id,
            SubcontractMilestone.status != MilestoneStatus.certified,
        )
    )
    if not outstanding:
        contract.status = SubcontractStatus.completed


def _get_milestone(db: Session, milestone_id: uuid.UUID) -> SubcontractMilestone:
    milestone = db.get(SubcontractMilestone, milestone_id)
    if milestone is None:
        raise NotFoundError("Milestone not found")
    return milestone


def subcontract_summary(db: Session, subcontract_id: uuid.UUID) -> dict:
    """Where the package stands: priced, certified, held, and left to do."""
    contract = get_subcontract(db, subcontract_id)
    certified = ZERO
    retention = ZERO
    remaining = ZERO
    for milestone in contract.milestones:
        if milestone.status is MilestoneStatus.certified:
            certified += Decimal(milestone.certified_amount or 0)
            retention += Decimal(milestone.retention_held or 0)
        else:
            remaining += Decimal(milestone.value)
    return {
        "subcontract_id": contract.id,
        "doc_number": contract.doc_number,
        "value": Decimal(contract.value),
        "certified": certified.quantize(CENT),
        "retention_held": retention.quantize(CENT),
        "net_payable": (certified - retention).quantize(CENT),
        "remaining": remaining.quantize(CENT),
        "status": contract.status.value,
    }
