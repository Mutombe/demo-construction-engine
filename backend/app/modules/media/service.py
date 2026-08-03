"""Central media library: polymorphic file attachments for every module.

Storage mirrors the ingestion module (media_root, sha256, authed serving);
images additionally get a Pillow thumbnail. The entity registry is the single
gatekeeper for what a file may attach to.
"""

import hashlib
import io
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import MediaFolder
from app.core.config import settings
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationFailedError
from app.modules.media.models import MediaFile

ACCEPTED_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/csv": ".csv",
    "text/plain": ".txt",
}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE = 25 * 1024 * 1024
THUMB_MAX = 480


def _entity_registry() -> dict[str, type]:
    """entity_type → model. Lazy import to avoid module-load cycles."""
    from app.modules.clients.models import Client
    from app.modules.expenses.models import ExpenseClaim
    from app.modules.inventory.models import StockItem
    from app.modules.payroll.models import Worker
    from app.modules.procurement.models import PurchaseOrder, Supplier
    from app.modules.projects.models import Project
    from app.modules.site.models import SiteDiaryEntry, SiteIssue
    from app.modules.valuations.models import Valuation

    return {
        "project": Project,
        "stock_item": StockItem,
        "expense_claim": ExpenseClaim,
        "supplier": Supplier,
        "site_issue": SiteIssue,
        "diary_entry": SiteDiaryEntry,
        "valuation": Valuation,
        "purchase_order": PurchaseOrder,
        "worker": Worker,
        "client": Client,
    }


def _media_root() -> Path:
    return Path(settings.media_root)


def _validate_entity(db: Session, entity_type: str, entity_id: uuid.UUID) -> None:
    registry = _entity_registry()
    model = registry.get(entity_type)
    if model is None:
        raise ValidationFailedError(
            f"Files cannot be attached to '{entity_type}'; "
            f"allowed: {', '.join(sorted(registry))}"
        )
    if db.get(model, entity_id) is None:
        raise NotFoundError(f"The {entity_type.replace('_', ' ')} to attach to was not found")


def _make_thumbnail(content: bytes, target: Path) -> bool:
    """Best-effort JPEG thumbnail; a corrupt image is not an upload error."""
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(content))
        image = image.convert("RGB")
        image.thumbnail((THUMB_MAX, THUMB_MAX))
        image.save(target, "JPEG", quality=80)
        return True
    except Exception:
        return False


def save_media(
    db: Session,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    folder: MediaFolder,
    caption: str | None,
    filename: str,
    content: bytes,
    media_type: str,
    user_id: uuid.UUID,
) -> MediaFile:
    if media_type not in ACCEPTED_TYPES:
        raise ValidationFailedError(
            "Unsupported file type — images, PDF, Word, Excel, CSV and text are accepted"
        )
    if len(content) == 0:
        raise ValidationFailedError("The uploaded file is empty")
    if len(content) > MAX_FILE_SIZE:
        raise ValidationFailedError("File exceeds the 25 MB limit")
    _validate_entity(db, entity_type, entity_id)

    media = MediaFile(
        entity_type=entity_type,
        entity_id=entity_id,
        folder=folder,
        original_filename=filename[:255],
        file_path="",
        file_sha256=hashlib.sha256(content).hexdigest(),
        media_type=media_type,
        file_size=len(content),
        caption=caption[:255] if caption else None,
        created_by=user_id,
    )
    db.add(media)
    db.flush()

    today = date.today()
    rel_dir = Path("library") / f"{today.year:04d}" / f"{today.month:02d}"
    rel_file = rel_dir / f"{media.id}{ACCEPTED_TYPES[media_type]}"
    target = _media_root() / rel_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    media.file_path = rel_file.as_posix()

    if media_type in IMAGE_TYPES:
        rel_thumb = rel_dir / f"{media.id}_thumb.jpg"
        if _make_thumbnail(content, _media_root() / rel_thumb):
            media.thumb_path = rel_thumb.as_posix()

    db.flush()
    return media


def get_media(db: Session, media_id: uuid.UUID) -> MediaFile:
    media = db.get(MediaFile, media_id)
    if media is None:
        raise NotFoundError("File not found")
    return media


def resolve_path(media: MediaFile, thumbnail: bool = False) -> Path:
    rel = media.thumb_path if thumbnail else media.file_path
    if not rel:
        raise NotFoundError("No thumbnail for this file")
    path = (_media_root() / rel).resolve()
    if not path.is_file():
        raise NotFoundError("Stored file is missing")
    return path


def list_media(
    db: Session,
    page: int,
    page_size: int,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    folder: MediaFolder | None = None,
    search: str | None = None,
) -> tuple[list[MediaFile], int]:
    query = select(MediaFile)
    if entity_type is not None:
        query = query.where(MediaFile.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(MediaFile.entity_id == entity_id)
    if folder is not None:
        query = query.where(MediaFile.folder == folder)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            MediaFile.original_filename.ilike(pattern) | MediaFile.caption.ilike(pattern)
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = list(
        db.scalars(
            query.order_by(MediaFile.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return items, total


def counts_by_folder(
    db: Session, entity_type: str, entity_id: uuid.UUID
) -> dict[str, int]:
    rows = db.execute(
        select(MediaFile.folder, func.count())
        .where(MediaFile.entity_type == entity_type, MediaFile.entity_id == entity_id)
        .group_by(MediaFile.folder)
    ).all()
    return {folder.value: count for folder, count in rows}


def update_media(
    db: Session,
    media_id: uuid.UUID,
    caption: str | None = None,
    folder: MediaFolder | None = None,
) -> MediaFile:
    media = get_media(db, media_id)
    if caption is not None:
        media.caption = caption[:255] or None
    if folder is not None:
        media.folder = folder
    return media


def delete_media(db: Session, media_id: uuid.UUID, user) -> None:
    from app.common.enums import UserRole

    media = get_media(db, media_id)
    if (
        user.role not in (UserRole.admin, UserRole.project_manager)
        and media.created_by != user.id
    ):
        raise ForbiddenError("Only the uploader or a project manager can delete this file")
    for rel in (media.file_path, media.thumb_path):
        if rel:
            try:
                (_media_root() / rel).unlink(missing_ok=True)
            except OSError:
                pass  # best-effort cleanup; the DB row is the source of truth
    db.delete(media)
