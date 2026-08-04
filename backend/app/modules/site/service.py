import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import IssueSeverity, IssueStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.projects.service import get_project
from app.modules.site.models import SiteDiaryEntry, SiteIssue
from app.modules.site.schemas import (
    DiaryEntryCreate,
    DiaryEntryUpdate,
    SiteIssueCreate,
    SiteIssueResolve,
    SiteIssueUpdate,
)

# --- Diary ------------------------------------------------------------------


def list_diary_entries(
    db: Session,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[list[SiteDiaryEntry], int]:
    get_project(db, project_id)
    query = select(SiteDiaryEntry).where(SiteDiaryEntry.project_id == project_id)
    if date_from:
        query = query.where(SiteDiaryEntry.entry_date >= date_from)
    if date_to:
        query = query.where(SiteDiaryEntry.entry_date <= date_to)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    entries = list(
        db.scalars(
            query.order_by(SiteDiaryEntry.entry_date.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return entries, total


def get_diary_entry(db: Session, entry_id: uuid.UUID) -> SiteDiaryEntry:
    entry = db.get(SiteDiaryEntry, entry_id)
    if entry is None:
        raise NotFoundError("Diary entry not found")
    return entry


def _check_date_free(
    db: Session,
    project_id: uuid.UUID,
    entry_date: date,
    exclude_id: uuid.UUID | None = None,
) -> None:
    query = select(SiteDiaryEntry.id).where(
        SiteDiaryEntry.project_id == project_id, SiteDiaryEntry.entry_date == entry_date
    )
    if exclude_id:
        query = query.where(SiteDiaryEntry.id != exclude_id)
    if db.scalar(query):
        raise ConflictError("A diary entry already exists for this date")


def create_diary_entry(
    db: Session, project_id: uuid.UUID, data: DiaryEntryCreate, created_by: uuid.UUID
) -> SiteDiaryEntry:
    get_project(db, project_id)
    _check_date_free(db, project_id, data.entry_date)
    entry = SiteDiaryEntry(**data.model_dump(), project_id=project_id, created_by=created_by)
    db.add(entry)
    db.flush()
    return entry


def update_diary_entry(db: Session, entry_id: uuid.UUID, data: DiaryEntryUpdate) -> SiteDiaryEntry:
    entry = get_diary_entry(db, entry_id)
    updates = data.model_dump(exclude_unset=True)
    if "entry_date" in updates and updates["entry_date"] != entry.entry_date:
        _check_date_free(db, entry.project_id, updates["entry_date"], exclude_id=entry.id)
    for field, value in updates.items():
        setattr(entry, field, value)
    return entry


def delete_diary_entry(db: Session, entry_id: uuid.UUID) -> None:
    db.delete(get_diary_entry(db, entry_id))


# --- Issues -----------------------------------------------------------------


def list_issues(
    db: Session,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    status: IssueStatus | None = None,
    severity: IssueSeverity | None = None,
) -> tuple[list[SiteIssue], int]:
    get_project(db, project_id)
    query = select(SiteIssue).where(SiteIssue.project_id == project_id)
    if status is not None:
        query = query.where(SiteIssue.status == status)
    if severity is not None:
        query = query.where(SiteIssue.severity == severity)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    issues = list(
        db.scalars(
            query.order_by(SiteIssue.raised_date.desc(), SiteIssue.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return issues, total


def get_issue(db: Session, issue_id: uuid.UUID) -> SiteIssue:
    issue = db.get(SiteIssue, issue_id)
    if issue is None:
        raise NotFoundError("Site issue not found")
    return issue


def create_issue(
    db: Session, project_id: uuid.UUID, data: SiteIssueCreate, created_by: uuid.UUID
) -> SiteIssue:
    get_project(db, project_id)
    issue = SiteIssue(
        project_id=project_id,
        title=data.title,
        description=data.description,
        severity=data.severity,
        raised_date=data.raised_date or date.today(),
        created_by=created_by,
    )
    db.add(issue)
    db.flush()
    return issue


def update_issue(db: Session, issue_id: uuid.UUID, data: SiteIssueUpdate) -> SiteIssue:
    issue = get_issue(db, issue_id)
    if issue.status != IssueStatus.open:
        raise ConflictError("Resolved issues cannot be edited; reopen it first")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(issue, field, value)
    return issue


def resolve_issue(db: Session, issue_id: uuid.UUID, data: SiteIssueResolve) -> SiteIssue:
    issue = get_issue(db, issue_id)
    if issue.status != IssueStatus.open:
        raise ConflictError("Issue is already resolved")
    issue.status = IssueStatus.resolved
    issue.resolved_date = data.resolved_date or date.today()
    issue.resolution_notes = data.resolution_notes
    return issue


def reopen_issue(db: Session, issue_id: uuid.UUID) -> SiteIssue:
    issue = get_issue(db, issue_id)
    if issue.status != IssueStatus.resolved:
        raise ConflictError("Issue is already open")
    issue.status = IssueStatus.open
    issue.resolved_date = None
    issue.resolution_notes = None
    return issue


# --- Diary labour -> timesheets ---------------------------------------------


def diary_labour_read(line):
    from app.modules.site.schemas import DiaryLabourRead

    read = DiaryLabourRead.model_validate(line)
    if line.worker:
        read.worker_name = line.worker.full_name
        read.trade = line.worker.trade
    return read


def _timesheets_exist(db: Session, entry) -> bool:
    """Have this diary's labour lines already been pushed to payroll?"""
    from app.modules.payroll.models import Timesheet

    worker_ids = [line.worker_id for line in entry.labour]
    if not worker_ids:
        return False
    count = db.scalar(
        select(func.count())
        .select_from(Timesheet)
        .where(
            Timesheet.project_id == entry.project_id,
            Timesheet.work_date == entry.entry_date,
            Timesheet.worker_id.in_(worker_ids),
        )
    ) or 0
    return count == len(worker_ids)


def diary_entry_read(db: Session, entry):
    from app.modules.site.schemas import DiaryEntryRead

    read = DiaryEntryRead.model_validate(entry)
    read.labour = [diary_labour_read(line) for line in entry.labour]
    read.timesheets_pushed = _timesheets_exist(db, entry)
    return read


def set_diary_labour(db: Session, entry_id: uuid.UUID, data):
    """Replace the day's labour list. Headcount follows the list so the two
    can never disagree."""
    from app.modules.payroll.service import get_worker
    from app.modules.site.models import SiteDiaryLabour

    entry = get_diary_entry(db, entry_id)
    seen: set[uuid.UUID] = set()
    entry.labour.clear()
    db.flush()  # release the unique (entry, worker) keys before re-inserting
    for spec in data.lines:
        if spec.worker_id in seen:
            raise ValidationFailedError("The same worker is listed twice")
        seen.add(spec.worker_id)
        get_worker(db, spec.worker_id)
        if spec.quantity == 0 and spec.overtime_quantity == 0:
            continue
        entry.labour.append(
            SiteDiaryLabour(
                worker_id=spec.worker_id,
                quantity=spec.quantity,
                overtime_quantity=spec.overtime_quantity,
                notes=spec.notes,
            )
        )
    entry.labour_headcount = len(entry.labour)
    db.flush()
    return entry


def push_diary_labour_to_timesheets(db: Session, entry_id: uuid.UUID, user_id: uuid.UUID):
    """Create timesheets from the diary's labour lines — one entry, not two.

    Time already locked into an approved pay run is left alone and reported
    back rather than silently skipped or, worse, overwritten.
    """
    from app.modules.payroll.models import Timesheet
    from app.modules.payroll.schemas import BulkEntry, TimesheetBulkCreate
    from app.modules.payroll.service import bulk_create_timesheets
    from app.modules.site.schemas import TimesheetPushResult

    entry = get_diary_entry(db, entry_id)
    if not entry.labour:
        raise ValidationFailedError("No labour recorded on this diary entry")

    existing = {
        sheet.worker_id: sheet
        for sheet in db.scalars(
            select(Timesheet).where(
                Timesheet.project_id == entry.project_id,
                Timesheet.work_date == entry.entry_date,
            )
        )
    }
    locked, pushable = [], []
    for line in entry.labour:
        sheet = existing.get(line.worker_id)
        if sheet is not None and sheet.pay_run_id is not None:
            locked.append(line.worker.full_name if line.worker else str(line.worker_id))
            continue
        pushable.append(line)

    created = sum(1 for line in pushable if line.worker_id not in existing)
    updated = len(pushable) - created
    if pushable:
        bulk_create_timesheets(
            db,
            TimesheetBulkCreate(
                project_id=entry.project_id,
                work_date=entry.entry_date,
                entries=[
                    BulkEntry(
                        worker_id=line.worker_id,
                        quantity=line.quantity,
                        overtime_quantity=line.overtime_quantity,
                    )
                    for line in pushable
                ],
            ),
            user_id,
        )
    return TimesheetPushResult(
        diary_entry_id=entry.id,
        created=created,
        updated=updated,
        skipped_locked=locked,
    )
