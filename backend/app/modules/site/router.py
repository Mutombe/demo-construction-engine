import uuid
from datetime import date

from fastapi import APIRouter, Depends

from app.common.enums import IssueSeverity, IssueStatus, UserRole
from app.common.pagination import PageParamsDep
from app.common.schemas import Page
from app.core.deps import DbDep, require_roles
from app.modules.site import service
from app.modules.site.schemas import (
    DiaryEntryCreate,
    DiaryEntryRead,
    DiaryEntryUpdate,
    DiaryLabourSet,
    SiteIssueCreate,
    SiteIssueRead,
    SiteIssueResolve,
    SiteIssueUpdate,
    TimesheetPushResult,
)

router = APIRouter(tags=["site"])

site_write = Depends(require_roles(UserRole.site_manager, UserRole.project_manager))
site_user = require_roles(UserRole.site_manager, UserRole.project_manager)


@router.get("/projects/{project_id}/diary", response_model=Page[DiaryEntryRead])
def list_diary_entries(
    project_id: uuid.UUID,
    db: DbDep,
    params: PageParamsDep,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Page[DiaryEntryRead]:
    entries, total = service.list_diary_entries(
        db, project_id, params.page, params.page_size, date_from, date_to
    )
    return Page(
        items=[DiaryEntryRead.model_validate(e) for e in entries],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/projects/{project_id}/diary", response_model=DiaryEntryRead, status_code=201)
def create_diary_entry(
    project_id: uuid.UUID, body: DiaryEntryCreate, db: DbDep, user=Depends(site_user)
) -> DiaryEntryRead:
    return DiaryEntryRead.model_validate(service.create_diary_entry(db, project_id, body, user.id))


@router.get("/diary/{entry_id}", response_model=DiaryEntryRead)
def get_diary_entry(entry_id: uuid.UUID, db: DbDep) -> DiaryEntryRead:
    return service.diary_entry_read(db, service.get_diary_entry(db, entry_id))


@router.put("/diary/{entry_id}/labour", response_model=DiaryEntryRead,
            dependencies=[site_write])
def set_diary_labour(entry_id: uuid.UUID, body: DiaryLabourSet, db: DbDep) -> DiaryEntryRead:
    return service.diary_entry_read(db, service.set_diary_labour(db, entry_id, body))


@router.post("/diary/{entry_id}/push-timesheets", response_model=TimesheetPushResult)
def push_diary_labour_to_timesheets(
    entry_id: uuid.UUID, db: DbDep, user=Depends(site_user)
) -> TimesheetPushResult:
    """Turn the day's diary labour into timesheets so the same fact is only
    ever entered once."""
    return service.push_diary_labour_to_timesheets(db, entry_id, user.id)


@router.patch("/diary/{entry_id}", response_model=DiaryEntryRead, dependencies=[site_write])
def update_diary_entry(entry_id: uuid.UUID, body: DiaryEntryUpdate, db: DbDep) -> DiaryEntryRead:
    return DiaryEntryRead.model_validate(service.update_diary_entry(db, entry_id, body))


@router.delete("/diary/{entry_id}", status_code=204, dependencies=[site_write])
def delete_diary_entry(entry_id: uuid.UUID, db: DbDep) -> None:
    service.delete_diary_entry(db, entry_id)


@router.get("/projects/{project_id}/issues", response_model=Page[SiteIssueRead])
def list_site_issues(
    project_id: uuid.UUID,
    db: DbDep,
    params: PageParamsDep,
    status: IssueStatus | None = None,
    severity: IssueSeverity | None = None,
) -> Page[SiteIssueRead]:
    issues, total = service.list_issues(
        db, project_id, params.page, params.page_size, status, severity
    )
    return Page(
        items=[SiteIssueRead.model_validate(i) for i in issues],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/projects/{project_id}/issues", response_model=SiteIssueRead, status_code=201)
def create_site_issue(
    project_id: uuid.UUID, body: SiteIssueCreate, db: DbDep, user=Depends(site_user)
) -> SiteIssueRead:
    return SiteIssueRead.model_validate(service.create_issue(db, project_id, body, user.id))


@router.get("/issues/{issue_id}", response_model=SiteIssueRead)
def get_site_issue(issue_id: uuid.UUID, db: DbDep) -> SiteIssueRead:
    return SiteIssueRead.model_validate(service.get_issue(db, issue_id))


@router.patch("/issues/{issue_id}", response_model=SiteIssueRead, dependencies=[site_write])
def update_site_issue(issue_id: uuid.UUID, body: SiteIssueUpdate, db: DbDep) -> SiteIssueRead:
    return SiteIssueRead.model_validate(service.update_issue(db, issue_id, body))


@router.post("/issues/{issue_id}/resolve", response_model=SiteIssueRead, dependencies=[site_write])
def resolve_site_issue(issue_id: uuid.UUID, body: SiteIssueResolve, db: DbDep) -> SiteIssueRead:
    return SiteIssueRead.model_validate(service.resolve_issue(db, issue_id, body))


@router.post("/issues/{issue_id}/reopen", response_model=SiteIssueRead, dependencies=[site_write])
def reopen_site_issue(issue_id: uuid.UUID, db: DbDep) -> SiteIssueRead:
    return SiteIssueRead.model_validate(service.reopen_issue(db, issue_id))
