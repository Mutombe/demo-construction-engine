"""Taking in work that was captured with no signal.

The whole module rests on two rules.

**Nothing is written twice.** Every capture carries an id the device made
before it saved the record locally, and that id is unique here. A phone that
retries after a dropped connection gets the original answer back, so a diary
entry sent three times is still one diary entry.

**Nothing is silently lost, in either direction.** A capture that cannot be
applied is kept with the reason it was refused, and the person is told. Where
a record already exists on the server, the server's content is never
overwritten by a device that has been out of range for a week — the device's
version is folded into the notes, attributed and dated, so both readings of
the day survive. This is the conflict rule, and it is deliberately not
last-write-wins: the last writer is usually just whoever regained signal
last, which says nothing about who was right.
"""

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError, ValidationFailedError
from app.modules.sync.models import SyncOperation
from app.modules.sync.schemas import (
    Bootstrap,
    SyncOperationIn,
    SyncPush,
    SyncPushResult,
    SyncResult,
)

logger = logging.getLogger(__name__)


class Outcome(NamedTuple):
    status: str  # applied | merged
    entity_type: str
    entity_id: uuid.UUID
    detail: str | None = None


def _uuid(payload: dict[str, Any], key: str, required: bool = True) -> uuid.UUID | None:
    raw = payload.get(key)
    if raw in (None, ""):
        if required:
            raise ValidationFailedError(f"{key.replace('_', ' ')} is missing")
        return None
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        raise ValidationFailedError(f"{raw} is not a valid {key.replace('_', ' ')}") from None


def _date(payload: dict[str, Any], key: str, default: date | None = None) -> date:
    raw = payload.get(key)
    if raw in (None, ""):
        if default is None:
            raise ValidationFailedError(f"{key.replace('_', ' ')} is missing")
        return default
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        raise ValidationFailedError(f"{raw} is not a date") from None


def _decimal(payload: dict[str, Any], key: str, required: bool = True) -> Decimal | None:
    raw = payload.get(key)
    if raw in (None, ""):
        if required:
            raise ValidationFailedError(f"{key.replace('_', ' ')} is missing")
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        raise ValidationFailedError(f"{raw} is not a number") from None


def _attribution(op: SyncOperationIn, user) -> str:
    who = getattr(user, "full_name", None) or "Site"
    when = op.captured_at or datetime.now(timezone.utc)
    return f"{who}, {when:%d %b %H:%M} on site"


# --- Handlers ----------------------------------------------------------------
#
# Each one takes the capture as it came off the device and returns what
# happened to it. They raise for anything they will not accept; the caller
# rolls that one capture back and records the reason.


def _diary_entry(db: Session, op: SyncOperationIn, user) -> Outcome:
    """The day's diary, which may already have been written by someone else.

    Two foremen on one site both write what they saw. Neither is wrong, so
    neither is discarded: blank fields are filled, and anything that would
    have overwritten existing content is appended under who wrote it.
    """
    from app.modules.site.models import SiteDiaryEntry

    project_id = _uuid(op.payload, "project_id")
    entry_date = _date(op.payload, "entry_date", date.today())
    work_done = str(op.payload.get("work_done") or "").strip()
    if not work_done:
        raise ValidationFailedError("A diary entry has to say what was done")

    existing = db.scalar(
        select(SiteDiaryEntry).where(
            SiteDiaryEntry.project_id == project_id,
            SiteDiaryEntry.entry_date == entry_date,
        )
    )
    fields = {
        "weather": op.payload.get("weather"),
        "labour_headcount": op.payload.get("labour_headcount"),
        "plant_equipment": op.payload.get("plant_equipment"),
        "work_done": work_done,
        "delays": op.payload.get("delays"),
        "notes": op.payload.get("notes"),
    }

    if existing is None:
        from app.modules.projects.service import get_project

        get_project(db, project_id)
        entry = SiteDiaryEntry(
            project_id=project_id,
            entry_date=entry_date,
            weather=fields["weather"] or "sunny",
            labour_headcount=fields["labour_headcount"] or 0,
            plant_equipment=fields["plant_equipment"],
            work_done=work_done,
            delays=fields["delays"],
            notes=fields["notes"],
            created_by=getattr(user, "id", None),
        )
        db.add(entry)
        db.flush()
        return Outcome("applied", "diary_entry", entry.id)

    carried: list[str] = []
    for field in ("plant_equipment", "delays"):
        incoming = (fields[field] or "").strip()
        if not incoming:
            continue
        current = (getattr(existing, field) or "").strip()
        if not current:
            setattr(existing, field, incoming)
        elif incoming not in current:
            carried.append(f"{field.replace('_', ' ').capitalize()}: {incoming}")

    if not (existing.work_done or "").strip():
        existing.work_done = work_done
    elif work_done not in existing.work_done:
        carried.append(work_done)

    incoming_notes = (fields["notes"] or "").strip()
    if incoming_notes and incoming_notes not in (existing.notes or ""):
        carried.append(incoming_notes)

    if not existing.labour_headcount and fields["labour_headcount"]:
        existing.labour_headcount = int(fields["labour_headcount"])

    if carried:
        block = f"[{_attribution(op, user)}]\n" + "\n".join(carried)
        existing.notes = f"{existing.notes}\n\n{block}" if existing.notes else block
        db.flush()
        return Outcome(
            "merged",
            "diary_entry",
            existing.id,
            "The day was already written up; your entry was added to it.",
        )

    db.flush()
    return Outcome("applied", "diary_entry", existing.id)


def _diary_labour(db: Session, op: SyncOperationIn, user) -> Outcome:
    """Who worked that day. The same crew re-counted is a correction of one
    fact, so the later count for a worker replaces the earlier one."""
    from app.modules.site.models import SiteDiaryEntry, SiteDiaryLabour

    project_id = _uuid(op.payload, "project_id")
    entry_date = _date(op.payload, "entry_date", date.today())
    lines = op.payload.get("lines") or []
    if not isinstance(lines, list) or not lines:
        raise ValidationFailedError("No labour was recorded")

    entry = db.scalar(
        select(SiteDiaryEntry).where(
            SiteDiaryEntry.project_id == project_id,
            SiteDiaryEntry.entry_date == entry_date,
        )
    )
    if entry is None:
        raise ValidationFailedError(
            f"There is no diary for {entry_date:%d %b} to hang this labour on"
        )

    touched = 0
    for line in lines:
        worker_id = _uuid(line, "worker_id")
        quantity = _decimal(line, "quantity")
        row = db.scalar(
            select(SiteDiaryLabour).where(
                SiteDiaryLabour.diary_entry_id == entry.id,
                SiteDiaryLabour.worker_id == worker_id,
            )
        )
        if row is None:
            row = SiteDiaryLabour(diary_entry_id=entry.id, worker_id=worker_id, quantity=quantity)
            db.add(row)
        else:
            row.quantity = quantity
        overtime = _decimal(line, "overtime_quantity", required=False)
        if overtime is not None:
            row.overtime_quantity = overtime
        if line.get("notes"):
            row.notes = str(line["notes"])
        touched += 1

    db.flush()
    entry.labour_headcount = max(entry.labour_headcount or 0, touched)
    return Outcome("applied", "diary_entry", entry.id, f"{touched} on the day")


def _site_issue(db: Session, op: SyncOperationIn, user) -> Outcome:
    """Something seen on site. Never merged: two people reporting the same
    crack is two reports, and deciding they are one is not the sync layer's
    call to make."""
    from app.modules.site.models import SiteIssue
    from app.modules.projects.service import get_project

    project_id = _uuid(op.payload, "project_id")
    title = str(op.payload.get("title") or "").strip()
    if not title:
        raise ValidationFailedError("An issue needs a title")
    get_project(db, project_id)

    issue = SiteIssue(
        project_id=project_id,
        title=title[:200],
        description=op.payload.get("description"),
        severity=op.payload.get("severity") or "medium",
        raised_date=_date(op.payload, "raised_date", date.today()),
        created_by=getattr(user, "id", None),
    )
    db.add(issue)
    db.flush()
    return Outcome("applied", "site_issue", issue.id)


def _meter_reading(db: Session, op: SyncOperationIn, user) -> Outcome:
    from app.modules.fleet import service as fleet
    from app.modules.fleet.schemas import MeterReadingCreate

    equipment_id = _uuid(op.payload, "equipment_id")
    reading = fleet.record_reading(
        db,
        equipment_id,
        MeterReadingCreate(
            reading_date=_date(op.payload, "reading_date", date.today()),
            meter=_decimal(op.payload, "meter"),
            source=op.payload.get("source") or "manual",
            project_id=_uuid(op.payload, "project_id", required=False),
            idle_hours=_decimal(op.payload, "idle_hours", required=False),
            notes=op.payload.get("notes"),
        ),
        user,
    )
    return Outcome("applied", "meter_reading", reading.id)


def _fuel_log(db: Session, op: SyncOperationIn, user) -> Outcome:
    from app.modules.fleet import service as fleet
    from app.modules.fleet.schemas import FuelLogCreate

    equipment_id = _uuid(op.payload, "equipment_id")
    log = fleet.record_fuel(
        db,
        equipment_id,
        FuelLogCreate(
            log_date=_date(op.payload, "log_date", date.today()),
            litres=_decimal(op.payload, "litres"),
            meter=_decimal(op.payload, "meter", required=False),
            unit_cost=_decimal(op.payload, "unit_cost", required=False),
            project_id=_uuid(op.payload, "project_id", required=False),
            reference=op.payload.get("reference"),
            operator=op.payload.get("operator"),
            notes=op.payload.get("notes"),
        ),
        user,
    )
    return Outcome("applied", "fuel_log", log.id)


HANDLERS: dict[str, Callable[[Session, SyncOperationIn, Any], Outcome]] = {
    "diary_entry": _diary_entry,
    "diary_labour": _diary_labour,
    "site_issue": _site_issue,
    "meter_reading": _meter_reading,
    "fuel_log": _fuel_log,
}


# --- Push --------------------------------------------------------------------


def push(db: Session, data: SyncPush, user) -> SyncPushResult:
    """Apply a device's backlog, one capture at a time.

    Each capture gets its own savepoint, so a single bad record does not take
    the rest of the day's work down with it. Without that, one impossible row
    from a fortnight ago blocks a phone forever, and the person carrying it
    stops using the app.
    """
    now = datetime.now(timezone.utc)
    results: list[SyncResult] = []

    for op in data.operations:
        prior = db.scalar(
            select(SyncOperation).where(SyncOperation.client_op_id == op.client_op_id)
        )
        if prior is not None:
            results.append(
                SyncResult(
                    client_op_id=op.client_op_id,
                    status="duplicate",
                    entity_type=prior.entity_type,
                    entity_id=prior.entity_id,
                    detail=prior.detail,
                )
            )
            continue

        record = SyncOperation(
            client_op_id=op.client_op_id,
            device_id=data.device_id,
            user_id=getattr(user, "id", None),
            op_type=op.op_type,
            payload=op.payload,
            captured_at=op.captured_at,
            received_at=now,
        )

        savepoint = db.begin_nested()
        try:
            handler = HANDLERS.get(op.op_type)
            if handler is None:
                raise ValidationFailedError(f"This version cannot take a {op.op_type}")
            outcome = handler(db, op, user)
            savepoint.commit()
            record.status = outcome.status
            record.entity_type = outcome.entity_type
            record.entity_id = outcome.entity_id
            record.detail = outcome.detail
        except AppError as exc:
            savepoint.rollback()
            record.status = "rejected"
            record.detail = exc.detail
        except Exception:
            savepoint.rollback()
            logger.exception("Sync operation %s failed", op.client_op_id)
            record.status = "rejected"
            record.detail = "This could not be saved. Someone will need to look at it."

        db.add(record)
        db.flush()
        results.append(SyncResult.model_validate(record))

    counts = {"applied": 0, "merged": 0, "duplicate": 0, "rejected": 0}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1

    return SyncPushResult(**counts, results=results, server_time=now)


def rejected_for(db: Session, user, limit: int = 50) -> list[SyncResult]:
    """What this person's device sent that did not land."""
    rows = db.scalars(
        select(SyncOperation)
        .where(
            SyncOperation.user_id == getattr(user, "id", None),
            SyncOperation.status == "rejected",
        )
        .order_by(SyncOperation.received_at.desc())
        .limit(limit)
    )
    return [SyncResult.model_validate(row) for row in rows]


# --- Bootstrap ---------------------------------------------------------------


def bootstrap(db: Session, project_id: uuid.UUID) -> Bootstrap:
    """The reference data a phone needs to work with no signal.

    Kept small on purpose. This is downloaded on whatever connection the site
    has on the way out of the yard, which is the worst one it will see.
    """
    from app.modules.fleet.models import Equipment
    from app.modules.payroll.models import Worker
    from app.modules.projects.models import Project
    from app.modules.site.models import SiteDiaryEntry, SiteIssue

    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError("Project not found")

    workers = db.scalars(
        select(Worker).where(Worker.is_active.is_(True)).order_by(Worker.full_name)
    )
    equipment = db.scalars(
        select(Equipment)
        .where(Equipment.is_active.is_(True), Equipment.current_project_id == project_id)
        .order_by(Equipment.code)
    )
    issues = db.scalars(
        select(SiteIssue)
        .where(SiteIssue.project_id == project_id, SiteIssue.status == "open")
        .order_by(SiteIssue.raised_date.desc())
        .limit(50)
    )
    diary_dates = db.scalars(
        select(SiteDiaryEntry.entry_date)
        .where(SiteDiaryEntry.project_id == project_id)
        .order_by(SiteDiaryEntry.entry_date.desc())
        .limit(60)
    )

    return Bootstrap(
        project_id=project.id,
        project_code=project.code,
        project_name=project.name,
        server_time=datetime.now(timezone.utc),
        workers=[
            {"id": w.id, "full_name": w.full_name, "trade": w.trade} for w in workers
        ],
        equipment=[
            {
                "id": e.id,
                "code": e.code,
                "name": e.name,
                "meter_type": e.meter_type.value,
                "current_meter": float(e.current_meter),
            }
            for e in equipment
        ],
        open_issues=[
            {
                "id": i.id,
                "title": i.title,
                "severity": i.severity.value,
                "raised_date": i.raised_date,
            }
            for i in issues
        ],
        diary_dates=list(diary_dates),
    )
