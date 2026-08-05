import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import UserRole
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationFailedError
from app.modules.comments.models import Comment
from app.modules.comments.schemas import CommentCreate, CommentUpdate


def _entity_registry() -> dict[str, type]:
    """entity_type → model. Lazy import to avoid module-load cycles.

    Wider than the media registry on purpose: a task is the single most
    important thing to be able to talk about, and it holds no files.
    """
    from app.modules.clients.models import Client
    from app.modules.expenses.models import ExpenseClaim
    from app.modules.inventory.models import StockItem
    from app.modules.procurement.models import PurchaseOrder, Rfq, Supplier
    from app.modules.projects.models import Project
    from app.modules.requisitions.models import Requisition
    from app.modules.site.models import SiteDiaryEntry, SiteIssue
    from app.modules.tasks.models import Task
    from app.modules.valuations.models import Valuation

    return {
        "task": Task,
        "project": Project,
        "client": Client,
        "supplier": Supplier,
        "purchase_order": PurchaseOrder,
        "rfq": Rfq,
        "requisition": Requisition,
        "expense_claim": ExpenseClaim,
        "site_issue": SiteIssue,
        "diary_entry": SiteDiaryEntry,
        "valuation": Valuation,
        "stock_item": StockItem,
    }


def _entity(db: Session, entity_type: str, entity_id: uuid.UUID):
    registry = _entity_registry()
    model = registry.get(entity_type)
    if model is None:
        raise ValidationFailedError(
            f"Comments cannot be left on '{entity_type}'; "
            f"allowed: {', '.join(sorted(registry))}"
        )
    record = db.get(model, entity_id)
    if record is None:
        raise NotFoundError(f"The {entity_type.replace('_', ' ')} was not found")
    return record


def list_comments(
    db: Session, entity_type: str, entity_id: uuid.UUID
) -> list[Comment]:
    _entity(db, entity_type, entity_id)
    # Oldest first: a thread is read top to bottom, unlike a feed.
    return list(
        db.scalars(
            select(Comment)
            .where(Comment.entity_type == entity_type, Comment.entity_id == entity_id)
            .order_by(Comment.created_at.asc(), Comment.id.asc())
        )
    )


def counts_for(
    db: Session, entity_type: str, entity_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """How many comments each record has, in one query.

    Lets a list show "3 comments" without N+1 round trips.
    """
    if not entity_ids:
        return {}
    rows = db.execute(
        select(Comment.entity_id, func.count())
        .where(Comment.entity_type == entity_type, Comment.entity_id.in_(entity_ids))
        .group_by(Comment.entity_id)
    ).all()
    return {row[0]: row[1] for row in rows}


def create(
    db: Session, entity_type: str, entity_id: uuid.UUID, data: CommentCreate, user
) -> Comment:
    record = _entity(db, entity_type, entity_id)
    comment = Comment(
        entity_type=entity_type,
        entity_id=entity_id,
        body=data.body.strip(),
        author_id=user.id,
        author_name=user.full_name,
    )
    db.add(comment)
    db.flush()
    _notify_watchers(db, entity_type, record, comment, user)
    return comment


def _notify_watchers(db: Session, entity_type: str, record, comment: Comment, user) -> None:
    """Tell the people the record already belongs to.

    Deliberately narrow: the assignee of a task and whoever raised the record.
    A comment thread that notifies everyone becomes noise, and noise gets muted.
    """
    from app.modules.notifications import service as notifications

    recipients: set[uuid.UUID] = set()
    for field in ("assignee_id", "created_by", "actioned_by", "raised_by"):
        value = getattr(record, field, None)
        if value:
            recipients.add(value)
    if not recipients:
        return

    label = getattr(record, "doc_number", None) or getattr(record, "name", None) or ""
    notifications.notify(
        db,
        recipients,
        type="comment",
        title=f"{user.full_name} commented on {label}".strip(),
        body=comment.body[:160],
        link=_link_for(entity_type, record),
        exclude=user.id,
    )


def _link_for(entity_type: str, record) -> str | None:
    """Where the notification should land. Tasks live inside their project."""
    if entity_type == "task":
        return f"/projects/{record.project_id}?tab=program&task={record.id}"
    paths = {
        "project": "/projects",
        "client": "/clients",
        "supplier": "/procurement/suppliers",
        "purchase_order": "/procurement/purchase-orders",
        "rfq": "/procurement/rfqs",
        "requisition": "/procurement/requisitions",
        "expense_claim": "/expenses",
        "valuation": "/valuations",
        "stock_item": "/inventory",
    }
    base = paths.get(entity_type)
    return f"{base}/{record.id}" if base else None


def update(db: Session, comment_id: uuid.UUID, data: CommentUpdate, user) -> Comment:
    comment = _get(db, comment_id)
    if comment.author_id != user.id:
        raise ForbiddenError("Only the author can edit a comment")
    comment.body = data.body.strip()
    comment.edited_at = datetime.now(timezone.utc)
    db.flush()
    return comment


def delete(db: Session, comment_id: uuid.UUID, user) -> None:
    comment = _get(db, comment_id)
    # The author, or someone senior clearing up after them.
    if comment.author_id != user.id and user.role not in (
        UserRole.admin,
        UserRole.project_manager,
    ):
        raise ForbiddenError("Only the author or a project manager can delete this")
    db.delete(comment)


def _get(db: Session, comment_id: uuid.UUID) -> Comment:
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise NotFoundError("Comment not found")
    return comment
