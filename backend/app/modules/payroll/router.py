import uuid
from datetime import date

from fastapi import APIRouter, Depends, Response

from app.common.enums import UserRole
from app.common.pagination import PageParamsDep
from app.common.schemas import Page
from app.core.deps import DbDep, require_roles
from app.modules.payroll import service
from app.modules.payroll.models import Timesheet
from app.modules.payroll.schemas import (
    PayItemCreate,
    PayItemRead,
    PayItemUpdate,
    PayRunCreate,
    PayRunDetail,
    PayRunRead,
    TimesheetBulkCreate,
    TimesheetCreate,
    TimesheetRead,
    TimesheetUpdate,
    WorkerCreate,
    WorkerRead,
    WorkerUpdate,
)
from app.modules.projects.models import Project

router = APIRouter(tags=["payroll"])

# Payroll data is sensitive: nothing here is viewer-readable. Pay runs and
# worker administration are PM-only; site managers enter and read timesheets
# (and need the worker list for the day-entry grid). Admin bypasses all.
pay_admin = require_roles(UserRole.project_manager)
timesheet_access = require_roles(UserRole.project_manager, UserRole.site_manager)


def _timesheet_read(db: DbDep, sheet: Timesheet) -> TimesheetRead:
    read = TimesheetRead.model_validate(sheet)
    worker = sheet.worker
    if worker is not None:
        read.worker_name = worker.full_name
        read.worker_trade = worker.trade
        read.pay_basis = worker.pay_basis
    project = db.get(Project, sheet.project_id)
    if project is not None:
        read.project_code = project.code
    return read


# --- Workers ----------------------------------------------------------------


@router.get("/workers", response_model=Page[WorkerRead], dependencies=[Depends(timesheet_access)])
def list_workers(
    db: DbDep,
    params: PageParamsDep,
    search: str | None = None,
    include_inactive: bool = False,
) -> Page[WorkerRead]:
    workers, total = service.list_workers(
        db, params.page, params.page_size, search, include_inactive
    )
    return Page(
        items=[WorkerRead.model_validate(w) for w in workers],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/workers", response_model=WorkerRead, status_code=201)
def create_worker(body: WorkerCreate, db: DbDep, user=Depends(pay_admin)) -> WorkerRead:
    return WorkerRead.model_validate(service.create_worker(db, body, user.id))


@router.get(
    "/workers/{worker_id}", response_model=WorkerRead, dependencies=[Depends(timesheet_access)]
)
def get_worker(worker_id: uuid.UUID, db: DbDep) -> WorkerRead:
    return WorkerRead.model_validate(service.get_worker(db, worker_id))


@router.patch("/workers/{worker_id}", response_model=WorkerRead, dependencies=[Depends(pay_admin)])
def update_worker(worker_id: uuid.UUID, body: WorkerUpdate, db: DbDep) -> WorkerRead:
    return WorkerRead.model_validate(service.update_worker(db, worker_id, body))


@router.post(
    "/workers/{worker_id}/pay-items",
    response_model=PayItemRead,
    status_code=201,
    dependencies=[Depends(pay_admin)],
)
def add_worker_pay_item(worker_id: uuid.UUID, body: PayItemCreate, db: DbDep) -> PayItemRead:
    return PayItemRead.model_validate(service.add_pay_item(db, worker_id, body))


@router.patch("/pay-items/{item_id}", response_model=PayItemRead, dependencies=[Depends(pay_admin)])
def update_worker_pay_item(item_id: uuid.UUID, body: PayItemUpdate, db: DbDep) -> PayItemRead:
    return PayItemRead.model_validate(service.update_pay_item(db, item_id, body))


@router.delete("/pay-items/{item_id}", status_code=204, dependencies=[Depends(pay_admin)])
def delete_worker_pay_item(item_id: uuid.UUID, db: DbDep) -> None:
    service.delete_pay_item(db, item_id)


# --- Timesheets -------------------------------------------------------------


@router.get(
    "/timesheets", response_model=Page[TimesheetRead], dependencies=[Depends(timesheet_access)]
)
def list_timesheets(
    db: DbDep,
    params: PageParamsDep,
    worker_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    unpaid_only: bool = False,
) -> Page[TimesheetRead]:
    sheets, total = service.list_timesheets(
        db, params.page, params.page_size, worker_id, project_id, date_from, date_to, unpaid_only
    )
    return Page(
        items=[_timesheet_read(db, s) for s in sheets],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/timesheets", response_model=TimesheetRead, status_code=201)
def create_timesheet(
    body: TimesheetCreate, db: DbDep, user=Depends(timesheet_access)
) -> TimesheetRead:
    return _timesheet_read(db, service.create_timesheet(db, body, user.id))


@router.post("/timesheets/bulk", response_model=list[TimesheetRead], status_code=201)
def bulk_create_timesheets(
    body: TimesheetBulkCreate, db: DbDep, user=Depends(timesheet_access)
) -> list[TimesheetRead]:
    return [_timesheet_read(db, s) for s in service.bulk_create_timesheets(db, body, user.id)]


@router.patch(
    "/timesheets/{timesheet_id}",
    response_model=TimesheetRead,
    dependencies=[Depends(timesheet_access)],
)
def update_timesheet(timesheet_id: uuid.UUID, body: TimesheetUpdate, db: DbDep) -> TimesheetRead:
    return _timesheet_read(db, service.update_timesheet(db, timesheet_id, body))


@router.delete(
    "/timesheets/{timesheet_id}", status_code=204, dependencies=[Depends(timesheet_access)]
)
def delete_timesheet(timesheet_id: uuid.UUID, db: DbDep) -> None:
    service.delete_timesheet(db, timesheet_id)


# --- Pay runs ---------------------------------------------------------------


def _run_read(run) -> PayRunRead:
    read = PayRunRead.model_validate(run)
    read.line_count = len(run.lines)
    return read


def _run_detail(run) -> PayRunDetail:
    detail = PayRunDetail.model_validate(run)
    detail.line_count = len(run.lines)
    return detail


@router.get("/pay-runs", response_model=Page[PayRunRead], dependencies=[Depends(pay_admin)])
def list_pay_runs(db: DbDep, params: PageParamsDep) -> Page[PayRunRead]:
    runs, total = service.list_pay_runs(db, params.page, params.page_size)
    return Page(
        items=[_run_read(r) for r in runs],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/pay-runs", response_model=PayRunDetail, status_code=201)
def create_pay_run(body: PayRunCreate, db: DbDep, user=Depends(pay_admin)) -> PayRunDetail:
    return _run_detail(service.create_pay_run(db, body, user.id))


@router.get(
    "/pay-runs/{pay_run_id}", response_model=PayRunDetail, dependencies=[Depends(pay_admin)]
)
def get_pay_run(pay_run_id: uuid.UUID, db: DbDep) -> PayRunDetail:
    return _run_detail(service.get_pay_run(db, pay_run_id))


@router.post(
    "/pay-runs/{pay_run_id}/regenerate",
    response_model=PayRunDetail,
    dependencies=[Depends(pay_admin)],
)
def regenerate_pay_run(pay_run_id: uuid.UUID, db: DbDep) -> PayRunDetail:
    return _run_detail(service.regenerate_pay_run(db, pay_run_id))


@router.post("/pay-runs/{pay_run_id}/approve", response_model=PayRunDetail)
def approve_pay_run(pay_run_id: uuid.UUID, db: DbDep, user=Depends(pay_admin)) -> PayRunDetail:
    return _run_detail(service.approve_pay_run(db, pay_run_id, user.id))


@router.delete("/pay-runs/{pay_run_id}", status_code=204, dependencies=[Depends(pay_admin)])
def delete_pay_run(pay_run_id: uuid.UUID, db: DbDep) -> None:
    service.delete_pay_run(db, pay_run_id)


def _pdf_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/pay-runs/{pay_run_id}/payslips", dependencies=[Depends(pay_admin)])
def download_payslips(pay_run_id: uuid.UUID, db: DbDep) -> Response:
    from app.modules.payroll.pdf import payslips_pdf

    run = service.get_pay_run(db, pay_run_id)
    return _pdf_response(payslips_pdf(db, run), f"{run.doc_number}_payslips.pdf")


@router.get("/pay-runs/{pay_run_id}/lines/{line_id}/payslip", dependencies=[Depends(pay_admin)])
def download_payslip(pay_run_id: uuid.UUID, line_id: uuid.UUID, db: DbDep) -> Response:
    from app.core.exceptions import NotFoundError
    from app.modules.payroll.pdf import payslip_pdf

    run = service.get_pay_run(db, pay_run_id)
    line = next((ln for ln in run.lines if ln.id == line_id), None)
    if line is None:
        raise NotFoundError("Pay run line not found")
    slug = line.worker_name.replace(" ", "_")
    return _pdf_response(payslip_pdf(db, run, line), f"{run.doc_number}_{slug}.pdf")
