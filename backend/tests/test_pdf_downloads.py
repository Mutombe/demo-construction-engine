"""Documents people actually send: RFQs, weekly reports and the exports."""

from datetime import date, timedelta

from app.common.enums import UserRole
from tests.factories import (
    auth_headers,
    make_boq_item,
    make_boq_section,
    make_project,
    make_user,
)


def _pm(db):
    return auth_headers(make_user(db, role=UserRole.project_manager))


def _is_pdf(res) -> bool:
    return (
        res.status_code == 200
        and res.headers["content-type"] == "application/pdf"
        and res.content.startswith(b"%PDF-")
        and len(res.content) > 800
    )


def test_an_rfq_downloads_as_a_pdf(client, db):
    headers = _pm(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section, description="Cement, 42.5N")
    rfq = client.post(
        f"/api/v1/projects/{project.id}/rfqs",
        json={
            "title": "Cement supply",
            "due_date": str(date.today() + timedelta(days=7)),
            "items": [
                {"boq_item_id": str(item.id), "description": "Cement, 42.5N",
                 "unit": "bag", "quantity": "500"}
            ],
        },
        headers=headers,
    ).json()

    res = client.get(f"/api/v1/rfqs/{rfq['id']}/pdf", headers=headers)
    assert _is_pdf(res)
    assert rfq["doc_number"] in res.headers["content-disposition"]


def test_the_rfq_pdf_carries_no_rates(client, db):
    """It is the document that goes out to ask for a price, so the buyer's own
    budget has no business being on it."""
    from app.modules.procurement.pdf import rfq_pdf
    from app.modules.procurement.service import get_rfq

    headers = _pm(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    # A rate that would be unmistakable if it leaked onto the page
    item = make_boq_item(db, section, description="Cement", rate="987654.32")
    rfq = client.post(
        f"/api/v1/projects/{project.id}/rfqs",
        json={
            "title": "Cement supply",
            "items": [
                {"boq_item_id": str(item.id), "description": "Cement",
                 "unit": "bag", "quantity": "10"}
            ],
        },
        headers=headers,
    ).json()

    content = rfq_pdf(db, get_rfq(db, rfq["id"]))
    assert b"987654" not in content
    assert b"987,654" not in content


def test_a_report_downloads_in_every_format(client, db):
    headers = _pm(db)
    project = make_project(db)
    make_boq_item(db, make_boq_section(db, project))

    for fmt, media in (
        ("csv", "text/csv"),
        ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("pdf", "application/pdf"),
    ):
        res = client.get(
            f"/api/v1/reports/project-cost?project_id={project.id}&format={fmt}",
            headers=headers,
        )
        assert res.status_code == 200, fmt
        assert media in res.headers["content-type"]
        assert res.headers["content-disposition"].endswith(f'.{fmt}"')

    pdf = client.get(
        f"/api/v1/reports/project-cost?project_id={project.id}&format=pdf", headers=headers
    )
    assert pdf.content.startswith(b"%PDF-")


def test_an_empty_report_still_produces_a_readable_pdf(client, db):
    """A report with no rows is a normal answer, not an error, and a zero-byte
    download would look like a broken button."""
    headers = _pm(db)
    project = make_project(db)
    res = client.get(
        f"/api/v1/reports/cost-ledger?project_id={project.id}&format=pdf", headers=headers
    )
    assert _is_pdf(res)


def test_markdown_reaches_the_page_as_prose_not_syntax(client, db):
    """The AI writes Markdown; fpdf has no rich text. A stakeholder should
    never meet a stray asterisk on a printed report."""
    from app.common.pdf import _strip_inline

    assert _strip_inline("**Block A** poured") == "Block A poured"
    assert _strip_inline("a *late* delivery") == "a late delivery"
    assert _strip_inline("see [the RFQ](http://x)") == "see the RFQ (http://x)"


def test_the_weekly_report_pdf_is_built_from_the_data_not_the_screen(client, db):
    from app.modules.procurement.pdf import weekly_report_pdf
    from app.modules.projects.service import get_project

    project = make_project(db)
    content = weekly_report_pdf(
        db,
        get_project(db, project.id),
        date.today() - timedelta(days=6),
        date.today(),
        "# Progress\\nWork continued on **Block A**.\\n\\n- Slab poured\\n- Rebar late",
    )
    assert content.startswith(b"%PDF-")
    assert len(content) > 800


def test_a_report_pdf_survives_an_em_dash_in_the_title(client, db):
    """Content-Disposition is latin-1 only, which has 500'd this path before."""
    headers = _pm(db)
    project = make_project(db, name="Riverside — Block A")
    res = client.get(
        f"/api/v1/reports/project-cost?project_id={project.id}&format=pdf", headers=headers
    )
    assert res.status_code == 200
