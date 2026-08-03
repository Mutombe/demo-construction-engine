from decimal import Decimal

from sqlalchemy import select

from app.common.enums import CostSource, ExpenseStatus, UserRole
from app.modules.costs.models import CostEntry
from app.modules.expenses.models import ExpenseClaim
from app.modules.ingestion.extraction import DocumentExtraction
from app.modules.procurement.models import Quote
from tests.ai_fakes import fake_response
from tests.factories import (
    auth_headers,
    make_boq_item,
    make_boq_section,
    make_project,
    make_rfq,
    make_supplier,
    make_user,
)


def _proc(db):
    return auth_headers(make_user(db, role=UserRole.procurement_officer))


def _upload(client, headers, *, content=b"fake-image-bytes", filename="doc.png",
            ctype="image/png", project_id=None):
    data = {"project_id": str(project_id)} if project_id else {}
    return client.post(
        "/api/v1/ingestion/items",
        files={"file": (filename, content, ctype)},
        data=data,
        headers=headers,
    )


def _f(value, conf="high"):
    return {"value": value, "confidence": conf}


def _extraction(doc_type, section_name, section, conf="high"):
    doc = {
        "document_type": doc_type,
        "classification_confidence": conf,
        "summary": "A test document",
        "invoice": None,
        "receipt": None,
        "delivery_note": None,
        "quote": None,
    }
    if section_name:
        doc[section_name] = section
    return DocumentExtraction.model_validate(doc)


def _invoice_extraction(project_code, **overrides):
    section = {
        "supplier_name": _f("BuildMart Hardware"),
        "invoice_number": _f("INV-889"),
        "invoice_date": _f("2026-07-15"),
        "total_amount": _f(1500.5),
        "currency": _f("USD"),
        "project_match": _f(project_code),
        "lines": [],
    } | overrides
    return _extraction("supplier_invoice", "invoice", section)


def _process(client, headers, item_id):
    return client.post(f"/api/v1/ingestion/items/{item_id}/process", headers=headers)


def _issued_po(client, db, headers, project):
    supplier = make_supplier(db, name="Steelco Ltd")
    po = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "items": [{"description": "Rebar Y12", "unit": "len", "quantity": "40",
                       "unit_price": "9.50"}],
        },
        headers=headers,
    ).json()
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)
    return client.get(f"/api/v1/purchase-orders/{po['id']}", headers=headers).json()


# --- Upload -----------------------------------------------------------------


def test_upload_and_duplicate_warning(client, db, fake_ai):
    headers = _proc(db)
    first = _upload(client, headers)
    assert first.status_code == 201
    body = first.json()
    assert body["item"]["status"] == "received"
    assert body["duplicate_ids"] == []

    second = _upload(client, headers)
    assert second.status_code == 201
    assert body["item"]["id"] in second.json()["duplicate_ids"]


def test_upload_rejects_bad_type_and_viewer(client, db, fake_ai):
    headers = _proc(db)
    assert _upload(client, headers, ctype="text/plain", filename="notes.txt").status_code == 422
    viewer = auth_headers(make_user(db, role=UserRole.viewer))
    assert _upload(client, viewer).status_code == 403


def test_upload_503_without_ai(client, db, no_ai):
    assert _upload(client, _proc(db)).status_code == 503


# --- Process: extraction call + pipeline ------------------------------------


def test_process_invoice_happy_path(client, db, fake_ai):
    headers = _proc(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    boq_item = make_boq_item(db, section)
    rfq = make_rfq(db, project, [boq_item], doc_number="RFQ-CTX-001")
    po = _issued_po(client, db, headers, project)

    item_id = _upload(client, headers).json()["item"]["id"]
    fake_ai.messages.parse_responses.append(
        fake_response(parsed_output=_invoice_extraction(project.code))
    )
    res = _process(client, headers, item_id)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "drafted"
    assert body["doc_type"] == "supplier_invoice"
    action = body["proposed_action"]
    assert action["action"] == "create_cost_entry"
    assert action["gate_passed"] is True
    assert action["params"]["amount"] == "1500.5"
    assert action["params"]["project_id"] == str(project.id)
    assert action["params"]["reference"] == "INV-889"

    # The single vision call carried the image plus DB context (PO + RFQ numbers)
    call = fake_ai.messages.parse_calls[0]
    content = call["messages"][0]["content"]
    assert content[0]["type"] == "image"
    context = content[1]["text"]
    assert po["doc_number"] in context
    assert rfq.doc_number in context
    assert project.code in context


def test_low_confidence_fails_gate(client, db, fake_ai):
    headers = _proc(db)
    project = make_project(db)
    item_id = _upload(client, headers).json()["item"]["id"]
    fake_ai.messages.parse_responses.append(
        fake_response(
            parsed_output=_invoice_extraction(project.code, total_amount=_f(1500.5, "low"))
        )
    )
    body = _process(client, headers, item_id).json()
    assert body["status"] == "needs_info"
    action = body["proposed_action"]
    assert action["gate_passed"] is False
    assert action["confidence_score"] == 0.5


def test_unknown_document_needs_info(client, db, fake_ai):
    headers = _proc(db)
    item_id = _upload(client, headers).json()["item"]["id"]
    fake_ai.messages.parse_responses.append(
        fake_response(parsed_output=_extraction("unknown", None, None, conf="low"))
    )
    body = _process(client, headers, item_id).json()
    assert body["status"] == "needs_info"
    assert body["doc_type"] is None
    assert body["proposed_action"]["problems"]


def test_ai_failure_is_retryable(client, db, fake_ai):
    headers = _proc(db)
    project = make_project(db)
    item_id = _upload(client, headers).json()["item"]["id"]

    fake_ai.messages.parse_responses.append(fake_response(stop_reason="refusal"))
    body = _process(client, headers, item_id).json()
    assert body["status"] == "failed"
    assert body["error"]

    fake_ai.messages.parse_responses.append(
        fake_response(parsed_output=_invoice_extraction(project.code))
    )
    assert _process(client, headers, item_id).json()["status"] == "drafted"


# --- Corrections ------------------------------------------------------------


def test_corrections_redraft_without_ai_call(client, db, fake_ai):
    headers = _proc(db)
    project = make_project(db)
    item_id = _upload(client, headers).json()["item"]["id"]
    fake_ai.messages.parse_responses.append(
        fake_response(
            parsed_output=_invoice_extraction(project.code, project_match=_f(None, "low"))
        )
    )
    body = _process(client, headers, item_id).json()
    assert body["status"] == "needs_info"
    assert "project_match" in body["proposed_action"]["missing_fields"]
    calls_before = len(fake_ai.messages.parse_calls)

    res = client.post(
        f"/api/v1/ingestion/items/{item_id}/draft",
        json={"corrections": {"project_match": project.code}},
        headers=headers,
    )
    body = res.json()
    assert body["status"] == "drafted"
    assert body["proposed_action"]["gate_passed"] is True
    assert body["proposed_action"]["corrections"] == {"project_match": project.code}
    assert len(fake_ai.messages.parse_calls) == calls_before


# --- Approve: the four posting adapters -------------------------------------


def test_approve_invoice_creates_cost_entry(client, db, fake_ai):
    headers = _proc(db)
    project = make_project(db)
    item_id = _upload(client, headers).json()["item"]["id"]
    fake_ai.messages.parse_responses.append(
        fake_response(parsed_output=_invoice_extraction(project.code))
    )
    _process(client, headers, item_id)

    res = client.post(f"/api/v1/ingestion/items/{item_id}/approve", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "posted"
    lineage = body["proposed_action"]["lineage"]
    assert lineage["posted_type"] == "cost_entry"

    entry = db.scalar(select(CostEntry).where(CostEntry.reference == "INV-889"))
    assert entry is not None
    assert entry.source == CostSource.invoice
    assert entry.amount == Decimal("1500.5")
    assert entry.project_id == project.id


def test_approve_receipt_files_pending_claim_for_uploader(client, db, fake_ai):
    uploader = make_user(db, role=UserRole.site_manager)
    headers = auth_headers(uploader)
    project = make_project(db)
    item_id = _upload(client, headers).json()["item"]["id"]
    section = {
        "vendor_name": _f("Total Fuel Station"),
        "receipt_date": _f("2026-07-20"),
        "total_amount": _f(85),
        "currency": _f("USD"),
        "category": _f("diesel"),
        "description": _f("Diesel for site generator"),
        "project_match": _f(project.code),
    }
    fake_ai.messages.parse_responses.append(
        fake_response(parsed_output=_extraction("expense_receipt", "receipt", section))
    )
    assert _process(client, headers, item_id).json()["status"] == "drafted"

    res = client.post(f"/api/v1/ingestion/items/{item_id}/approve", headers=headers)
    assert res.status_code == 200
    claim = db.scalar(select(ExpenseClaim).order_by(ExpenseClaim.created_at.desc()).limit(1))
    assert claim.status == ExpenseStatus.pending
    assert claim.created_by == uploader.id
    assert claim.category.value == "fuel"
    assert claim.amount == Decimal("85")


def test_approve_delivery_receives_po(client, db, fake_ai):
    headers = _proc(db)
    project = make_project(db)
    po = _issued_po(client, db, headers, project)
    item_id = _upload(client, headers).json()["item"]["id"]
    section = {
        "supplier_name": _f("Steelco Ltd"),
        "po_match": _f(po["doc_number"]),
        "delivery_date": _f("2026-07-22"),
        "delivery_note_number": _f("DN-4411"),
        "lines": [],
    }
    fake_ai.messages.parse_responses.append(
        fake_response(parsed_output=_extraction("delivery_note", "delivery_note", section))
    )
    assert _process(client, headers, item_id).json()["status"] == "drafted"

    res = client.post(f"/api/v1/ingestion/items/{item_id}/approve", headers=headers)
    assert res.status_code == 200
    po_after = client.get(f"/api/v1/purchase-orders/{po['id']}", headers=headers).json()
    assert po_after["status"] == "received"
    assert po_after["received_to"] == "project"
    entry = db.scalar(select(CostEntry).where(CostEntry.reference == po["doc_number"]))
    assert entry is not None


def test_approve_quote_records_ai_extracted_quote(client, db, fake_ai):
    headers = _proc(db)
    project = make_project(db)
    section_row = make_boq_section(db, project)
    boq_item = make_boq_item(db, section_row)
    rfq = make_rfq(db, project, [boq_item])
    supplier = make_supplier(db, name="Quotewell Supplies")
    item_id = _upload(client, headers).json()["item"]["id"]
    section = {
        "rfq_match": _f(rfq.doc_number),
        "supplier_name": _f("Quotewell Supplies"),
        "valid_until": _f("2026-09-01"),
        "payment_terms": _f("30 days"),
        "delivery_terms": _f("Delivered to site"),
        "currency": _f("USD"),
        "lines": [
            {
                "rfq_item_id": str(rfq.items[0].id),
                "description": rfq.items[0].description,
                "unit": rfq.items[0].unit,
                "quantity": float(rfq.items[0].quantity),
                "unit_price": 45.0,
                "match_confidence": "exact",
            }
        ],
    }
    fake_ai.messages.parse_responses.append(
        fake_response(parsed_output=_extraction("supplier_quote", "quote", section))
    )
    assert _process(client, headers, item_id).json()["status"] == "drafted"

    res = client.post(f"/api/v1/ingestion/items/{item_id}/approve", headers=headers)
    assert res.status_code == 200
    quote = db.scalar(select(Quote).where(Quote.supplier_id == supplier.id))
    assert quote is not None
    assert quote.ai_extracted is True
    assert quote.rfq_id == rfq.id
    assert quote.items[0].rfq_item_id == rfq.items[0].id


# --- State machine + RBAC ---------------------------------------------------


def test_state_machine_conflicts(client, db, fake_ai):
    headers = _proc(db)
    project = make_project(db)
    item_id = _upload(client, headers).json()["item"]["id"]

    # not processed yet: approve/draft are 409
    approve_url = f"/api/v1/ingestion/items/{item_id}/approve"
    assert client.post(approve_url, headers=headers).status_code == 409
    assert (
        client.post(
            f"/api/v1/ingestion/items/{item_id}/draft", json={"corrections": {}}, headers=headers
        ).status_code
        == 409
    )

    fake_ai.messages.parse_responses.append(
        fake_response(parsed_output=_invoice_extraction(project.code))
    )
    _process(client, headers, item_id)
    # drafted: re-process is 409
    assert _process(client, headers, item_id).status_code == 409

    client.post(approve_url, headers=headers)
    # posted: reject is 409
    assert (
        client.post(
            f"/api/v1/ingestion/items/{item_id}/reject", json={"reason": "no"}, headers=headers
        ).status_code
        == 409
    )


def test_site_manager_cannot_approve_invoice(client, db, fake_ai):
    site = auth_headers(make_user(db, role=UserRole.site_manager))
    project = make_project(db)
    item_id = _upload(client, site).json()["item"]["id"]
    fake_ai.messages.parse_responses.append(
        fake_response(parsed_output=_invoice_extraction(project.code))
    )
    assert _process(client, site, item_id).json()["status"] == "drafted"
    res = client.post(f"/api/v1/ingestion/items/{item_id}/approve", headers=site)
    assert res.status_code == 403


def test_reject_and_list_filters(client, db, fake_ai):
    headers = _proc(db)
    item_id = _upload(client, headers).json()["item"]["id"]
    res = client.post(
        f"/api/v1/ingestion/items/{item_id}/reject",
        json={"reason": "Blurry photo"},
        headers=headers,
    )
    assert res.json()["status"] == "rejected"
    assert res.json()["rejection_reason"] == "Blurry photo"

    listed = client.get("/api/v1/ingestion/items?status=rejected", headers=headers).json()
    assert any(i["id"] == item_id for i in listed["items"])
    empty = client.get("/api/v1/ingestion/items?status=posted", headers=headers).json()
    assert all(i["id"] != item_id for i in empty["items"])


def test_file_download_requires_auth(client, db, fake_ai):
    headers = _proc(db)
    item_id = _upload(client, headers, content=b"png-payload").json()["item"]["id"]
    anon = client.get(f"/api/v1/ingestion/items/{item_id}/file")
    assert anon.status_code == 401
    ok = client.get(f"/api/v1/ingestion/items/{item_id}/file", headers=headers)
    assert ok.status_code == 200
    assert ok.content == b"png-payload"
    assert ok.headers["content-type"].startswith("image/png")
