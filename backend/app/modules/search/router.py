from typing import Annotated

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, DbDep
from app.modules.search import service
from app.modules.search.schemas import SearchResults

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResults)
def global_search(
    db: DbDep,
    user: CurrentUser,
    q: Annotated[str, Query(max_length=100)] = "",
) -> SearchResults:
    """Records matching `q` across every addressable entity, for the palette."""
    return service.search(db, q, user)
