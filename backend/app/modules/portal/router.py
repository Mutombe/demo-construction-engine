import uuid

from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse

from app.common.enums import UserRole
from app.core.deps import DbDep, require_roles
from app.modules.portal import service
from app.modules.portal.deps import PortalClient
from app.modules.portal.schemas import (
    PortalLinkCreate,
    PortalLinkCreated,
    PortalLinkRead,
    PortalPhotoTimeline,
    PortalProjectDetail,
    PortalSummary,
    PortalValuation,
)
from app.modules.valuations.pdf import certificate_pdf

# --- Staff-side management (mounted under the protected router) --------------

links_router = APIRouter(tags=["portal-links"])
link_admin = require_roles(UserRole.project_manager)


@links_router.post(
    "/clients/{client_id}/portal-links", response_model=PortalLinkCreated, status_code=201
)
def create_portal_link(
    client_id: uuid.UUID, body: PortalLinkCreate, db: DbDep, user=Depends(link_admin)
) -> PortalLinkCreated:
    token, raw = service.create_link(db, client_id, body, user.id)
    base = PortalLinkRead.model_validate(token)
    return PortalLinkCreated(**base.model_dump(), token=raw, url=service.portal_url(raw))


@links_router.get(
    "/clients/{client_id}/portal-links",
    response_model=list[PortalLinkRead],
    dependencies=[Depends(link_admin)],
)
def list_portal_links(client_id: uuid.UUID, db: DbDep) -> list[PortalLinkRead]:
    return [PortalLinkRead.model_validate(t) for t in service.list_links(db, client_id)]


@links_router.post(
    "/portal-links/{link_id}/revoke",
    response_model=PortalLinkRead,
    dependencies=[Depends(link_admin)],
)
def revoke_portal_link(link_id: uuid.UUID, db: DbDep) -> PortalLinkRead:
    return PortalLinkRead.model_validate(service.revoke_link(db, link_id))


# --- Client-facing portal (own router group; X-Portal-Token auth) ------------

portal_router = APIRouter(prefix="/portal", tags=["portal"])


@portal_router.get("/summary", response_model=PortalSummary)
def portal_summary(db: DbDep, client: PortalClient) -> PortalSummary:
    return service.summary(db, client)


@portal_router.get("/projects/{project_id}", response_model=PortalProjectDetail)
def portal_project_detail(
    project_id: uuid.UUID, db: DbDep, client: PortalClient
) -> PortalProjectDetail:
    return service.project_detail(db, client, project_id)


@portal_router.get("/projects/{project_id}/valuations", response_model=list[PortalValuation])
def portal_project_valuations(
    project_id: uuid.UUID, db: DbDep, client: PortalClient
) -> list[PortalValuation]:
    return service.project_valuations(db, client, project_id)


@portal_router.get("/valuations/{valuation_id}/certificate")
def portal_valuation_certificate(
    valuation_id: uuid.UUID, db: DbDep, client: PortalClient
) -> Response:
    valuation = service.own_valuation(db, client, valuation_id)
    return Response(
        content=certificate_pdf(db, valuation),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{valuation.doc_number}_certificate.pdf"'
        },
    )


@portal_router.get(
    "/projects/{project_id}/photos", response_model=PortalPhotoTimeline
)
def portal_project_photos(
    project_id: uuid.UUID, db: DbDep, client: PortalClient
) -> PortalPhotoTimeline:
    return service.project_photos(db, client, project_id)


@portal_router.get("/photos/{media_id}/file")
def portal_photo_file(
    media_id: uuid.UUID, db: DbDep, client: PortalClient, thumb: bool = False
) -> FileResponse:
    """Images are served through the token like everything else here, never
    from a public static mount."""
    from app.modules.media import service as media_service

    media = service.own_photo(db, client, media_id)
    path = media_service.resolve_path(media, thumbnail=thumb)
    return FileResponse(path, media_type=media.media_type)
