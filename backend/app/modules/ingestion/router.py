import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.common.enums import IngestionDocType, IngestionStatus, UserRole
from app.common.pagination import PageParamsDep
from app.common.schemas import Page
from app.core.deps import DbDep, require_roles
from app.core.exceptions import AiNotConfiguredError
from app.modules.ai.client import ai_available
from app.modules.ingestion import posting, service
from app.modules.ingestion.schemas import (
    IngestionDraftRequest,
    IngestionItemRead,
    IngestionRejectRequest,
    IngestionUploadResponse,
)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

ingest_write = require_roles(
    UserRole.project_manager, UserRole.site_manager, UserRole.procurement_officer
)


def _require_ai() -> None:
    if not ai_available():
        raise AiNotConfiguredError()


@router.post("/items", response_model=IngestionUploadResponse, status_code=201)
async def upload_ingestion_item(
    db: DbDep,
    file: UploadFile = File(...),
    project_id: uuid.UUID | None = Form(default=None),
    user=Depends(ingest_write),
) -> IngestionUploadResponse:
    _require_ai()
    content = await file.read()
    item, duplicate_ids = service.save_upload(
        db,
        filename=file.filename or "upload",
        content=content,
        media_type=file.content_type or "application/octet-stream",
        project_id=project_id,
        user_id=user.id,
    )
    return IngestionUploadResponse(
        item=IngestionItemRead.model_validate(item), duplicate_ids=duplicate_ids
    )


@router.post("/items/{item_id}/process", response_model=IngestionItemRead)
def process_ingestion_item(
    item_id: uuid.UUID, db: DbDep, user=Depends(ingest_write)
) -> IngestionItemRead:
    _require_ai()
    return IngestionItemRead.model_validate(service.process_item(db, item_id))


@router.post("/items/{item_id}/draft", response_model=IngestionItemRead)
def redraft_ingestion_item(
    item_id: uuid.UUID,
    body: IngestionDraftRequest,
    db: DbDep,
    user=Depends(ingest_write),
) -> IngestionItemRead:
    return IngestionItemRead.model_validate(service.redraft_item(db, item_id, body.corrections))


@router.post("/items/{item_id}/approve", response_model=IngestionItemRead)
def approve_ingestion_item(
    item_id: uuid.UUID, db: DbDep, user=Depends(ingest_write)
) -> IngestionItemRead:
    return IngestionItemRead.model_validate(posting.approve_item(db, item_id, user))


@router.post("/items/{item_id}/reject", response_model=IngestionItemRead)
def reject_ingestion_item(
    item_id: uuid.UUID,
    body: IngestionRejectRequest,
    db: DbDep,
    user=Depends(ingest_write),
) -> IngestionItemRead:
    return IngestionItemRead.model_validate(service.reject_item(db, item_id, body.reason, user.id))


@router.get("/items", response_model=Page[IngestionItemRead])
def list_ingestion_items(
    db: DbDep,
    params: PageParamsDep,
    status: IngestionStatus | None = None,
    doc_type: IngestionDocType | None = None,
    project_id: uuid.UUID | None = None,
) -> Page[IngestionItemRead]:
    items, total = service.list_items(
        db, params.page, params.page_size, status, doc_type, project_id
    )
    return Page(
        items=[IngestionItemRead.model_validate(i) for i in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/items/{item_id}", response_model=IngestionItemRead)
def get_ingestion_item(item_id: uuid.UUID, db: DbDep) -> IngestionItemRead:
    return IngestionItemRead.model_validate(service.get_item(db, item_id))


@router.get("/items/{item_id}/file")
def download_ingestion_file(item_id: uuid.UUID, db: DbDep) -> FileResponse:
    item = service.get_item(db, item_id)
    path = service.resolve_file_path(item)
    return FileResponse(path, media_type=item.media_type, filename=item.original_filename)
