from pydantic import BaseModel


class SearchHit(BaseModel):
    """One addressable record the palette can jump to."""

    type: str  # "project", "purchase_order", … — drives the icon and grouping
    type_label: str  # human-facing group heading
    id: str
    label: str  # the line people read
    sublabel: str | None  # context: project, supplier, status
    code: str | None  # doc number or code, shown monospaced
    url: str  # where selecting it navigates


class SearchResults(BaseModel):
    query: str
    hits: list[SearchHit]
    total: int
    truncated: bool  # more matches exist than were returned
