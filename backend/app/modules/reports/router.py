import re
import unicodedata
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Response

from app.common.enums import CostSource, ExpenseStatus
from app.core.deps import DbDep
from app.modules.reports import service
from app.modules.reports.render import ReportTable, to_csv, to_xlsx

router = APIRouter(prefix="/reports", tags=["reports"])

Format = Literal["csv", "xlsx"]

_MEDIA_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _filename_stem(title: str) -> str:
    """Report titles carry punctuation and em dashes; HTTP headers are latin-1
    only, so anything outside [a-z0-9_-] is dropped rather than 500'ing the
    download."""
    ascii_only = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    cleaned = re.sub(r"[^a-z0-9]+", "_", ascii_only.lower()).strip("_")
    return cleaned or "report"


def _respond(table: ReportTable, format: Format) -> Response:
    content = to_csv(table) if format == "csv" else to_xlsx(table)
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
    return _respond(service.project_cost_report(db, project_id), format)


@router.get("/material-reconciliation")
def export_material_reconciliation(
    project_id: uuid.UUID, db: DbDep, format: Format = "csv"
) -> Response:
    return _respond(service.material_reconciliation(db, project_id), format)


@router.get("/procurement-register")
def export_procurement_register(
    db: DbDep, project_id: uuid.UUID | None = None, format: Format = "csv"
) -> Response:
    return _respond(service.procurement_register(db, project_id), format)


@router.get("/expense-register")
def export_expense_register(
    db: DbDep,
    project_id: uuid.UUID | None = None,
    status: ExpenseStatus | None = None,
    format: Format = "csv",
) -> Response:
    return _respond(service.expense_register(db, project_id, status), format)


@router.get("/inventory-analytics")
def export_inventory_analytics(
    db: DbDep, days: int = 90, format: Format = "csv"
) -> Response:
    return _respond(service.inventory_analytics_report(db, days), format)


@router.get("/stock-valuation")
def export_stock_valuation(
    db: DbDep, low_stock_only: bool = False, format: Format = "csv"
) -> Response:
    return _respond(service.stock_valuation(db, low_stock_only), format)


@router.get("/cost-ledger")
def export_cost_ledger(
    project_id: uuid.UUID,
    db: DbDep,
    source: CostSource | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    format: Format = "csv",
) -> Response:
    return _respond(service.cost_ledger(db, project_id, source, date_from, date_to), format)
