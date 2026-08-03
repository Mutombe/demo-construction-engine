from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.common.enums import CostSource, UserRole
from app.modules.costs.models import CostEntry
from tests.factories import (
    auth_headers,
    fake_uuid,
    make_boq_item,
    make_boq_section,
    make_project,
    make_quote,
    make_rfq,
    make_supplier,
    make_user,
)


def _pm(db):
    return auth_headers(make_user(db, role=UserRole.project_manager))


def _proc(db):
    return auth_headers(make_user(db, role=UserRole.procurement_officer))


# --- Suppliers --------------------------------------------------------------


def test_supplier_crud_and_dedupe(client, db):
    headers = _proc(db)
    res = client.post(
        "/api/v1/suppliers", json={"name": "SteelCo", "categories": "steel"}, headers=headers
    )
    assert res.status_code == 201
    supplier_id = res.json()["id"]

    assert (
        client.post("/api/v1/suppliers", json={"name": "SteelCo"}, headers=headers).status_code
        == 409
    )

    res = client.patch(
        f"/api/v1/suppliers/{supplier_id}", json={"is_active": False}, headers=headers
    )
    assert res.status_code == 200
    assert res.json()["is_active"] is False


def test_supplier_write_requires_role(client, db):
    viewer = auth_headers(make_user(db, role=UserRole.viewer))
    assert (
        client.post("/api/v1/suppliers", json={"name": "Nope"}, headers=viewer).status_code == 403
    )


# --- RFQs -------------------------------------------------------------------


def test_rfq_create_snapshots_boq(client, db):
    headers = _proc(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section, description="Cement 42.5N", unit="t", quantity=Decimal("50"))

    res = client.post(
        f"/api/v1/projects/{project.id}/rfqs",
        json={"title": "Cement supply", "items": [{"boq_item_id": str(item.id)}]},
        headers=headers,
    )
    assert res.status_code == 201
    body = res.json()
    assert body["doc_number"].startswith("RFQ-")
    line = body["items"][0]
    assert line["description"] == "Cement 42.5N"
    assert line["unit"] == "t"
    assert Decimal(line["quantity"]) == Decimal("50")

    # Snapshot survives BOQ edits
    client.patch(f"/api/v1/boq/items/{item.id}", json={"description": "CHANGED"}, headers=_pm(db))
    res = client.get(f"/api/v1/rfqs/{body['id']}", headers=headers)
    assert res.json()["items"][0]["description"] == "Cement 42.5N"


def test_rfq_duplicate_boq_item_rejected(client, db):
    headers = _proc(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section)
    res = client.post(
        f"/api/v1/projects/{project.id}/rfqs",
        json={
            "title": "Dup",
            "items": [{"boq_item_id": str(item.id)}, {"boq_item_id": str(item.id)}],
        },
        headers=headers,
    )
    assert res.status_code == 422


def test_rfq_immutable_after_issue(client, db):
    headers = _proc(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section)
    rfq_id = client.post(
        f"/api/v1/projects/{project.id}/rfqs",
        json={"title": "Freeze", "items": [{"boq_item_id": str(item.id)}]},
        headers=headers,
    ).json()["id"]

    assert client.post(f"/api/v1/rfqs/{rfq_id}/issue", headers=headers).status_code == 200
    assert (
        client.patch(f"/api/v1/rfqs/{rfq_id}", json={"title": "X"}, headers=headers).status_code
        == 409
    )
    assert (
        client.put(
            f"/api/v1/rfqs/{rfq_id}/items",
            json={"items": [{"boq_item_id": str(item.id)}]},
            headers=headers,
        ).status_code
        == 409
    )
    assert client.delete(f"/api/v1/rfqs/{rfq_id}", headers=headers).status_code == 409


def test_rfq_doc_numbers_sequence(client, db):
    headers = _proc(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    year = date.today().year
    numbers = []
    for _ in range(2):
        item = make_boq_item(db, section)
        res = client.post(
            f"/api/v1/projects/{project.id}/rfqs",
            json={"title": "Seq", "items": [{"boq_item_id": str(item.id)}]},
            headers=headers,
        )
        numbers.append(res.json()["doc_number"])
    assert numbers[0] == f"RFQ-{year}-001"
    assert numbers[1] == f"RFQ-{year}-002"


# --- Quotes -----------------------------------------------------------------


def test_quote_requires_issued_rfq(client, db):
    headers = _proc(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section)
    supplier = make_supplier(db)
    rfq = make_rfq(db, project, [item], status="draft")
    res = client.post(
        f"/api/v1/rfqs/{rfq.id}/quotes",
        json={
            "supplier_id": str(supplier.id),
            "items": [
                {
                    "rfq_item_id": str(rfq.items[0].id),
                    "description": "d",
                    "quantity": "1",
                    "unit_price": "10",
                }
            ],
        },
        headers=headers,
    )
    assert res.status_code == 409


def test_quote_subset_coverage_and_mismatch_flags(client, db):
    headers = _proc(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    a = make_boq_item(db, section, unit="m3", quantity=Decimal("10"))
    b = make_boq_item(db, section, unit="kg", quantity=Decimal("500"))
    rfq = make_rfq(db, project, [a, b])
    supplier = make_supplier(db)

    res = client.post(
        f"/api/v1/rfqs/{rfq.id}/quotes",
        json={
            "supplier_id": str(supplier.id),
            "items": [
                {
                    # unit + qty mismatch on purpose
                    "rfq_item_id": str(rfq.items[0].id),
                    "description": "Concrete",
                    "unit": "m2",
                    "quantity": "12",
                    "unit_price": "150",
                }
            ],
        },
        headers=headers,
    )
    assert res.status_code == 201
    quote = res.json()
    assert quote["coverage_pct"] == 50.0
    line = quote["items"][0]
    assert line["unit_mismatch"] is True
    assert line["quantity_mismatch"] is True
    assert Decimal(quote["total_amount"]) == Decimal("1800.00")


def test_one_quote_per_supplier(client, db):
    headers = _proc(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section)
    rfq = make_rfq(db, project, [item])
    supplier = make_supplier(db)
    payload = {
        "supplier_id": str(supplier.id),
        "items": [
            {
                "rfq_item_id": str(rfq.items[0].id),
                "description": "d",
                "quantity": "1",
                "unit_price": "10",
            }
        ],
    }
    assert (
        client.post(f"/api/v1/rfqs/{rfq.id}/quotes", json=payload, headers=headers).status_code
        == 201
    )
    assert (
        client.post(f"/api/v1/rfqs/{rfq.id}/quotes", json=payload, headers=headers).status_code
        == 409
    )


def test_accept_quote_rejects_siblings_and_closes_rfq(client, db):
    headers = _proc(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section)
    rfq = make_rfq(db, project, [item])
    q1 = make_quote(db, rfq, make_supplier(db))
    q2 = make_quote(db, rfq, make_supplier(db))

    res = client.post(f"/api/v1/quotes/{q1.id}/accept", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "accepted"

    quotes = client.get(f"/api/v1/rfqs/{rfq.id}/quotes", headers=headers).json()
    by_id = {q["id"]: q["status"] for q in quotes}
    assert by_id[str(q2.id)] == "rejected"
    assert client.get(f"/api/v1/rfqs/{rfq.id}", headers=headers).json()["status"] == "closed"

    # Accepting again fails — RFQ is closed
    assert client.post(f"/api/v1/quotes/{q2.id}/accept", headers=headers).status_code == 409


# --- Purchase orders + the money test ---------------------------------------


def test_po_full_lifecycle_writes_cost_entries(client, db):
    """BOQ -> RFQ -> quote -> accept -> PO -> issue -> receive => budget actuals move."""
    headers = _proc(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    boq_a = make_boq_item(db, section, quantity=Decimal("10"), rate=Decimal("200"))
    boq_b = make_boq_item(db, section, quantity=Decimal("5"), rate=Decimal("400"))
    rfq = make_rfq(db, project, [boq_a, boq_b])
    supplier = make_supplier(db, name="Winner Ltd")
    line_ids = {item.boq_item_id: item.id for item in rfq.items}
    quote = make_quote(
        db,
        rfq,
        supplier,
        prices={line_ids[boq_a.id]: Decimal("180"), line_ids[boq_b.id]: Decimal("390")},
    )
    client.post(f"/api/v1/quotes/{quote.id}/accept", headers=headers)

    # PO from quote — lines derived deterministically
    res = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={"quote_id": str(quote.id)},
        headers=headers,
    )
    assert res.status_code == 201
    po = res.json()
    assert po["doc_number"].startswith("PO-")
    assert po["supplier_name"] == "Winner Ltd"
    assert Decimal(po["total_amount"]) == Decimal("10") * 180 + Decimal("5") * 390
    boq_ids = {line["boq_item_id"] for line in po["items"]}
    assert boq_ids == {str(boq_a.id), str(boq_b.id)}

    # Receive before issue -> 409
    assert (
        client.post(
            f"/api/v1/purchase-orders/{po['id']}/receive", json={}, headers=headers
        ).status_code
        == 409
    )

    assert (
        client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers).status_code == 200
    )
    res = client.post(f"/api/v1/purchase-orders/{po['id']}/receive", json={}, headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "received"

    entries = db.scalars(select(CostEntry).where(CostEntry.project_id == project.id)).all()
    assert len(entries) == 2
    assert all(e.source == CostSource.purchase_order for e in entries)
    assert all(e.reference == po["doc_number"] for e in entries)
    assert {e.boq_item_id for e in entries} == {boq_a.id, boq_b.id}
    assert sum(e.amount for e in entries) == Decimal(po["total_amount"])

    # Project actuals now include the PO total
    summary = client.get(f"/api/v1/projects/{project.id}/summary", headers=headers).json()
    assert Decimal(summary["actual_total"]) == Decimal(po["total_amount"])

    # Double receive impossible; cancel after receipt impossible
    assert (
        client.post(
            f"/api/v1/purchase-orders/{po['id']}/receive", json={}, headers=headers
        ).status_code
        == 409
    )
    assert (
        client.post(f"/api/v1/purchase-orders/{po['id']}/cancel", headers=headers).status_code
        == 409
    )


def _issued_po(client, db, headers, project):
    supplier = make_supplier(db)
    po = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "items": [
                {"description": "Cement 42.5N", "unit": "bag", "quantity": "100",
                 "unit_price": "12.00"},
                {"description": "Rebar Y10", "unit": "length", "quantity": "50",
                 "unit_price": "8.00"},
            ],
        },
        headers=headers,
    ).json()
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)
    return client.get(f"/api/v1/purchase-orders/{po['id']}", headers=headers).json()


def test_receive_po_to_store(client, db):
    headers = _proc(db)
    project = make_project(db)
    po = _issued_po(client, db, headers, project)

    # One existing stock item + one created inline
    existing = client.post(
        "/api/v1/stock-items",
        json={"code": "CEM-T1", "name": "Cement", "unit": "bag"},
        headers=headers,
    ).json()
    res = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        json={
            "destination": "store",
            "store_lines": [
                {"po_item_id": po["items"][0]["id"], "stock_item_id": existing["id"]},
                {
                    "po_item_id": po["items"][1]["id"],
                    "new_item": {"code": "REB-T1", "name": "Rebar Y10", "unit": "length"},
                },
            ],
        },
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "received"
    assert res.json()["received_to"] == "store"

    # Stock updated at PO prices; GRN movements reference the PO
    cement = client.get(f"/api/v1/stock-items/{existing['id']}", headers=headers).json()
    assert Decimal(cement["qty_on_hand"]) == Decimal("100")
    assert Decimal(cement["unit_cost"]) == Decimal("12.00")
    movements = client.get(
        f"/api/v1/stock-items/{existing['id']}/movements", headers=headers
    ).json()["items"]
    assert movements[0]["reference"] == po["doc_number"]

    # ZERO cost entries — cost hits the project only on issue
    entries = db.scalars(
        select(CostEntry).where(CostEntry.project_id == project.id)
    ).all()
    assert entries == []


def test_receive_to_store_mapping_validation(client, db):
    headers = _proc(db)
    project = make_project(db)
    po = _issued_po(client, db, headers, project)

    # Unmapped line
    res = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        json={
            "destination": "store",
            "store_lines": [
                {"po_item_id": po["items"][0]["id"],
                 "new_item": {"code": "X1", "name": "X", "unit": "ea"}},
            ],
        },
        headers=headers,
    )
    assert res.status_code == 422

    # Both stock_item_id and new_item on one line
    res = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        json={
            "destination": "store",
            "store_lines": [
                {"po_item_id": po["items"][0]["id"], "stock_item_id": fake_uuid(),
                 "new_item": {"code": "X2", "name": "X", "unit": "ea"}},
                {"po_item_id": po["items"][1]["id"],
                 "new_item": {"code": "X3", "name": "X", "unit": "ea"}},
            ],
        },
        headers=headers,
    )
    assert res.status_code == 422


def test_receive_to_project_regression(client, db):
    headers = _proc(db)
    project = make_project(db)
    po = _issued_po(client, db, headers, project)
    res = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive", json={}, headers=headers
    )
    assert res.status_code == 200
    assert res.json()["received_to"] == "project"
    entries = db.scalars(select(CostEntry).where(CostEntry.project_id == project.id)).all()
    assert len(entries) == 2
    assert sum(e.amount for e in entries) == Decimal(po["total_amount"])


def test_po_freeform_requires_supplier_and_items(client, db):
    headers = _proc(db)
    project = make_project(db)
    res = client.post(f"/api/v1/projects/{project.id}/purchase-orders", json={}, headers=headers)
    assert res.status_code == 422


def test_po_edit_only_in_draft(client, db):
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)
    po = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "items": [{"description": "Sand", "quantity": "10", "unit_price": "25"}],
        },
        headers=headers,
    ).json()
    assert (
        client.patch(
            f"/api/v1/purchase-orders/{po['id']}", json={"notes": "ok"}, headers=headers
        ).status_code
        == 200
    )
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)
    assert (
        client.patch(
            f"/api/v1/purchase-orders/{po['id']}", json={"notes": "no"}, headers=headers
        ).status_code
        == 409
    )
