"""Plant as a business rather than a log: what it earns, what it wears out.

Two things a plant register has to answer that a list of readings cannot.

**What did the job pay for the machine?** There are only two coherent answers
and they cannot both be used. Under `direct` costing, fuel and repairs go
straight to whichever job the machine was on: simple, and what most
contractors do, but the job never bears the cost of *owning* the machine —
depreciation, insurance, the standing weeks between jobs — so plant always
looks cheaper than it is. Under `internal_hire`, every running and ownership
cost pools against the yard and jobs are charged an hourly rate instead. The
gap between the pool and what was recovered is the yard's over- or
under-recovery, and it is the only figure that says whether owning the plant
beats hiring it.

Running a recharge while the books are on `direct` would charge a job for
fuel it has already been charged for, so this module refuses to.

**What is it worth now?** Depreciation, straight-line, once a month, and only
where somebody actually supplied a cost and a life. A machine with no life
entered is not depreciated over a guessed one — an invented life is an
invented number that then sits in the accounts looking authoritative.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import CostSource, JournalSource, PlantCostingMode
from app.core.exceptions import ConflictError, NotFoundError
from app.modules.fleet.models import (
    DepreciationCharge,
    Equipment,
    EquipmentAssignment,
    MeterReading,
    PlantRecharge,
)

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def costing_mode(db: Session) -> PlantCostingMode:
    from app.modules.company.models import CompanySettings

    settings = db.scalar(select(CompanySettings).limit(1))
    return settings.plant_costing_mode if settings else PlantCostingMode.direct


def _month_end(period_start: date) -> date:
    if period_start.month == 12:
        return date(period_start.year, 12, 31)
    return date(period_start.year, period_start.month + 1, 1) - timedelta(days=1)


def _project_at(db: Session, equipment_id: uuid.UUID, when: date) -> uuid.UUID | None:
    """Which job the machine was on that day, from its assignment history."""
    row = db.scalar(
        select(EquipmentAssignment)
        .where(
            EquipmentAssignment.equipment_id == equipment_id,
            EquipmentAssignment.started_on <= when,
        )
        .order_by(EquipmentAssignment.started_on.desc())
        .limit(1)
    )
    if row is None:
        return None
    if row.ended_on is not None and row.ended_on < when:
        return None
    return row.project_id


def metered_by_project(
    db: Session, equipment_id: uuid.UUID, start: date, end: date
) -> dict[uuid.UUID, Decimal]:
    """Movement in the window, split across the jobs that caused it.

    A gap is attributed to where the machine was when the *later* reading was
    taken, because that is the job it had been working for. Movement with no
    job behind it is dropped rather than spread: charging a job for hours that
    might not be its own is worse than charging nothing.
    """
    readings = list(
        db.scalars(
            select(MeterReading)
            .where(
                MeterReading.equipment_id == equipment_id,
                MeterReading.reading_date >= start,
                MeterReading.reading_date <= end,
            )
            .order_by(MeterReading.reading_date, MeterReading.created_at)
        )
    )
    if not readings:
        return {}

    # The last reading before the window is the opening position; without it
    # the first reading inside would look like it did all its work that day.
    opening = db.scalar(
        select(MeterReading)
        .where(
            MeterReading.equipment_id == equipment_id,
            MeterReading.reading_date < start,
        )
        .order_by(MeterReading.reading_date.desc(), MeterReading.created_at.desc())
        .limit(1)
    )

    # With no earlier reading, the meter it was registered at is the
    # baseline — otherwise a machine's first month of work is never charged
    # to anyone, which is exactly the month a new machine works hardest.
    machine = get_equipment_or_404(db, equipment_id)
    totals: dict[uuid.UUID, Decimal] = {}
    previous = Decimal(opening.meter) if opening else Decimal(machine.opening_meter)
    for reading in readings:
        moved = Decimal(reading.meter) - previous
        previous = Decimal(reading.meter)
        if moved <= 0:
            continue
        project_id = reading.project_id or _project_at(db, equipment_id, reading.reading_date)
        if project_id is None:
            continue
        totals[project_id] = totals.get(project_id, ZERO) + moved
    return totals


def run_recharge(db: Session, period_start: date, user=None) -> dict:
    """Charge every job for the plant it used in a month.

    Safe to run twice: a machine and job already recharged for the period is
    left alone rather than charged again, which is enforced by the database
    and not merely by this loop.
    """
    from app.modules.accounting import service as accounting
    from app.modules.costs.models import CostEntry

    mode = costing_mode(db)
    if mode is not PlantCostingMode.internal_hire:
        raise ConflictError(
            "The books are on direct plant costing, where fuel and repairs already "
            "go to the job. Recharging as well would charge it twice. Switch plant "
            "costing to internal hire in Settings first."
        )

    period_start = period_start.replace(day=1)
    period_end = _month_end(period_start)
    accounting.ensure_chart(db)

    charged = ZERO
    created = 0
    skipped = 0
    lines: list[dict] = []

    for machine in db.scalars(
        select(Equipment).where(Equipment.is_active.is_(True)).order_by(Equipment.code)
    ):
        if not machine.hourly_rate or Decimal(machine.hourly_rate) <= 0:
            continue
        rate = Decimal(machine.hourly_rate)

        for project_id, units in metered_by_project(
            db, machine.id, period_start, period_end
        ).items():
            existing = db.scalar(
                select(PlantRecharge).where(
                    PlantRecharge.equipment_id == machine.id,
                    PlantRecharge.project_id == project_id,
                    PlantRecharge.period_start == period_start,
                )
            )
            if existing is not None:
                skipped += 1
                continue

            amount = (units * rate).quantize(CENT)
            if amount <= 0:
                continue

            description = (
                f"{machine.code} {units} "
                f"{'hrs' if machine.meter_type.value == 'hours' else 'km'} at {rate}"
            )
            entry = CostEntry(
                project_id=project_id,
                entry_date=period_end,
                description=description,
                amount=amount,
                source=CostSource.manual,
                reference=f"PLANT-{period_start:%Y%m}-{machine.code}",
                created_by=getattr(user, "id", None),
            )
            db.add(entry)
            db.flush()

            journal = accounting.create_journal(
                db,
                journal_date=period_end,
                memo=f"Plant recharge {period_start:%b %Y} — {machine.code}",
                source=JournalSource.cost_entry,
                source_id=entry.id,
                project_id=project_id,
                created_by=getattr(user, "id", None),
                lines=[
                    # The job bears it...
                    {"account_code": "5200", "debit": amount, "description": description},
                    # ...and the yard's pool is relieved of it. Not revenue:
                    # nothing left the business, so turnover must not move.
                    {"account_code": accounting.PLANT_RECOVERED, "credit": amount},
                ],
            )
            accounting.post(db, journal.id, user)

            db.add(
                PlantRecharge(
                    equipment_id=machine.id,
                    project_id=project_id,
                    period_start=period_start,
                    period_end=period_end,
                    units=units.quantize(CENT),
                    rate=rate,
                    amount=amount,
                    cost_entry_id=entry.id,
                    journal_id=journal.id,
                    created_by=getattr(user, "id", None),
                )
            )
            charged += amount
            created += 1
            lines.append(
                {
                    "equipment_id": machine.id,
                    "code": machine.code,
                    "project_id": project_id,
                    "units": units.quantize(CENT),
                    "rate": rate,
                    "amount": amount,
                }
            )

    db.flush()
    return {
        "period_start": period_start,
        "period_end": period_end,
        "recharged": created,
        "already_done": skipped,
        "total": charged.quantize(CENT),
        "lines": lines,
    }


def recovery(db: Session, start: date, end: date) -> dict:
    """What the yard cost against what it charged out.

    Under-recovery means the rates are too low or the machines stood idle;
    over-recovery means jobs are subsidising the yard. Either way it is a
    number somebody has to answer for, and it does not exist anywhere else.
    """
    from app.modules.accounting import service as accounting
    from app.modules.accounting.models import Account, JournalLine, Journal

    def balance(code: str) -> Decimal:
        account = db.scalar(select(Account).where(Account.code == code))
        if account is None:
            return ZERO
        total = db.scalar(
            select(
                func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)
            )
            .select_from(JournalLine)
            .join(Journal, Journal.id == JournalLine.journal_id)
            .where(
                JournalLine.account_id == account.id,
                Journal.journal_date >= start,
                Journal.journal_date <= end,
                Journal.posted_at.is_not(None),
            )
        )
        return Decimal(total or 0)

    pooled = balance(accounting.PLANT_OPERATING)
    # Recovered is a credit balance, so it comes back negative.
    recovered = -balance(accounting.PLANT_RECOVERED)
    return {
        "start": start,
        "end": end,
        "mode": costing_mode(db).value,
        "pooled": pooled.quantize(CENT),
        "recovered": recovered.quantize(CENT),
        # Positive means the yard cost more than it charged out.
        "under_recovered": (pooled - recovered).quantize(CENT),
    }


# --- Depreciation ------------------------------------------------------------


def monthly_depreciation(machine: Equipment) -> Decimal | None:
    """Straight line, or nothing at all.

    Returns None where the inputs were never supplied. A machine depreciated
    over a life somebody guessed produces a number that looks as authoritative
    as a real one, which is worse than an obvious gap.
    """
    if not machine.purchase_cost or not machine.useful_life_months:
        return None
    if machine.useful_life_months <= 0:
        return None
    residual = Decimal(machine.residual_value or 0)
    depreciable = Decimal(machine.purchase_cost) - residual
    if depreciable <= 0:
        return None
    return (depreciable / Decimal(machine.useful_life_months)).quantize(CENT)


def run_depreciation(db: Session, period_start: date, user=None) -> dict:
    """One month of wear, posted. Repeating a month is a no-op."""
    from app.modules.accounting import service as accounting

    period_start = period_start.replace(day=1)
    period_end = _month_end(period_start)
    accounting.ensure_chart(db)

    posted = ZERO
    created = 0
    skipped = 0
    not_depreciated: list[str] = []

    for machine in db.scalars(
        select(Equipment).where(Equipment.is_active.is_(True)).order_by(Equipment.code)
    ):
        amount = monthly_depreciation(machine)
        if amount is None or amount <= 0:
            not_depreciated.append(machine.code)
            continue

        # Stop at the residual: a machine written down to nothing keeps
        # working, but it stops costing the accounts anything.
        written_off = Decimal(
            db.scalar(
                select(func.coalesce(func.sum(DepreciationCharge.amount), 0)).where(
                    DepreciationCharge.equipment_id == machine.id
                )
            )
            or 0
        )
        remaining = (
            Decimal(machine.purchase_cost) - Decimal(machine.residual_value or 0) - written_off
        )
        if remaining <= 0:
            continue
        amount = min(amount, remaining).quantize(CENT)

        if db.scalar(
            select(DepreciationCharge).where(
                DepreciationCharge.equipment_id == machine.id,
                DepreciationCharge.period_start == period_start,
            )
        ):
            skipped += 1
            continue

        journal = accounting.create_journal(
            db,
            journal_date=period_end,
            memo=f"Depreciation {period_start:%b %Y} — {machine.code}",
            source=JournalSource.manual,
            created_by=getattr(user, "id", None),
            lines=[
                {"account_code": accounting.DEPRECIATION, "debit": amount},
                {"account_code": accounting.ACCUMULATED_DEPRECIATION, "credit": amount},
            ],
        )
        accounting.post(db, journal.id, user)

        db.add(
            DepreciationCharge(
                equipment_id=machine.id,
                period_start=period_start,
                amount=amount,
                journal_id=journal.id,
                created_by=getattr(user, "id", None),
            )
        )
        posted += amount
        created += 1

    db.flush()
    return {
        "period_start": period_start,
        "posted": created,
        "already_done": skipped,
        "total": posted.quantize(CENT),
        "not_depreciated": not_depreciated,
    }


def asset_register(db: Session) -> list[dict]:
    """What the plant is carried at, machine by machine."""
    rows = []
    for machine in db.scalars(
        select(Equipment).where(Equipment.is_active.is_(True)).order_by(Equipment.code)
    ):
        written_off = Decimal(
            db.scalar(
                select(func.coalesce(func.sum(DepreciationCharge.amount), 0)).where(
                    DepreciationCharge.equipment_id == machine.id
                )
            )
            or 0
        )
        cost = Decimal(machine.purchase_cost) if machine.purchase_cost else None
        rows.append(
            {
                "equipment_id": machine.id,
                "code": machine.code,
                "name": machine.name,
                "ownership": machine.ownership.value,
                "purchase_date": machine.purchase_date,
                "purchase_cost": cost,
                "residual_value": Decimal(machine.residual_value)
                if machine.residual_value
                else None,
                "useful_life_months": machine.useful_life_months,
                "accumulated_depreciation": written_off.quantize(CENT),
                # Null rather than zero where no cost was ever entered: an
                # unpriced machine has no book value, it has no record.
                "net_book_value": (cost - written_off).quantize(CENT) if cost else None,
                "monthly_charge": monthly_depreciation(machine),
            }
        )
    return rows


def get_equipment_or_404(db: Session, equipment_id: uuid.UUID) -> Equipment:
    machine = db.get(Equipment, equipment_id)
    if machine is None:
        raise NotFoundError("Equipment not found")
    return machine


# --- Statutory compliance ----------------------------------------------------
#
# Which certificates actually stop a machine working depends on what it is. A
# generator needs no roadworthiness test; a tipper on the public road does;
# lifting gear needs a thorough examination and nothing else will do instead.

MANDATORY_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "crane": ("insurance", "thorough_examination"),
    "tipper": ("insurance", "roadworthiness"),
    "truck": ("insurance", "roadworthiness"),
    "light_vehicle": ("insurance", "roadworthiness"),
}
# Everything else still has to be insured.
DEFAULT_MANDATORY: tuple[str, ...] = ("insurance",)


def mandatory_certs(machine: Equipment) -> tuple[str, ...]:
    return MANDATORY_BY_CATEGORY.get(machine.category.value, DEFAULT_MANDATORY)


def equipment_compliance(db: Session, equipment_id: uuid.UUID, as_at: date | None = None) -> dict:
    """Where a machine stands on its paperwork, certificate by certificate."""
    from app.modules.fleet.models import EquipmentCertificate

    as_at = as_at or date.today()
    machine = get_equipment_or_404(db, equipment_id)

    held: dict = {}
    for cert in db.scalars(
        select(EquipmentCertificate)
        .where(EquipmentCertificate.equipment_id == equipment_id)
        .order_by(EquipmentCertificate.expires_on.desc().nullsfirst())
    ):
        # Keep the copy that runs longest, so renewing does not leave the old
        # one deciding the answer.
        held.setdefault(cert.cert_type.value, cert)

    required = mandatory_certs(machine)
    items = []
    blocking: list[str] = []
    incomplete: list[str] = []
    for cert_type in sorted(set(required) | set(held)):
        cert = held.get(cert_type)
        if cert is None:
            state, days = "missing", None
        elif cert.expires_on is None:
            state, days = "valid", None
        else:
            days = (cert.expires_on - as_at).days
            state = "expired" if days < 0 else ("expiring" if days <= 30 else "valid")

        items.append(
            {
                "cert_type": cert_type,
                "is_mandatory": cert_type in required,
                "state": state,
                "certificate_id": cert.id if cert else None,
                "reference": cert.reference if cert else None,
                "expires_on": cert.expires_on if cert else None,
                "days_to_expiry": days,
            }
        )
        if cert_type not in required:
            continue
        if state == "expired":
            blocking.append(cert_type)
        elif state == "missing":
            incomplete.append(cert_type)

    return {
        "equipment_id": machine.id,
        "code": machine.code,
        "name": machine.name,
        # Complete and in date. Anything less is worth showing, but only
        # `blocking` actually stops the machine.
        "is_compliant": not blocking and not incomplete,
        "blocking": blocking,
        "incomplete": incomplete,
        "certificates": items,
    }


# Where a missing certificate is as good as an expired one. Lifting gear may
# not lawfully be used without a current thorough examination, and the cost of
# being wrong is not a fine.
MISSING_ALSO_BLOCKS = ("thorough_examination",)


def require_roadworthy(db: Session, equipment_id: uuid.UUID) -> None:
    """Refuses to let a machine go to site on lapsed paperwork.

    An **expired** certificate blocks: somebody entered cover and it has run
    out, which is a fact the system knows. A **missing** one generally does
    not, because it usually means nobody has finished entering the paperwork
    yet — an absence of data, not evidence of an absence of insurance. A
    system that refuses to move any machine until every certificate has been
    typed in is a system that gets worked around within a week.

    Lifting gear is the exception, and is listed rather than inferred.

    Checked when the machine is sent out rather than when the certificate
    lapses, because that is the moment somebody is making a decision and can
    still act on the answer.
    """
    status = equipment_compliance(db, equipment_id)
    stops = list(status["blocking"]) + [
        item for item in status["incomplete"] if item in MISSING_ALSO_BLOCKS
    ]
    if not stops:
        return
    named = ", ".join(item.replace("_", " ") for item in stops)
    raise ConflictError(
        f"{status['code']} cannot go to site: {named} is missing or out of date"
    )


def expiring_certificates(db: Session, days: int = 30) -> list[dict]:
    """Everything about to lapse across the yard, soonest first."""
    from app.modules.fleet.models import EquipmentCertificate

    today = date.today()
    rows = db.execute(
        select(EquipmentCertificate, Equipment)
        .join(Equipment, Equipment.id == EquipmentCertificate.equipment_id)
        .where(
            EquipmentCertificate.expires_on.is_not(None),
            Equipment.is_active.is_(True),
        )
        .order_by(EquipmentCertificate.expires_on)
    ).all()

    out = []
    for cert, machine in rows:
        remaining = (cert.expires_on - today).days
        if remaining > days:
            continue
        out.append(
            {
                "equipment_id": machine.id,
                "code": machine.code,
                "name": machine.name,
                "cert_type": cert.cert_type.value,
                "reference": cert.reference,
                "expires_on": cert.expires_on,
                "days_to_expiry": remaining,
                "state": "expired" if remaining < 0 else "expiring",
            }
        )
    return out


# --- Availability ------------------------------------------------------------


def availability(db: Session, start: date, end: date) -> list[dict]:
    """How much of the time a machine was on a job it was actually able to work.

    The denominator is days it was assigned to a site, not calendar days: a
    machine sitting in the yard is not unavailable, it is unused, and rolling
    the two together makes both meaningless. Where it was never assigned in
    the window there is nothing to report, so it is reported as null rather
    than as 100% or 0%.
    """
    from app.modules.fleet.models import MaintenanceRecord

    HOURS_PER_DAY = Decimal("8")
    rows = []

    for machine in db.scalars(
        select(Equipment).where(Equipment.is_active.is_(True)).order_by(Equipment.code)
    ):
        assigned_days = 0
        for row in db.scalars(
            select(EquipmentAssignment).where(
                EquipmentAssignment.equipment_id == machine.id,
                EquipmentAssignment.started_on <= end,
            )
        ):
            span_start = max(row.started_on, start)
            span_end = min(row.ended_on or end, end)
            if span_end >= span_start:
                assigned_days += (span_end - span_start).days + 1

        downtime, breakdowns = db.execute(
            select(
                func.coalesce(func.sum(MaintenanceRecord.downtime_hours), 0),
                func.count(),
            ).where(
                MaintenanceRecord.equipment_id == machine.id,
                MaintenanceRecord.service_date >= start,
                MaintenanceRecord.service_date <= end,
            )
        ).one()
        downtime = Decimal(downtime or 0)

        scheduled = Decimal(assigned_days) * HOURS_PER_DAY
        metered = sum(metered_by_project(db, machine.id, start, end).values(), ZERO)

        rows.append(
            {
                "equipment_id": machine.id,
                "code": machine.code,
                "name": machine.name,
                "assigned_days": assigned_days,
                "scheduled_hours": scheduled.quantize(CENT) if assigned_days else None,
                "downtime_hours": downtime.quantize(CENT),
                "breakdowns": int(breakdowns or 0),
                "availability_pct": (
                    float(
                        ((scheduled - downtime) / scheduled * 100).quantize(Decimal("0.1"))
                    )
                    if scheduled > 0
                    else None
                ),
                # Hours run between visits to the workshop. Null on a machine
                # that has not broken down: dividing by nothing is not infinity,
                # it is an absence of evidence.
                "mean_hours_between_failures": (
                    (Decimal(metered) / Decimal(breakdowns)).quantize(CENT)
                    if breakdowns and metered
                    else None
                ),
                "metered": Decimal(metered).quantize(CENT) if metered else None,
            }
        )
    return rows
