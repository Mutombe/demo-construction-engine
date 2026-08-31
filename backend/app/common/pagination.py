from typing import Annotated

from fastapi import Depends, Query
from pydantic import BaseModel


class PageParams(BaseModel):
    page: int = 1
    page_size: int = 50

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


PageParamsDep = Annotated[PageParams, Depends(page_params)]


def paginate(db, stmt, params: PageParams, mapper=None):
    """Count the whole set, return one page of it.

    Two queries rather than one, deliberately: a window function that carries
    the total on every row makes a page of 50 pay for counting a million.

    The count drops ORDER BY. Ordering a count changes nothing about the
    answer and, on a large table, costs a sort that is thrown away.
    """
    from sqlalchemy import func, select

    from app.common.schemas import Page

    total = db.scalar(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    )
    rows = db.execute(
        stmt.offset(params.offset).limit(params.page_size)
    ).scalars().all()
    return Page(
        items=[mapper(row) for row in rows] if mapper else list(rows),
        total=total or 0,
        page=params.page,
        page_size=params.page_size,
    )


def page_of(items: list, params: PageParams, mapper=None):
    """One page out of a list that had to be built in full.

    For answers that are computed rather than queried — availability, an
    asset register, anything that walks each row to work out its numbers.
    Honest about what it is: the work has already been done, and this only
    saves shipping it all to the browser.
    """
    from app.common.schemas import Page

    window = items[params.offset : params.offset + params.page_size]
    return Page(
        items=[mapper(row) for row in window] if mapper else window,
        total=len(items),
        page=params.page,
        page_size=params.page_size,
    )
