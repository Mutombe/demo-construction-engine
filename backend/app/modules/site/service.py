import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import IssueSeverity, IssueStatus
from app.core.exceptions import ConflictError, NotFoundError
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
