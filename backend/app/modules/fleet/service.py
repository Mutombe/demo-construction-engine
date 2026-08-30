"""Fleet: what each machine did, what it burned, and what it cost.

Three questions the yard cannot answer from a spreadsheet, and each is
answered here from readings rather than from opinion:

    utilisation   how much of the available time it actually worked
    burn rate     litres per hour against what this machine should burn
    due           what service is next, on meter or on days

The fuel check is the one worth being careful about. Litres on their own are
meaningless — a big machine burns a lot. Litres against the hours run since
the last fill is comparable, and a draw well above a machine's own baseline is
the signal. It is reported as an exception to look at, never as an accusation:
a blocked filter and a siphon look identical in the data, and the system does
not know which it is.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import CostSource, EquipmentStatus, MeterType
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.fleet.models import (
    Equipment,
    EquipmentAssignment,
    FuelLog,
    MaintenanceRecord,
    MaintenanceSchedule,
    MeterReading,
)

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

# How far above its own baseline a fill has to be before it is worth a look.
# 25% absorbs a hard week and a cold start; beyond that something is wrong,
# even if what is wrong is the filter rather than a person.
BURN_TOLERANCE = Decimal("1.25")

# A service coming up inside this much meter or time is "due soon" rather than
# a surprise on the day.
DUE_SOON_METER = Decimal("50")
DUE_SOON_DAYS = 14


def get_equipment(db: Session, equipment_id: uuid.UUID) -> Equipment:
    machine = db.get(Equipment, equipment_id)
    if machine is None:
        raise NotFoundError("Equipment not found")
    return machine


# --- Meter -------------------------------------------------------------------


def record_reading(db: Session, equipment_id: uuid.UUID, data, user=None) -> MeterReading:
    """Adds a reading and moves the machine's cached meter forward.

    A reading below the last one is refused. It is either a mis-key or a
    replaced meter, and both need a person: accepting it would make the gap
    since the previous reading negative, and every utilisation and burn figure
    is built on those gaps.
    """
    machine = get_equipment(db, equipment_id)
    meter = Decimal(data.meter)

    previous = db.scalar(
        select(MeterReading)
        .where(MeterReading.equipment_id == equipment_id)
        .order_by(MeterReading.reading_date.desc(), MeterReading.created_at.desc())
    )
    if previous is not None and meter < Decimal(previous.meter):
        raise ValidationFailedError(
            f"{machine.code} last read {previous.meter} on "
            f"{previous.reading_date.isoformat()}; a meter cannot go backwards"
        )

    reading = MeterReading(
        equipment_id=equipment_id,
        reading_date=data.reading_date or date.today(),
        meter=meter,
        source=data.source,
        project_id=data.project_id or machine.current_project_id,
        idle_hours=data.idle_hours,
        notes=data.notes,
        created_by=getattr(user, "id", None),
    )
    db.add(reading)
    if meter > Decimal(machine.current_meter):
        machine.current_meter = meter
    db.flush()
    return reading


# --- Fuel --------------------------------------------------------------------


def record_fuel(db: Session, equipment_id: uuid.UUID, data, user=None) -> FuelLog:
    """Logs a fill, and books it to the job if one is named.

    Fuel is a real project cost, so it goes through the cost ledger like any
    other — which means it reaches the CVR and the general ledger without a
    second entry anywhere.
    """
    machine = get_equipment(db, equipment_id)
    litres = Decimal(data.litres)
    if litres <= 0:
        raise ValidationFailedError("A fuel issue has to be for some litres")

    total = data.total_cost
    if total is None and data.unit_cost is not None:
        total = (litres * Decimal(data.unit_cost)).quantize(CENT)

    log = FuelLog(
        equipment_id=equipment_id,
        log_date=data.log_date or date.today(),
        litres=litres,
        meter=data.meter,
        unit_cost=data.unit_cost,
        total_cost=total,
        project_id=data.project_id or machine.current_project_id,
        stock_item_id=data.stock_item_id,
        reference=data.reference,
        operator=data.operator,
        notes=data.notes,
        created_by=getattr(user, "id", None),
    )
    db.add(log)

    if data.meter is not None and Decimal(data.meter) > Decimal(machine.current_meter):
        machine.current_meter = Decimal(data.meter)
    db.flush()

    if log.project_id and total:
        _post_plant_cost(
            db,
            project_id=log.project_id,
            when=log.log_date,
            amount=Decimal(total),
            description=f"Fuel {machine.code}: {litres}L",
            reference=log.reference or machine.code,
            user=user,
        )
    return log


def _post_plant_cost(db, *, project_id, when, amount, description, reference, user):
    """One route into the ledger for every plant cost, so fuel and repairs land
    where the rest of the job's cost already is."""
    from app.modules.accounting import service as accounting
    from app.modules.costs.models import CostEntry

    entry = CostEntry(
        project_id=project_id,
        entry_date=when,
        description=description,
        amount=amount,
        source=CostSource.manual,
        reference=reference[:60] if reference else None,
        created_by=getattr(user, "id", None),
    )
    db.add(entry)
    db.flush()
    accounting.post_cost_entry(db, entry, user)
    return entry


def fuel_exceptions(db: Session, days: int = 90) -> list[dict]:
    """Fills that burned well above the machine's own baseline.

    Compared against the hours actually run between fills, so a big machine on
    a hard week is not flagged simply for being big. Reported as something to
    look at: a blocked filter and a siphon are indistinguishable here.
    """
    since = date.today() - timedelta(days=days)
    out: list[dict] = []

    machines = db.scalars(
        select(Equipment).where(Equipment.is_active.is_(True))
    ).all()
    for machine in machines:
        logs = list(
            db.scalars(
                select(FuelLog)
                .where(
                    FuelLog.equipment_id == machine.id,
                    FuelLog.log_date >= since,
                    FuelLog.meter.is_not(None),
                )
                .order_by(FuelLog.meter)
            )
        )
        if len(logs) < 2:
            # One fill gives no interval to measure against, and guessing one
            # would invent the very number this is meant to test.
            continue

        baseline = (
            Decimal(machine.expected_burn_rate)
            if machine.expected_burn_rate
            else _observed_baseline(logs)
        )
        if not baseline:
            continue

        for previous, current in zip(logs, logs[1:], strict=False):
            run = Decimal(current.meter) - Decimal(previous.meter)
            if run <= 0:
                continue
            rate = (Decimal(current.litres) / run).quantize(Decimal("0.01"))
            if rate <= baseline * BURN_TOLERANCE:
                continue
            out.append(
                {
                    "equipment_id": machine.id,
                    "code": machine.code,
                    "name": machine.name,
                    "fuel_log_id": current.id,
                    "log_date": current.log_date,
                    "litres": Decimal(current.litres),
                    "meter_run": run,
                    "rate": rate,
                    "baseline": baseline.quantize(Decimal("0.01")),
                    "excess_pct": (((rate / baseline) - 1) * 100).quantize(Decimal("0.1")),
                    "operator": current.operator,
                }
            )
    return sorted(out, key=lambda row: -row["excess_pct"])


def _observed_baseline(logs: list[FuelLog]) -> Decimal | None:
    """The machine's own median rate, when nobody has set an expected one.

    Median rather than mean, so the outlier being hunted does not raise the bar
    it is measured against.
    """
    rates: list[Decimal] = []
    for previous, current in zip(logs, logs[1:], strict=False):
        run = Decimal(current.meter) - Decimal(previous.meter)
        if run > 0:
            rates.append(Decimal(current.litres) / run)
    if not rates:
        return None
    rates.sort()
    middle = len(rates) // 2
    if len(rates) % 2:
        return rates[middle]
    return (rates[middle - 1] + rates[middle]) / 2


# --- Utilisation -------------------------------------------------------------


def utilisation(db: Session, start: date, end: date, project_id=None) -> list[dict]:
    """How hard each machine worked over a window.

    Measured from the first and last readings inside the window, which is the
    only thing the data actually supports. A machine with fewer than two
    readings reports None rather than zero — "we did not measure it" and "it
    did nothing" are different answers, and a fleet report that confuses them
    sends someone to look for an idle machine that was working all along.
    """
    days = (end - start).days + 1
    out: list[dict] = []

    stmt = select(Equipment).where(Equipment.is_active.is_(True))
    if project_id is not None:
        stmt = stmt.where(Equipment.current_project_id == project_id)

    for machine in db.scalars(stmt):
        readings = list(
            db.scalars(
                select(MeterReading)
                .where(
                    MeterReading.equipment_id == machine.id,
                    MeterReading.reading_date >= start,
                    MeterReading.reading_date <= end,
                )
                .order_by(MeterReading.reading_date, MeterReading.created_at)
            )
        )
        worked = None
        if len(readings) >= 2:
            worked = (Decimal(readings[-1].meter) - Decimal(readings[0].meter)).quantize(
                Decimal("0.1")
            )

        idle = sum(
            (Decimal(r.idle_hours) for r in readings if r.idle_hours is not None), ZERO
        )
        # A working day, not a calendar day: nobody expects a grader to run on
        # a Sunday, and measuring against 24 hours makes every machine look idle.
        available = Decimal(days) * Decimal("8")
        out.append(
            {
                "equipment_id": machine.id,
                "code": machine.code,
                "name": machine.name,
                "category": machine.category.value,
                "status": machine.status.value,
                "meter_type": machine.meter_type.value,
                "readings": len(readings),
                "worked": worked,
                "idle_hours": idle.quantize(Decimal("0.1")) if idle else ZERO,
                "available_hours": available,
                "utilisation_pct": (
                    ((worked / available) * 100).quantize(Decimal("0.1"))
                    if worked is not None and available and machine.meter_type is MeterType.hours
                    else None
                ),
                "measured": worked is not None,
            }
        )
    return sorted(
        out,
        key=lambda row: (row["utilisation_pct"] is None, row["utilisation_pct"] or 0),
    )


# --- Maintenance -------------------------------------------------------------


def maintenance_due(db: Session) -> list[dict]:
    """What is due, overdue, or coming up, on meter or on days."""
    today = date.today()
    out: list[dict] = []

    rows = db.execute(
        select(MaintenanceSchedule, Equipment)
        .join(Equipment, Equipment.id == MaintenanceSchedule.equipment_id)
        .where(MaintenanceSchedule.is_active.is_(True), Equipment.is_active.is_(True))
    ).all()

    for schedule, machine in rows:
        meter_due = meter_remaining = None
        if schedule.interval_meter:
            base = Decimal(schedule.last_done_meter or 0)
            meter_due = base + Decimal(schedule.interval_meter)
            meter_remaining = (meter_due - Decimal(machine.current_meter)).quantize(
                Decimal("0.1")
            )

        date_due = days_remaining = None
        if schedule.interval_days:
            base_date = schedule.last_done_date or (machine.purchase_date or today)
            date_due = base_date + timedelta(days=schedule.interval_days)
            days_remaining = (date_due - today).days

        # Whichever comes first governs: a machine that has done the hours is
        # due even if the date has not arrived, and the other way round.
        overdue = (meter_remaining is not None and meter_remaining <= 0) or (
            days_remaining is not None and days_remaining <= 0
        )
        soon = not overdue and (
            (meter_remaining is not None and meter_remaining <= DUE_SOON_METER)
            or (days_remaining is not None and days_remaining <= DUE_SOON_DAYS)
        )
        if not overdue and not soon:
            continue

        out.append(
            {
                "schedule_id": schedule.id,
                "equipment_id": machine.id,
                "code": machine.code,
                "name": machine.name,
                "service": schedule.name,
                "current_meter": Decimal(machine.current_meter),
                "meter_due_at": meter_due,
                "meter_remaining": meter_remaining,
                "date_due": date_due,
                "days_remaining": days_remaining,
                "status": "overdue" if overdue else "due_soon",
            }
        )
    return sorted(out, key=lambda row: (row["status"] != "overdue", row["code"]))


def record_maintenance(db: Session, equipment_id: uuid.UUID, data, user=None):
    """Logs the work, resets the schedule it satisfied, and books the cost."""
    machine = get_equipment(db, equipment_id)
    record = MaintenanceRecord(
        equipment_id=equipment_id,
        schedule_id=data.schedule_id,
        service_date=data.service_date or date.today(),
        meter=data.meter if data.meter is not None else machine.current_meter,
        description=data.description,
        cost=data.cost,
        downtime_hours=data.downtime_hours,
        supplier_id=data.supplier_id,
        reference=data.reference,
        created_by=getattr(user, "id", None),
    )
    db.add(record)

    if data.schedule_id:
        schedule = db.get(MaintenanceSchedule, data.schedule_id)
        if schedule is None or schedule.equipment_id != equipment_id:
            raise ValidationFailedError("That schedule belongs to another machine")
        schedule.last_done_meter = record.meter
        schedule.last_done_date = record.service_date
    db.flush()

    if machine.current_project_id and data.cost:
        _post_plant_cost(
            db,
            project_id=machine.current_project_id,
            when=record.service_date,
            amount=Decimal(data.cost),
            description=f"Maintenance {machine.code}: {data.description}"[:200],
            reference=data.reference or machine.code,
            user=user,
        )
    return record


# --- Deployment --------------------------------------------------------------


def assign(db: Session, equipment_id: uuid.UUID, data, user=None) -> EquipmentAssignment:
    """Moves a machine to a job, closing whatever it was on.

    A machine is in one place at a time, so the open assignment is closed
    rather than left running: two open assignments would double-count the
    plant cost of every hour it ran.
    """
    from app.modules.projects.service import get_project

    machine = get_equipment(db, equipment_id)
    get_project(db, data.project_id)
    started = data.started_on or date.today()

    open_row = db.scalar(
        select(EquipmentAssignment).where(
            EquipmentAssignment.equipment_id == equipment_id,
            EquipmentAssignment.ended_on.is_(None),
        )
    )
    if open_row is not None:
        if open_row.project_id == data.project_id:
            raise ConflictError(f"{machine.code} is already on that project")
        if started < open_row.started_on:
            raise ValidationFailedError(
                "A machine cannot move to a job before it arrived at the last one"
            )
        open_row.ended_on = started

    assignment = EquipmentAssignment(
        equipment_id=equipment_id,
        project_id=data.project_id,
        started_on=started,
        notes=data.notes,
        created_by=getattr(user, "id", None),
    )
    db.add(assignment)
    machine.current_project_id = data.project_id
    machine.status = EquipmentStatus.on_site
    db.flush()
    return assignment


def release(db: Session, equipment_id: uuid.UUID, when: date | None = None) -> Equipment:
    """Brings a machine back off a job."""
    machine = get_equipment(db, equipment_id)
    open_row = db.scalar(
        select(EquipmentAssignment).where(
            EquipmentAssignment.equipment_id == equipment_id,
            EquipmentAssignment.ended_on.is_(None),
        )
    )
    if open_row is None:
        raise ConflictError(f"{machine.code} is not on a project")
    open_row.ended_on = when or date.today()
    machine.current_project_id = None
    machine.status = EquipmentStatus.available
    db.flush()
    return machine


def fleet_summary(db: Session) -> dict:
    """The yard at a glance, for the dashboard."""
    counts = dict(
        db.execute(
            select(Equipment.status, func.count())
            .where(Equipment.is_active.is_(True))
            .group_by(Equipment.status)
        ).all()
    )
    total = sum(counts.values())
    return {
        "total": total,
        "by_status": {status.value: count for status, count in counts.items()},
        "on_site": counts.get(EquipmentStatus.on_site, 0),
        "workshop": counts.get(EquipmentStatus.workshop, 0),
        "standing": counts.get(EquipmentStatus.standing, 0),
        "maintenance_due": len(maintenance_due(db)),
        "fuel_exceptions": len(fuel_exceptions(db)),
    }
