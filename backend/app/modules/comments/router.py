import uuid

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbDep
from app.modules.comments import service
from app.modules.comments.schemas import CommentCreate, CommentRead, CommentUpdate

router = APIRouter(tags=["comments"])


def _read(comment, user) -> CommentRead:
    out = CommentRead.model_validate(comment)
    out.can_edit = comment.author_id == user.id
    return out


@router.get("/comments", response_model=list[CommentRead])
def list_comments(
    entity_type: str, entity_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> list[CommentRead]:
    return [_read(c, user) for c in service.list_comments(db, entity_type, entity_id)]


@router.post("/comments", response_model=CommentRead, status_code=201)
def create_comment(
    entity_type: str,
    entity_id: uuid.UUID,
    body: CommentCreate,
    db: DbDep,
    user: CurrentUser,
) -> CommentRead:
    return _read(service.create(db, entity_type, entity_id, body, user), user)


@router.patch("/comments/{comment_id}", response_model=CommentRead)
def update_comment(
    comment_id: uuid.UUID, body: CommentUpdate, db: DbDep, user: CurrentUser
) -> CommentRead:
    return _read(service.update(db, comment_id, body, user), user)


@router.delete("/comments/{comment_id}", status_code=204)
def delete_comment(comment_id: uuid.UUID, db: DbDep, user: CurrentUser) -> None:
    service.delete(db, comment_id, user)
