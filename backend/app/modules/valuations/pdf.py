from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.pdf import Col, DocumentPdf, money
from app.modules.company.models import CompanySettings
from app.modules.valuations.models import Valuation


def certificate_pdf(db: Session, valuation: Valuation) -> bytes:
    project = valuation.project
    client = project.client if project else None
    company = db.scalar(select(CompanySettings).limit(1))

    doc = DocumentPdf(
        company_name=company.name if company else "Construction ERP",
        doc_title="Payment certificate",
        doc_number=valuation.doc_number,
    )
    doc.meta_grid(
        [
            ("Project", f"{project.code} - {project.name}"),
            ("Client", client.name if client else "-"),
            ("Certificate no.", f"Valuation {valuation.valuation_number}"),
            ("Period ending", valuation.period_end.isoformat()),
            ("Status", valuation.status.value.capitalize()),
            (
                "Issued / paid",
                " / ".join(
                    filter(
                        None,
                        [
                            valuation.issued_date.isoformat() if valuation.issued_date else None,
                            valuation.paid_date.isoformat() if valuation.paid_date else None,
                        ],
                    )
                )
                or "-",
            ),
        ]
    )

    if valuation.lines:
        doc.section_title("Measurement summary")
        doc.table(
            cols=[
                Col("Item", 0.10),
                Col("Description", 0.40),
                Col("Unit", 0.08),
                Col("Qty to date", 0.14, "R"),
                Col("Rate", 0.12, "R"),
                Col("Amount", 0.16, "R"),
            ],
            rows=[
                [
                    line.item_code,
                    line.description,
                    line.unit,
                    f"{line.qty_to_date:,.3f}",
                    money(line.rate),
                    money(line.amount),
                ]
                for line in valuation.lines
            ],
            totals=["", "TOTAL", "", "", "", money(valuation.gross_valuation)],
        )

    doc.section_title("Certificate")
    doc.amount_summary(
        [
            ("Gross value of work executed to date", money(valuation.gross_valuation)),
            ("Less retention", f"({money(valuation.retention_amount)})"),
            ("Less previously certified", f"({money(valuation.previous_certified)})"),
            ("Net amount certified this valuation (USD)", money(valuation.net_certified)),
        ]
    )
    if valuation.notes:
        doc.note(valuation.notes)
    doc.note(
        "This certificate records the value of work executed under the contract. "
        "Retention is held in accordance with the contract terms."
    )
    return doc.render()
