"""The commercial side of a subcontract: what changed, what was deducted.

Certifying a stage says what the subcontractor earned. It says nothing about
the three things that decide what they are actually paid, and every one of
them is a conversation somebody has every month:

    variations     work instructed beyond the original scope
    back-charges   their work somebody else had to put right
    withholding    tax deducted at source and owed to the revenue authority

Each is a document rather than an adjustment to a number. A subcontractor
asking "why is this less than I claimed" needs an answer with a reference on
it, and a value that was quietly edited cannot provide one.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.doc_numbers import next_doc_number
from app.common.enums import JournalSource, SubcontractStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.subcontracts.models import BackCharge, SubcontractVariation
from app.modules.subcontracts.service import (
    get_subcontract,
    subcontract_summary,
)

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


# --- Variations --------------------------------------------------------------


def create_variation(db: Session, subcontract_id: uuid.UUID, data, user=None):
    """Instructed work, priced, and not yet part of the package.

    It does not move the contract value until somebody approves it. An
    instruction given on site is a claim until the person carrying the cost
    agrees it, and treating those as the same thing is how a package quietly
    grows by a third.
    """
    contract = get_subcontract(db, subcontract_id)
    if contract.status is SubcontractStatus.draft:
        raise ConflictError("Award the package before instructing variations against it")
    if Decimal(data.amount) == 0:
        raise ValidationFailedError("A variation has to change the value by something")

    variation = SubcontractVariation(
        subcontract_id=contract.id,
        doc_number=next_doc_number(db, SubcontractVariation, "SCV"),
        title=data.title,
        description=data.description,
        amount=Decimal(data.amount),
        instructed_on=data.instructed_on or date.today(),
        instructed_by=data.instructed_by,
        created_by=getattr(user, "id", None),
    )
    db.add(variation)
    db.flush()
    return variation


def approve_variation(db: Session, variation_id: uuid.UUID, user=None):
    """Agreeing it is what moves the package value."""
    variation = db.get(SubcontractVariation, variation_id)
    if variation is None:
        raise NotFoundError("Variation not found")
    if variation.status == "approved":
        raise ConflictError("That variation has already been approved")

    contract = get_subcontract(db, variation.subcontract_id)
    new_value = Decimal(contract.value) + Decimal(variation.amount)
    if new_value < 0:
        raise ValidationFailedError(
            "That omission is worth more than the package it is being taken from"
        )

    variation.status = "approved"
    variation.approved_at = datetime.now(timezone.utc)
    variation.approved_by = getattr(user, "id", None)
    contract.value = new_value
    db.flush()
    return variation


def reject_variation(db: Session, variation_id: uuid.UUID, user=None):
    variation = db.get(SubcontractVariation, variation_id)
    if variation is None:
        raise NotFoundError("Variation not found")
    if variation.status == "approved":
        raise ConflictError(
            "An approved variation is already in the package value. Omit it with a "
            "negative variation rather than deleting the history of it."
        )
    variation.status = "rejected"
    db.flush()
    return variation


def list_variations(db: Session, subcontract_id: uuid.UUID):
    return list(
        db.scalars(
            select(SubcontractVariation)
            .where(SubcontractVariation.subcontract_id == subcontract_id)
            .order_by(SubcontractVariation.instructed_on.desc())
        )
    )


def approved_variation_total(db: Session, subcontract_id: uuid.UUID) -> Decimal:
    return sum(
        (
            Decimal(v.amount)
            for v in list_variations(db, subcontract_id)
            if v.status == "approved"
        ),
        ZERO,
    )


# --- Back-charges ------------------------------------------------------------


def raise_back_charge(db: Session, subcontract_id: uuid.UUID, data, user=None):
    """Recover from a subcontractor the cost of putting their work right.

    Posted when it is raised, not when it comes off a payment: the money is
    owed from the moment somebody else had to do the work. What is uncertain
    is when it is recovered, never whether it is due.

    It credits the job rather than creating income. The remedial work is
    already sitting on the job as a cost; recovering it takes that cost back
    off. Nothing was earned here.
    """
    from app.modules.accounting import service as accounting
    from app.modules.accounting import subsidiary

    contract = get_subcontract(db, subcontract_id)
    amount = Decimal(data.amount)
    if amount <= 0:
        raise ValidationFailedError("A back-charge has to be worth something")

    charge = BackCharge(
        subcontract_id=contract.id,
        doc_number=next_doc_number(db, BackCharge, "BC"),
        reason=data.reason,
        amount=amount,
        raised_on=data.raised_on or date.today(),
        created_by=getattr(user, "id", None),
    )
    db.add(charge)
    db.flush()

    # A negative cost entry, so the job's own figures move too. Posting only a
    # journal would take the cost off the ledger and leave the project screen
    # still showing money the job got back, which is where anyone actually
    # looks.
    from app.common.enums import CostSource
    from app.modules.costs.models import CostEntry

    entry = CostEntry(
        project_id=contract.project_id,
        entry_date=charge.raised_on,
        description=f"{charge.doc_number} back-charge: {str(data.reason)[:150]}",
        amount=-amount,
        source=CostSource.manual,
        reference=charge.doc_number,
        created_by=getattr(user, "id", None),
    )
    db.add(entry)
    db.flush()

    accounting.ensure_chart(db)
    journal = accounting.create_journal(
        db,
        journal_date=charge.raised_on,
        memo=f"{charge.doc_number} back-charge to {contract.doc_number}",
        # Tagged to the cost entry so the unposted control counts it as
        # accounted for rather than reporting it as a gap.
        source=JournalSource.cost_entry,
        source_id=entry.id,
        project_id=contract.project_id,
        created_by=getattr(user, "id", None),
        lines=[
            {
                "account_code": accounting.ACCOUNTS_PAYABLE,
                "debit": amount,
                "subsidiary_id": subsidiary.pocket_for(db, "supplier", contract.supplier_id).id,
            },
            {
                "account_code": "5300",
                "credit": amount,
                "description": str(data.reason)[:200],
            },
        ],
    )
    accounting.post(db, journal.id, user)
    charge.journal_id = journal.id
    charge.recovered_at = datetime.now(timezone.utc)
    db.flush()
    return charge


def list_back_charges(db: Session, subcontract_id: uuid.UUID):
    return list(
        db.scalars(
            select(BackCharge)
            .where(BackCharge.subcontract_id == subcontract_id)
            .order_by(BackCharge.raised_on.desc())
        )
    )


def back_charge_total(db: Session, subcontract_id: uuid.UUID) -> Decimal:
    return sum(
        (Decimal(c.amount) for c in list_back_charges(db, subcontract_id)), ZERO
    )


# --- Withholding tax ---------------------------------------------------------


def apply_withholding(db: Session, subcontract_id: uuid.UUID, data, user=None):
    """Withhold tax from what the subcontractor is owed.

    This is not a saving. It moves money from what we owe the subcontractor to
    what we owe the revenue authority, and it stays owed until it is remitted.
    Anything that books it as other than a liability is how a company ends up
    spending money it was only holding.
    """
    from app.modules.accounting import service as accounting
    from app.modules.accounting import subsidiary

    contract = get_subcontract(db, subcontract_id)
    rate = Decimal(contract.withholding_pct or 0)
    if rate <= 0:
        raise ConflictError(
            f"{contract.doc_number} withholds at zero. A subcontractor holding a valid tax "
            "clearance is withheld at nothing, but that is a decision to record on the "
            "package rather than one to assume here."
        )

    if data.amount is not None:
        base = Decimal(data.amount)
    else:
        summary = subcontract_summary(db, subcontract_id)
        base = Decimal(summary["net_payable"])
    if base <= 0:
        raise ConflictError("There is nothing owed to withhold from")

    amount = (base * rate / 100).quantize(CENT)
    accounting.ensure_chart(db)
    journal = accounting.create_journal(
        db,
        journal_date=data.withheld_on or date.today(),
        memo=f"{contract.doc_number} withholding tax at {rate}%",
        source=JournalSource.manual,
        project_id=contract.project_id,
        created_by=getattr(user, "id", None),
        lines=[
            {
                "account_code": accounting.ACCOUNTS_PAYABLE,
                "debit": amount,
                "subsidiary_id": subsidiary.pocket_for(db, "supplier", contract.supplier_id).id,
            },
            {"account_code": accounting.WITHHOLDING_TAX_PAYABLE, "credit": amount},
        ],
    )
    accounting.post(db, journal.id, user)
    db.flush()
    return {
        "subcontract_id": contract.id,
        "doc_number": contract.doc_number,
        "rate_pct": rate,
        "base": base.quantize(CENT),
        "withheld": amount,
        "journal_id": journal.id,
    }


# --- The payment certificate -------------------------------------------------


def payment_certificate(db: Session, subcontract_id: uuid.UUID) -> dict:
    """What the subcontractor will actually be paid, and why it is less than
    what they claimed.

    Every line that reduces the figure is shown and named. A subcontractor
    paid a number they cannot reconstruct rings up every single month, and
    they are right to.
    """
    contract = get_subcontract(db, subcontract_id)
    summary = subcontract_summary(db, subcontract_id)

    certified = Decimal(summary["certified"])
    retention = Decimal(summary["retention_outstanding"])
    back_charged = back_charge_total(db, subcontract_id)
    variations = approved_variation_total(db, subcontract_id)

    rate = Decimal(contract.withholding_pct or 0)
    after_retention = certified - retention
    withheld = (after_retention * rate / 100).quantize(CENT) if rate > 0 else ZERO

    return {
        "subcontract_id": contract.id,
        "doc_number": contract.doc_number,
        "title": contract.title,
        "supplier_name": contract.supplier.name if contract.supplier else None,
        "project_id": contract.project_id,
        # The original is derived, not stored: the contract value moves as
        # variations are approved, and the two have to agree by construction.
        "original_value": (Decimal(contract.value) - variations).quantize(CENT),
        "variations": variations.quantize(CENT),
        "contract_value": Decimal(contract.value).quantize(CENT),
        "certified": certified.quantize(CENT),
        "retention_held": retention.quantize(CENT),
        "back_charges": back_charged.quantize(CENT),
        "withholding_pct": rate,
        "withholding_tax": withheld,
        "net_payable": (after_retention - back_charged - withheld).quantize(CENT),
    }
