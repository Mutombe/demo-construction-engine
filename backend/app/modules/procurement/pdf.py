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
        company_name=company.name if company else "Company Name Not Set",
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


def rfq_pdf(db: Session, rfq) -> bytes:
    """The request as a supplier receives it.

    Carries quantities and scope but no rates: this is the document that goes
    out to ask for a price, so putting the buyer's own budget on it would
    defeat the exercise.
    """
    company = db.scalar(select(CompanySettings).limit(1))
    project = rfq.project

    doc = DocumentPdf(
        company_name=company.name if company else "Company Name Not Set",
        doc_title="Request for quotation",
        doc_number=rfq.doc_number,
    )
    doc.meta_grid(
        [
            ("Project", f"{project.code} - {project.name}" if project else "-"),
            ("Issued", rfq.created_at.date().isoformat()),
            ("Quotes due", rfq.due_date.isoformat() if rfq.due_date else "-"),
            ("Status", rfq.status.value.capitalize()),
            ("Delivery to", (project.site_address or project.city or "-") if project else "-"),
            ("Reference", rfq.doc_number),
        ]
    )

    doc.section_title("Scope")
    doc.table(
        cols=[
            Col("Description", 0.62),
            Col("Unit", 0.14),
            Col("Quantity", 0.24, "R"),
        ],
        rows=[
            [item.description, item.unit or "-", f"{item.quantity:,.3f}"]
            for item in sorted(rfq.items, key=lambda i: i.sort_order)
        ],
    )

    if rfq.body:
        doc.section_title("Instructions to tenderers")
        doc.markdown_block(rfq.body)

    doc.note(
        "Please return your price against each line above, together with "
        "payment terms, delivery lead time and the period your quote stays open."
    )
    return doc.render()


def weekly_report_pdf(db: Session, project, week_start, week_end, body: str) -> bytes:
    """The AI weekly report as something a client or director can be handed."""
    company = db.scalar(select(CompanySettings).limit(1))
    doc = DocumentPdf(
        company_name=company.name if company else "Company Name Not Set",
        doc_title="Weekly site report",
        doc_number=f"{week_start.isoformat()} to {week_end.isoformat()}",
    )
    doc.meta_grid(
        [
            ("Project", f"{project.code} - {project.name}"),
            ("Site", project.site_address or project.city or "-"),
            ("Week commencing", week_start.isoformat()),
            ("Week ending", week_end.isoformat()),
        ]
    )
    doc.markdown_block(body)
    return doc.render()
