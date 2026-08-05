import re
import unicodedata
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Response

from app.common.enums import CostSource, ExpenseStatus
from app.core.deps import DbDep
from app.modules.reports import service
from app.modules.reports.render import ReportTable, to_csv, to_pdf, to_xlsx


def _company_name(db) -> str:
    """The letterhead. Reports are the documents most likely to leave the
    building, so they carry the company's own name rather than the default."""
    if db is None:
        return "Construction ERP"
    from sqlalchemy import select as _select

    from app.modules.company.models import CompanySettings

    company = db.scalar(_select(CompanySettings).limit(1))
    return company.name if company else "Construction ERP"

router = APIRouter(prefix="/reports", tags=["reports"])

Format = Literal["csv", "xlsx", "pdf"]

_MEDIA_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def _filename_stem(title: str) -> str:
    """Report titles carry punctuation and em dashes; HTTP headers are latin-1
    only, so anything outside [a-z0-9_-] is dropped rather than 500'ing the
    download."""
    ascii_only = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    cleaned = re.sub(r"[^a-z0-9]+", "_", ascii_only.lower()).strip("_")
    return cleaned or "report"


def _respond(table: ReportTable, format: Format, db=None) -> Response:
    if format == "pdf":
        content = to_pdf(table, _company_name(db))
    elif format == "xlsx":
        content = to_xlsx(table)
    else:
        content = to_csv(table)
    filename = f"{_filename_stem(table.title)}_{date.today()}.{format}"
    return Response(
        content=content,
        media_type=_MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/project-cost")
def export_project_cost(
    project_id: uuid.UUID, db: DbDep, format: Format = "csv"
) -> Response:
    return _respond(service.project_cost_report(db, project_id), format, db)


@router.get("/material-reconciliation")
def export_material_reconciliation(
    project_id: uuid.UUID, db: DbDep, format: Format = "csv"
) -> Response:
    return _respond(service.material_reconciliation(db, project_id), format, db)


@router.get("/procurement-register")
def export_procurement_register(
    db: DbDep, project_id: uuid.UUID | None = None, format: Format = "csv"
) -> Response:
    return _respond(service.procurement_register(db, project_id), format, db)


@router.get("/expense-register")
def export_expense_register(
    db: DbDep,
    project_id: uuid.UUID | None = None,
    status: ExpenseStatus | None = None,
    format: Format = "csv",
) -> Response:
    return _respond(service.expense_register(db, project_id, status), format, db)


@router.get("/inventory-analytics")
def export_inventory_analytics(
    db: DbDep, days: int = 90, format: Format = "csv"
) -> Response:
    return _respond(service.inventory_analytics_report(db, days), format, db)


@router.get("/stock-valuation")
def export_stock_valuation(
    db: DbDep, low_stock_only: bool = False, format: Format = "csv"
) -> Response:
    return _respond(service.stock_valuation(db, low_stock_only), format, db)


@router.get("/cost-ledger")
def export_cost_ledger(
    project_id: uuid.UUID,
    db: DbDep,
    source: CostSource | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    format: Format = "csv",
) -> Response:
    return _respond(service.cost_ledger(db, project_id, source, date_from, date_to), format, db)
