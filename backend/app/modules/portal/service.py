import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import ValuationStatus
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.modules.clients.models import Client
from app.modules.company.models import CompanySettings
from app.modules.portal.models import ClientAccessToken
from app.modules.portal.schemas import (
    PortalLinkCreate,
    PortalPhase,
    PortalProjectDetail,
    PortalProjectSummary,
    PortalSummary,
    PortalValuation,
)
from app.modules.projects.models import Project
from app.modules.projects.service import project_progress_pct
from app.modules.valuations.models import Valuation

VISIBLE_STATUSES = (ValuationStatus.issued, ValuationStatus.paid)


# --- Staff-side link management ---------------------------------------------


def create_link(
    db: Session, client_id: uuid.UUID, data: PortalLinkCreate, created_by: uuid.UUID
) -> tuple[ClientAccessToken, str]:
    client = db.get(Client, client_id)
    if client is None:
        raise NotFoundError("Client not found")
    raw = secrets.token_urlsafe(32)
    token = ClientAccessToken(
        client_id=client_id,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        label=data.label,
        expires_at=datetime.now(UTC) + timedelta(days=data.expires_in_days),
        created_by=created_by,
    )
    db.add(token)
    db.flush()
    return token, raw


def portal_url(raw_token: str) -> str:
    origin = settings.cors_origins[0] if settings.cors_origins else ""
    return f"{origin}/portal/{raw_token}"


def list_links(db: Session, client_id: uuid.UUID) -> list[ClientAccessToken]:
    if db.get(Client, client_id) is None:
        raise NotFoundError("Client not found")
    return list(
        db.scalars(
            select(ClientAccessToken)
            .where(ClientAccessToken.client_id == client_id)
            .order_by(ClientAccessToken.created_at.desc())
        )
    )


def revoke_link(db: Session, link_id: uuid.UUID) -> ClientAccessToken:
    token = db.get(ClientAccessToken, link_id)
    if token is None:
        raise NotFoundError("Portal link not found")
    if token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
    return token


# --- Client-facing reads ------------------------------------------------------


def _project_summary(db: Session, project: Project) -> PortalProjectSummary:
    return PortalProjectSummary(
        id=project.id,
        code=project.code,
        name=project.name,
        status=project.status,
        city=project.city,
        planned_start=project.planned_start,
        planned_end=project.planned_end,
        contract_value=project.contract_value,
        progress_pct=project_progress_pct(db, project.id),
    )


def summary(db: Session, client: Client) -> PortalSummary:
    company = db.scalar(select(CompanySettings).limit(1))
    projects = list(
        db.scalars(
            select(Project)
            .where(Project.client_id == client.id)
            .order_by(Project.created_at.desc())
        )
    )
    return PortalSummary(
        client_name=client.name,
        company_name=company.name if company else "Construction ERP",
        projects=[_project_summary(db, p) for p in projects],
    )


def _own_project(db: Session, client: Client, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.client_id != client.id:
        raise NotFoundError("Project not found")
    return project


def project_detail(db: Session, client: Client, project_id: uuid.UUID) -> PortalProjectDetail:
    project = _own_project(db, client, project_id)
    base = _project_summary(db, project)
    phases = sorted(project.phases, key=lambda p: p.sequence)
    return PortalProjectDetail(
        **base.model_dump(),
        description=project.description,
        site_address=project.site_address,
        actual_start=project.actual_start,
        phases=[
            PortalPhase(
                name=p.name,
                sequence=p.sequence,
                status=p.status,
                planned_start=p.planned_start,
                planned_end=p.planned_end,
            )
            for p in phases
        ],
    )


def project_valuations(
    db: Session, client: Client, project_id: uuid.UUID
) -> list[PortalValuation]:
    project = _own_project(db, client, project_id)
    valuations = db.scalars(
        select(Valuation)
        .where(Valuation.project_id == project.id, Valuation.status.in_(VISIBLE_STATUSES))
        .order_by(Valuation.valuation_number)
    )
    return [PortalValuation.model_validate(v) for v in valuations]


def own_valuation(db: Session, client: Client, valuation_id: uuid.UUID) -> Valuation:
    valuation = db.get(Valuation, valuation_id)
    if valuation is None or valuation.status not in VISIBLE_STATUSES:
        raise NotFoundError("Valuation not found")
    _own_project(db, client, valuation.project_id)
    return valuation


def project_photos(db: Session, client: Client, project_id: uuid.UUID):
    """Progress photos for one of the client's projects, oldest day first.

    Only the photos folder is ever reachable here — the same filter the staff
    timeline uses — so contracts, invoices and scanned delivery notes sitting
    in the same media library can never surface on a client link.
    """
    from app.modules.media import service as media_service
    from app.modules.portal.schemas import (
        PortalPhoto,
        PortalPhotoDay,
        PortalPhotoTimeline,
    )

    project = _own_project(db, client, project_id)
    timeline = media_service.photo_timeline(db, "project", project.id)
    days = [
        PortalPhotoDay(
            day=day.day,
            photos=[
                PortalPhoto(id=p.id, caption=p.caption, has_thumbnail=p.has_thumbnail)
                for p in day.photos
            ],
        )
        # Staff read newest-first to see what just happened; a client is
        # watching the building go up, so this runs the other way.
        for day in reversed(timeline.days)
    ]
    return PortalPhotoTimeline(
        project_id=project.id,
        total_photos=timeline.total_photos,
        first_photo=timeline.first_photo,
        last_photo=timeline.last_photo,
        days=days,
    )


def own_photo(db: Session, client: Client, media_id: uuid.UUID):
    """The guard for serving an image on a portal link.

    Checks the file is a progress photo, that it hangs off a project, and that
    the project is this client's. Without all three a link holder could walk
    media ids and read another client's files.
    """
    from app.common.enums import MediaFolder
    from app.modules.media.models import MediaFile

    media = db.get(MediaFile, media_id)
    if (
        media is None
        or media.folder != MediaFolder.photos
        or media.entity_type != "project"
    ):
        raise NotFoundError("Photo not found")
    _own_project(db, client, media.entity_id)
    return media
