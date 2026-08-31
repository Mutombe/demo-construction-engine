from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.pdf import Col, DocumentPdf, money
from app.modules.company.models import CompanySettings
from app.modules.payroll.models import PayRun, PayRunLine


def _payslip_page(doc: DocumentPdf, run: PayRun, line: PayRunLine) -> None:
    doc.meta_grid(
        [
            ("Worker", line.worker_name),
            ("Trade", line.trade),
            ("Pay period", f"{run.period_start.isoformat()} to {run.period_end.isoformat()}"),
            ("Basis / rate", f"{line.pay_basis.value.capitalize()} @ {money(line.rate)}"),
        ]
    )

    unit = "hrs" if line.pay_basis.value == "hourly" else "days"
    earning_rows = [
        [f"Normal time ({line.quantity:,.2f} {unit})", money(line.base_pay)],
    ]
    if line.overtime_quantity and line.overtime_quantity > 0:
        earning_rows.append(
            [f"Overtime x1.5 ({line.overtime_quantity:,.2f} {unit})", money(line.overtime_pay)]
        )
    for item in line.pay_items or []:
        if item["kind"] == "allowance":
            earning_rows.append([f"Allowance - {item['label']}", money(item["amount"])])

    deduction_rows = [
        [f"Deduction - {item['label']}", money(item["amount"])]
        for item in (line.pay_items or [])
        if item["kind"] == "deduction"
    ]

    doc.section_title("Earnings")
    doc.table(
        cols=[Col("Description", 0.7), Col("Amount", 0.3, "R")],
        rows=earning_rows,
        totals=["GROSS PAY", money(line.gross_pay)],
    )
    if deduction_rows:
        doc.section_title("Deductions")
        doc.table(
            cols=[Col("Description", 0.7), Col("Amount", 0.3, "R")],
            rows=deduction_rows,
            totals=["TOTAL DEDUCTIONS", money(line.deduction_total)],
        )
    doc.amount_summary([("Net pay (USD)", money(line.net_pay))])

    if line.project_allocation and len(line.project_allocation) > 1:
        doc.note(
            "Labour cost allocation: "
            + "; ".join(
                f"{a['project_code']} {money(a['amount'])}" for a in line.project_allocation
            )
        )


def payslip_pdf(db: Session, run: PayRun, line: PayRunLine) -> bytes:
    company = db.scalar(select(CompanySettings).limit(1))
    doc = DocumentPdf(
        company_name=company.name if company else "Company Name Not Set",
        doc_title="Payslip",
        doc_number=run.doc_number,
    )
    _payslip_page(doc, run, line)
    return doc.render()


def payslips_pdf(db: Session, run: PayRun) -> bytes:
    """All payslips for a run, one page per worker."""
    company = db.scalar(select(CompanySettings).limit(1))
    doc = DocumentPdf(
        company_name=company.name if company else "Company Name Not Set",
        doc_title="Payslips",
        doc_number=run.doc_number,
    )
    for i, line in enumerate(sorted(run.lines, key=lambda ln: ln.worker_name)):
        if i > 0:
            doc.add_page()
        _payslip_page(doc, run, line)
    return doc.render()
