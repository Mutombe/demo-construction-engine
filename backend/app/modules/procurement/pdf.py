from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.pdf import Col, DocumentPdf, money
from app.modules.company.models import CompanySettings
from app.modules.procurement.models import PurchaseOrder


def po_pdf(db: Session, po: PurchaseOrder) -> bytes:
    company = db.scalar(select(CompanySettings).limit(1))
    supplier = po.supplier
    project = po.project

    doc = DocumentPdf(
        company_name=company.name if company else "Construction ERP",
        doc_title="Purchase order",
        doc_number=po.doc_number,
    )
    doc.meta_grid(
        [
            ("Supplier", supplier.name if supplier else "-"),
            ("Project", f"{project.code} - {project.name}" if project else "-"),
            ("Order date", po.order_date.isoformat()),
            (
                "Expected delivery",
                po.expected_delivery.isoformat() if po.expected_delivery else "-",
            ),
            ("Status", po.status.value.capitalize()),
            ("Deliver to", (project.site_address or project.city or "-") if project else "-"),
        ]
    )

    doc.section_title("Order lines")
    doc.table(
        cols=[
            Col("Description", 0.44),
            Col("Unit", 0.08),
            Col("Qty", 0.14, "R"),
            Col("Unit price", 0.16, "R"),
            Col("Amount", 0.18, "R"),
        ],
        rows=[
            [
                item.description,
                item.unit or "-",
                f"{item.quantity:,.2f}",
                money(item.unit_price),
                money(item.amount),
            ]
            for item in po.items
        ],
        totals=["TOTAL", "", "", "", money(po.total_amount)],
    )

    if po.terms:
        doc.section_title("Commercial terms")
        doc.note(po.terms)
    return doc.render()
