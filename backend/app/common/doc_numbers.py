from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session


def next_doc_number(db: Session, model, prefix: str) -> str:
    """Sequential per-prefix, per-year document numbers: PREFIX-YYYY-NNN.

    Locks the latest matching row FOR UPDATE to serialize concurrent issuance;
    the unique constraint on doc_number is the backstop.
    """
    year = date.today().year
    like = f"{prefix}-{year}-%"
    last = db.scalar(
        select(model.doc_number)
        .where(model.doc_number.like(like))
        .order_by(model.doc_number.desc())
        .with_for_update()
        .limit(1)
    )
    seq = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}-{year}-{seq:03d}"
