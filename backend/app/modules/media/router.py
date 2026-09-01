import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.common.enums import MediaFolder, UserRole
from app.common.pagination import PageParamsDep
from app.common.schemas import Page
from sqlalchemy import select

from app.core.deps import CurrentUser, DbDep, require_roles
from app.modules.media import service
from app.modules.media.models import MediaFile
from app.modules.media.schemas import FolderCounts, MediaRead, MediaUpdate, PhotoTimeline

router = APIRouter(prefix="/media", tags=["media"])

media_write = require_roles(
    UserRole.project_manager, UserRole.site_manager, UserRole.procurement_officer
)


def _read(media: MediaFile) -> MediaRead:
    read = MediaRead.model_validate(media)
    read.has_thumbnail = bool(media.thumb_path)
    return read


@router.post("", response_model=MediaRead, status_code=201)
async def upload_media(
    db: DbDep,
    file: UploadFile = File(...),
    entity_type: str = Form(...),
    entity_id: uuid.UUID = Form(...),
    folder: MediaFolder = Form(default=MediaFolder.other),
    caption: str | None = Form(default=None),
    # Supplied by a device that captured the photo offline. Makes the
    # upload safe to retry: a dropped connection costs a wasted request,
    # never a second copy of the same photograph.
    client_op_id: uuid.UUID | None = Form(default=None),
    user=Depends(media_write),
) -> MediaRead:
    if client_op_id is not None:
        existing = db.scalar(
            select(MediaFile).where(MediaFile.client_op_id == client_op_id)
        )
        if existing is not None:
            return _read(existing)

    content = await file.read()
    media = service.save_media(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        folder=folder,
        caption=caption,
        filename=file.filename or "upload",
        content=content,
        media_type=file.content_type or "application/octet-stream",
        user_id=user.id,
    )
    media.client_op_id = client_op_id
    db.flush()
    return _read(media)


@router.get("", response_model=Page[MediaRead])
def list_media(
    db: DbDep,
    params: PageParamsDep,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    folder: MediaFolder | None = None,
    search: str | None = None,
) -> Page[MediaRead]:
    items, total = service.list_media(
        db, params.page, params.page_size, entity_type, entity_id, folder, search
    )
    return Page(
        items=[_read(m) for m in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/folders", response_model=FolderCounts)
def get_media_folder_counts(
    entity_type: str, entity_id: uuid.UUID, db: DbDep
) -> FolderCounts:
    counts = service.counts_by_folder(db, entity_type, entity_id)
    return FolderCounts(counts=counts, total=sum(counts.values()))


@router.get("/photo-timeline", response_model=PhotoTimeline)
def get_photo_timeline(entity_type: str, entity_id: uuid.UUID, db: DbDep) -> PhotoTimeline:
    return service.photo_timeline(db, entity_type, entity_id)


@router.get("/{media_id}/file")
def download_media_file(media_id: uuid.UUID, db: DbDep) -> FileResponse:
    media = service.get_media(db, media_id)
    return FileResponse(
        service.resolve_path(media),
        media_type=media.media_type,
        filename=media.original_filename,
    )


@router.get("/{media_id}/thumbnail")
def download_media_thumbnail(media_id: uuid.UUID, db: DbDep) -> FileResponse:
    media = service.get_media(db, media_id)
    return FileResponse(service.resolve_path(media, thumbnail=True), media_type="image/jpeg")


@router.patch("/{media_id}", response_model=MediaRead, dependencies=[Depends(media_write)])
def update_media(media_id: uuid.UUID, body: MediaUpdate, db: DbDep) -> MediaRead:
    return _read(service.update_media(db, media_id, body.caption, body.folder))


@router.delete("/{media_id}", status_code=204)
def delete_media(media_id: uuid.UUID, db: DbDep, user: CurrentUser) -> None:
    service.delete_media(db, media_id, user)
