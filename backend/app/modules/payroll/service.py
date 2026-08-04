import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.common.doc_numbers import next_doc_number
from app.common.enums import CostSource, PayItemKind, PayRunStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.costs.models import CostEntry
from app.modules.payroll.models import PayRun, PayRunLine, Timesheet, Worker, WorkerPayItem
from app.modules.payroll.schemas import (
    PayItemCreate,
    PayItemUpdate,
    PayRunCreate,
    TimesheetBulkCreate,
    TimesheetCreate,
    TimesheetUpdate,
    WorkerCreate,
    WorkerUpdate,
)
from app.modules.projects.models import Project
from app.modules.projects.service import get_project
from app.modules.admin import trash

CENT = Decimal("0.01")
OT_MULTIPLIER = Decimal("1.5")


# --- Workers ----------------------------------------------------------------


def list_workers(
    db: Session,
    page: int,
    page_size: int,
    search: str | None = None,
    include_inactive: bool = False,
) -> tuple[list[Worker], int]:
    query = select(Worker).options(joinedload(Worker.pay_items))
    if not include_inactive:
        query = query.where(Worker.is_active.is_(True))
    if search:
        pattern = f"%{search}%"
        query = query.where(Worker.full_name.ilike(pattern) | Worker.trade.ilike(pattern))
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    workers = list(
        db.scalars(
            query.order_by(Worker.full_name).offset((page - 1) * page_size).limit(page_size)
        ).unique()
    )
    return workers, total


def get_worker(db: Session, worker_id: uuid.UUID) -> Worker:
    worker = db.get(Worker, worker_id)
    if worker is None:
        raise NotFoundError("Worker not found")
    return worker


def create_worker(db: Session, data: WorkerCreate, created_by: uuid.UUID) -> Worker:
    worker = Worker(**data.model_dump(), created_by=created_by)
    db.add(worker)
    db.flush()
    return worker


def update_worker(db: Session, worker_id: uuid.UUID, data: WorkerUpdate) -> Worker:
    worker = get_worker(db, worker_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(worker, field, value)
    return worker


def add_pay_item(db: Session, worker_id: uuid.UUID, data: PayItemCreate) -> WorkerPayItem:
    worker = get_worker(db, worker_id)
    item = WorkerPayItem(worker_id=worker.id, **data.model_dump())
    db.add(item)
    db.flush()
    return item


def update_pay_item(db: Session, item_id: uuid.UUID, data: PayItemUpdate) -> WorkerPayItem:
    item = db.get(WorkerPayItem, item_id)
    if item is None:
        raise NotFoundError("Pay item not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    return item


def delete_pay_item(db: Session, item_id: uuid.UUID, user=None) -> None:
    item = db.get(WorkerPayItem, item_id)
    if item is None:
        raise NotFoundError("Pay item not found")
    trash.archive(db, item, entity_type="pay_item", label=item.label, user=user)
    db.delete(item)


# --- Timesheets -------------------------------------------------------------


def list_timesheets(
    db: Session,
    page: int,
    page_size: int,
    worker_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    date_from=None,
    date_to=None,
    unpaid_only: bool = False,
) -> tuple[list[Timesheet], int]:
    query = select(Timesheet)
    if worker_id is not None:
        query = query.where(Timesheet.worker_id == worker_id)
    if project_id is not None:
        query = query.where(Timesheet.project_id == project_id)
    if date_from is not None:
        query = query.where(Timesheet.work_date >= date_from)
    if date_to is not None:
        query = query.where(Timesheet.work_date <= date_to)
    if unpaid_only:
        query = query.where(Timesheet.pay_run_id.is_(None))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    sheets = list(
        db.scalars(
            query.order_by(Timesheet.work_date.desc(), Timesheet.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return sheets, total


def get_timesheet(db: Session, timesheet_id: uuid.UUID) -> Timesheet:
    sheet = db.get(Timesheet, timesheet_id)
    if sheet is None:
        raise NotFoundError("Timesheet not found")
    return sheet


def _require_unpaid(sheet: Timesheet) -> None:
    if sheet.pay_run_id is not None:
        raise ConflictError("This timesheet is on an approved pay run and cannot change")


def create_timesheet(db: Session, data: TimesheetCreate, created_by: uuid.UUID) -> Timesheet:
    get_worker(db, data.worker_id)
    get_project(db, data.project_id)
    existing = db.scalar(
        select(Timesheet).where(
            Timesheet.worker_id == data.worker_id,
            Timesheet.project_id == data.project_id,
            Timesheet.work_date == data.work_date,
        )
    )
    if existing is not None:
        raise ConflictError("This worker already has time on this project for that day")
    sheet = Timesheet(**data.model_dump(), created_by=created_by)
    db.add(sheet)
    db.flush()
    return sheet


def bulk_create_timesheets(
    db: Session, data: TimesheetBulkCreate, created_by: uuid.UUID
) -> list[Timesheet]:
    """Site day entry: upserts one row per worker; zero-quantity entries are
    skipped (or delete an existing unpaid row, letting the grid 'clear' a day)."""
    get_project(db, data.project_id)
    seen: set[uuid.UUID] = set()
    result: list[Timesheet] = []
    for entry in data.entries:
        if entry.worker_id in seen:
            raise ValidationFailedError("Duplicate worker in bulk entry")
        seen.add(entry.worker_id)
        get_worker(db, entry.worker_id)
        existing = db.scalar(
            select(Timesheet).where(
                Timesheet.worker_id == entry.worker_id,
                Timesheet.project_id == data.project_id,
                Timesheet.work_date == data.work_date,
            )
        )
        if entry.quantity == 0 and entry.overtime_quantity == 0:
            if existing is not None:
                _require_unpaid(existing)
                db.delete(existing)
            continue
        if existing is not None:
            _require_unpaid(existing)
            existing.quantity = entry.quantity
            existing.overtime_quantity = entry.overtime_quantity
            result.append(existing)
        else:
            sheet = Timesheet(
                worker_id=entry.worker_id,
                project_id=data.project_id,
                work_date=data.work_date,
                quantity=entry.quantity,
                overtime_quantity=entry.overtime_quantity,
                created_by=created_by,
            )
            db.add(sheet)
            result.append(sheet)
    db.flush()
    return result


def update_timesheet(db: Session, timesheet_id: uuid.UUID, data: TimesheetUpdate) -> Timesheet:
    sheet = get_timesheet(db, timesheet_id)
    _require_unpaid(sheet)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(sheet, field, value)
    return sheet


def delete_timesheet(db: Session, timesheet_id: uuid.UUID, user=None) -> None:
    sheet = get_timesheet(db, timesheet_id)
    _require_unpaid(sheet)
    trash.archive(
        db,
        sheet,
        entity_type="timesheet",
        label=f"{sheet.worker.full_name} on {sheet.work_date}",
        user=user,
    )
    db.delete(sheet)


# --- Pay runs ---------------------------------------------------------------


def list_pay_runs(db: Session, page: int, page_size: int) -> tuple[list[PayRun], int]:
    total = db.scalar(select(func.count()).select_from(PayRun)) or 0
    runs = list(
        db.scalars(
            select(PayRun)
            .options(joinedload(PayRun.lines))
            .order_by(PayRun.period_end.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).unique()
    )
    return runs, total


def get_pay_run(db: Session, pay_run_id: uuid.UUID) -> PayRun:
    run = db.scalar(
        select(PayRun).options(joinedload(PayRun.lines)).where(PayRun.id == pay_run_id)
    )
    if run is None:
        raise NotFoundError("Pay run not found")
    return run


def create_pay_run(db: Session, data: PayRunCreate, created_by: uuid.UUID) -> PayRun:
    if data.period_end < data.period_start:
        raise ValidationFailedError("Period end must be on or after period start")
    if db.scalar(select(PayRun).where(PayRun.status == PayRunStatus.draft)):
        raise ConflictError("A draft pay run already exists — approve or delete it first")
    overlap = db.scalar(
        select(PayRun).where(
            PayRun.status == PayRunStatus.approved,
            PayRun.period_start <= data.period_end,
            PayRun.period_end >= data.period_start,
        )
    )
    if overlap is not None:
        raise ConflictError(f"Period overlaps approved pay run {overlap.doc_number}")

    run = PayRun(
        doc_number=next_doc_number(db, PayRun, "PAY"),
        period_start=data.period_start,
        period_end=data.period_end,
        notes=data.notes,
        created_by=created_by,
    )
    db.add(run)
    db.flush()
    _generate_lines(db, run)
    return get_pay_run(db, run.id)


def regenerate_pay_run(db: Session, pay_run_id: uuid.UUID) -> PayRun:
    run = get_pay_run(db, pay_run_id)
    if run.status != PayRunStatus.draft:
        raise ConflictError("Only draft pay runs can be regenerated")
    _generate_lines(db, run)
    return get_pay_run(db, run.id)


def delete_pay_run(db: Session, pay_run_id: uuid.UUID, user=None) -> None:
    run = get_pay_run(db, pay_run_id)
    if run.status != PayRunStatus.draft:
        raise ConflictError("Only draft pay runs can be deleted")
    trash.archive(
        db,
        run,
        entity_type="pay_run",
        label=f"{run.doc_number} ({run.period_start} to {run.period_end})",
        user=user,
    )
    db.delete(run)


def _unpaid_timesheets(db: Session, run: PayRun) -> list[Timesheet]:
    return list(
        db.scalars(
            select(Timesheet)
            .options(joinedload(Timesheet.worker).joinedload(Worker.pay_items))
            .where(
                Timesheet.pay_run_id.is_(None),
                Timesheet.work_date >= run.period_start,
                Timesheet.work_date <= run.period_end,
            )
        ).unique()
    )


def _generate_lines(db: Session, run: PayRun) -> list[Timesheet]:
    """(Re)build lines from unpaid timesheets in the period. Returns the
    timesheets consumed so approve() can stamp exactly this set."""
    run.lines.clear()  # delete-orphan cascade removes old rows
    db.flush()

    sheets = _unpaid_timesheets(db, run)
    by_worker: dict[uuid.UUID, list[Timesheet]] = {}
    for sheet in sheets:
        by_worker.setdefault(sheet.worker_id, []).append(sheet)

    project_codes = {p.id: p.code for p in db.scalars(select(Project))}

    totals = {key: Decimal("0") for key in ("base", "ot", "allow", "deduct", "gross", "net")}
    for worker_sheets in sorted(by_worker.values(), key=lambda ws: ws[0].worker.full_name):
        worker = worker_sheets[0].worker
        qty = sum((s.quantity for s in worker_sheets), Decimal("0"))
        ot_qty = sum((s.overtime_quantity for s in worker_sheets), Decimal("0"))
        base = (qty * worker.rate).quantize(CENT)
        ot_pay = (ot_qty * worker.rate * OT_MULTIPLIER).quantize(CENT)

        items = [i for i in worker.pay_items if i.is_active]
        allowances = sum(
            (i.amount for i in items if i.kind == PayItemKind.allowance), Decimal("0")
        )
        deductions = sum(
            (i.amount for i in items if i.kind == PayItemKind.deduction), Decimal("0")
        )
        gross = base + ot_pay + allowances
        net = gross - deductions

        # Earned amount per project; allowances spread proportionally so the
        # allocation always sums exactly to gross (last project takes rounding).
        earned: dict[uuid.UUID, Decimal] = {}
        for sheet in worker_sheets:
            amount = (
                sheet.quantity * worker.rate
                + sheet.overtime_quantity * worker.rate * OT_MULTIPLIER
            )
            earned[sheet.project_id] = earned.get(sheet.project_id, Decimal("0")) + amount
        total_earned = sum(earned.values(), Decimal("0"))
        allocation: list[dict] = []
        remaining = gross
        project_ids = sorted(earned.keys(), key=lambda pid: project_codes.get(pid, ""))
        for i, project_id in enumerate(project_ids):
            if i == len(project_ids) - 1:
                share = remaining
            elif total_earned > 0:
                share = (gross * earned[project_id] / total_earned).quantize(CENT)
            else:
                share = Decimal("0")
            remaining -= share
            allocation.append(
                {
                    "project_id": str(project_id),
                    "project_code": project_codes.get(project_id, "?"),
                    "amount": str(share),
                }
            )

        run.lines.append(
            PayRunLine(
                worker_id=worker.id,
                worker_name=worker.full_name,
                trade=worker.trade,
                pay_basis=worker.pay_basis,
                rate=worker.rate,
                quantity=qty,
                overtime_quantity=ot_qty,
                base_pay=base,
                overtime_pay=ot_pay,
                allowance_total=allowances,
                deduction_total=deductions,
                gross_pay=gross,
                net_pay=net,
                pay_items=[
                    {"kind": i.kind.value, "label": i.label, "amount": str(i.amount)}
                    for i in items
                ],
                project_allocation=allocation,
            )
        )
        totals["base"] += base
        totals["ot"] += ot_pay
        totals["allow"] += allowances
        totals["deduct"] += deductions
        totals["gross"] += gross
        totals["net"] += net

    run.base_total = totals["base"]
    run.overtime_total = totals["ot"]
    run.allowance_total = totals["allow"]
    run.deduction_total = totals["deduct"]
    run.gross_total = totals["gross"]
    run.net_total = totals["net"]
    db.flush()
    return sheets


def approve_pay_run(db: Session, pay_run_id: uuid.UUID, approver_id: uuid.UUID) -> PayRun:
    run = get_pay_run(db, pay_run_id)
    if run.status != PayRunStatus.draft:
        raise ConflictError("This pay run is already approved")

    # Defensive recompute so timesheets added after the draft was built are
    # either included or excluded consistently with what gets stamped.
    sheets = _generate_lines(db, run)
    if not sheets:
        raise ValidationFailedError("No unpaid timesheets fall in this period")

    per_project: dict[str, Decimal] = {}
    for line in run.lines:
        for alloc in line.project_allocation or []:
            per_project[alloc["project_id"]] = per_project.get(
                alloc["project_id"], Decimal("0")
            ) + Decimal(alloc["amount"])

    for project_id, amount in per_project.items():
        if amount == 0:
            continue
        db.add(
            CostEntry(
                project_id=uuid.UUID(project_id),
                entry_date=run.period_end,
                description=f"Pay run {run.doc_number}: site labour",
                amount=amount,
                source=CostSource.payroll,
                reference=run.doc_number,
                created_by=approver_id,
            )
        )

    for sheet in sheets:
        sheet.pay_run_id = run.id

    run.status = PayRunStatus.approved
    run.approved_by = approver_id
    run.approved_at = datetime.now(UTC)
    db.flush()

    from app.common.enums import UserRole
    from app.modules.notifications import service as notifications

    notifications.notify_roles(
        db,
        [UserRole.admin],
        "pay_run_approved",
        f"Pay run {run.doc_number} approved",
        f"Gross {run.gross_total} across {len(run.lines)} workers",
        link=f"/payroll/runs/{run.id}",
        exclude=approver_id,
    )
    return get_pay_run(db, run.id)
