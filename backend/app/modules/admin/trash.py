"""Deleting a record puts a copy in the trash first, so it can come back.

The whole feature rests on one property of this codebase: nothing deletes a
row that still has dependants. A client with projects, a project with tasks, a
pay run that has been approved — the service layer refuses all of them. So a
delete is always a small, self-contained subtree, which is what makes keeping
a verbatim copy and re-inserting it later a reasonable thing to do rather than
a distributed-systems problem.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import Base
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.admin.models import DeletedRecord

# A delete bigger than this is not something we can promise to undo, and
# holding a megabyte of JSON per row helps nobody.
MAX_ARCHIVED_ROWS = 500


def _encode(value: Any) -> Any:
    """Column value to something JSONB will hold without losing precision."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)  # str, not float: money does not survive float
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def _decode(column, value: Any) -> Any:
    """The inverse, driven by the column's own type rather than by guessing."""
    if value is None:
        return None
    try:
        python_type = column.type.python_type
    except NotImplementedError:
        return value
    if python_type is uuid.UUID and isinstance(value, str):
        return uuid.UUID(value)
    if python_type is Decimal and isinstance(value, str):
        return Decimal(value)
    if python_type is datetime and isinstance(value, str):
        return datetime.fromisoformat(value)
    if python_type is date and isinstance(value, str):
        return date.fromisoformat(value)
    if python_type is bytes and isinstance(value, str):
        return bytes.fromhex(value)
    return value


def _restorable_columns(mapper_or_table):
    """Everything except columns the database computes for itself.

    BOQ item `amount` is `quantity * rate` as a generated column: writing it
    back is not just unnecessary, Postgres rejects the INSERT outright.
    """
    columns = getattr(mapper_or_table, "columns", mapper_or_table)
    return [c for c in columns if c.computed is None]


def _row_values(obj) -> dict[str, Any]:
    return {
        c.key: _encode(getattr(obj, c.key))
        for c in _restorable_columns(inspect(obj).mapper.columns)
    }


def _cascade_children(obj, seen: set[tuple[str, Any]]) -> list[Any]:
    """Rows the database will take with this one, deepest last.

    Only follows relationships configured to cascade the delete, which is
    exactly the set that would otherwise vanish without a copy.
    """
    collected: list[Any] = []
    for rel in inspect(obj).mapper.relationships:
        if not rel.cascade.delete or rel.viewonly:
            continue
        related = getattr(obj, rel.key)
        children = related if isinstance(related, (list, set)) else ([related] if related else [])
        for child in children:
            key = (child.__tablename__, getattr(child, "id", id(child)))
            if key in seen:
                continue
            seen.add(key)
            collected.append(child)
            collected.extend(_cascade_children(child, seen))
    return collected


def archive(
    db: Session,
    obj,
    *,
    entity_type: str,
    label: str,
    user=None,
    project_id: uuid.UUID | None = None,
) -> DeletedRecord:
    """Copy `obj` (and anything cascading from it) into the trash.

    Does not delete: the caller still does that, so the existing guards and
    ordering stay exactly where they are.
    """
    seen: set[tuple[str, Any]] = {(obj.__tablename__, obj.id)}
    children = _cascade_children(obj, seen)

    # Parents first, so restore can insert in the same order
    groups: list[dict[str, Any]] = [{"table": obj.__tablename__, "rows": [_row_values(obj)]}]
    for child in children:
        table = child.__tablename__
        existing = next((g for g in groups if g["table"] == table), None)
        if existing is None:
            groups.append({"table": table, "rows": [_row_values(child)]})
        else:
            existing["rows"].append(_row_values(child))

    total = sum(len(g["rows"]) for g in groups)
    too_big = total > MAX_ARCHIVED_ROWS
    record = DeletedRecord(
        entity_type=entity_type,
        entity_id=obj.id,
        table_name=obj.__tablename__,
        label=label,
        project_id=project_id or getattr(obj, "project_id", None),
        payload=[] if too_big else groups,
        row_count=total,
        deleted_at=datetime.now(timezone.utc),
        deleted_by_id=getattr(user, "id", None),
        deleted_by_name=getattr(user, "full_name", None),
        restorable=not too_big,
    )
    db.add(record)
    db.flush()
    return record


def list_deleted(
    db: Session,
    page: int,
    page_size: int,
    entity_type: str | None = None,
) -> tuple[list[DeletedRecord], int]:
    stmt = select(DeletedRecord).where(DeletedRecord.restored_at.is_(None))
    if entity_type:
        stmt = stmt.where(DeletedRecord.entity_type == entity_type)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        db.scalars(
            stmt.order_by(DeletedRecord.deleted_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return rows, total


def _get(db: Session, record_id: uuid.UUID) -> DeletedRecord:
    record = db.get(DeletedRecord, record_id)
    if record is None:
        raise NotFoundError("That trash entry no longer exists")
    return record


def restore(db: Session, record_id: uuid.UUID) -> DeletedRecord:
    record = _get(db, record_id)
    if record.restored_at is not None:
        raise ConflictError("This has already been restored")
    if not record.restorable:
        raise ConflictError(
            f"This removed {record.row_count} rows, too many to keep a copy of. "
            "It cannot be restored."
        )

    tables = Base.metadata.tables
    # A savepoint, so a half-inserted subtree cannot survive a failure part
    # way through and the caller's transaction stays usable either way.
    nested = db.begin_nested()
    try:
        for group in record.payload:
            table = tables.get(group["table"])
            if table is None:
                raise ConflictError(f"The {group['table']} table no longer exists")
            for row in group["rows"]:
                writable = {c.name for c in _restorable_columns(table.columns)}
                values = {
                    name: _decode(table.c[name], value)
                    for name, value in row.items()
                    if name in writable
                }
                db.execute(table.insert().values(**values))
        nested.commit()
    except IntegrityError as exc:
        nested.rollback()
        # Almost always: the thing it belonged to was deleted after it was
        raise ValidationFailedError(
            f"{record.label} cannot be put back — something it depended on is gone."
        ) from exc

    record.restored_at = datetime.now(timezone.utc)
    db.flush()
    return record


def purge(db: Session, record_id: uuid.UUID) -> DeletedRecord:
    record = _get(db, record_id)
    if record.entity_type == "document" and record.restored_at is None:
        _remove_files(record)
    db.delete(record)
    db.flush()
    return record


def _remove_files(record: DeletedRecord) -> None:
    """Uploads stay on disk while their row is in the trash. This is the point
    where they stop being recoverable, so it is also where they go."""
    from app.modules.media.service import _media_root

    root = _media_root()
    for group in record.payload:
        for row in group["rows"]:
            for key in ("file_path", "thumb_path"):
                rel = row.get(key)
                if not rel:
                    continue
                try:
                    (root / rel).unlink(missing_ok=True)
                except OSError:
                    pass  # best effort; the row leaving is what matters


def distinct_types(db: Session) -> list[str]:
    return sorted(
        t
        for t in db.scalars(
            select(DeletedRecord.entity_type).where(DeletedRecord.restored_at.is_(None)).distinct()
        )
    )
