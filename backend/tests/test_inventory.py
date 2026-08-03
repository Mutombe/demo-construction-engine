from decimal import Decimal

from sqlalchemy import select

from app.common.enums import CostSource, UserRole
from app.modules.costs.models import CostEntry
from tests.factories import auth_headers, make_project, make_user


def _proc(db):
    return auth_headers(make_user(db, role=UserRole.procurement_officer))


def _make_item(client, headers, **kw):
    payload = {"code": kw.pop("code", "CEM-425"), "name": "Cement 42.5N", "unit": "bag", **kw}
    res = client.post("/api/v1/stock-items", json=payload, headers=headers)
    assert res.status_code == 201
    return res.json()


def test_item_crud_and_duplicate_code(client, db):
    headers = _proc(db)
    item = _make_item(client, headers)
    assert Decimal(item["qty_on_hand"]) == Decimal("0")
    res = client.post(
        "/api/v1/stock-items",
        json={"code": "CEM-425", "name": "Dup", "unit": "bag"},
        headers=headers,
    )
    assert res.status_code == 409

    res = client.patch(
        f"/api/v1/stock-items/{item['id']}", json={"reorder_level": "50"}, headers=headers
    )
    assert res.status_code == 200
    assert Decimal(res.json()["reorder_level"]) == Decimal("50")


def test_weighted_average_cost(client, db):
    headers = _proc(db)
    item = _make_item(client, headers)

    res = client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "10", "unit_cost": "100.00"},
        headers=headers,
    )
    assert Decimal(res.json()["unit_cost"]) == Decimal("100.00")

    res = client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "10", "unit_cost": "200.00"},
        headers=headers,
    )
    body = res.json()
    assert Decimal(body["unit_cost"]) == Decimal("150.00")
    assert Decimal(body["qty_on_hand"]) == Decimal("20")


def test_issue_posts_cost_entry_and_preserves_wac(client, db):
    headers = _proc(db)
    project = make_project(db)
    item = _make_item(client, headers)
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "10", "unit_cost": "100.00"},
        headers=headers,
    )
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "10", "unit_cost": "200.00"},
        headers=headers,
    )

    res = client.post(
        f"/api/v1/stock-items/{item['id']}/issue",
        json={"project_id": str(project.id), "quantity": "5"},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert Decimal(body["qty_on_hand"]) == Decimal("15")
    assert Decimal(body["unit_cost"]) == Decimal("150.00")  # WAC unchanged by issue

    entries = db.scalars(select(CostEntry).where(CostEntry.project_id == project.id)).all()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.source == CostSource.inventory_issue
    assert entry.amount == Decimal("750.00")
    assert entry.quantity == Decimal("5")
    assert entry.reference.startswith("ISS-")

    movements = client.get(f"/api/v1/stock-items/{item['id']}/movements", headers=headers).json()[
        "items"
    ]
    issue_movement = next(m for m in movements if m["movement_type"] == "issue")
    assert Decimal(issue_movement["quantity"]) == Decimal("-5")
    assert issue_movement["project_name"] is not None


def test_insufficient_stock_guard(client, db):
    headers = _proc(db)
    project = make_project(db)
    item = _make_item(client, headers)
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "3", "unit_cost": "10.00"},
        headers=headers,
    )
    res = client.post(
        f"/api/v1/stock-items/{item['id']}/issue",
        json={"project_id": str(project.id), "quantity": "999"},
        headers=headers,
    )
    assert res.status_code == 409
    # No side effects
    assert db.scalars(select(CostEntry).where(CostEntry.project_id == project.id)).all() == []
    assert Decimal(
        client.get(f"/api/v1/stock-items/{item['id']}", headers=headers).json()["qty_on_hand"]
    ) == Decimal("3")


def test_adjustment_rules(client, db):
    headers = _proc(db)
    item = _make_item(client, headers)
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "10", "unit_cost": "50.00"},
        headers=headers,
    )
    # Below zero -> 409
    res = client.post(
        f"/api/v1/stock-items/{item['id']}/adjust",
        json={"quantity": "-20", "notes": "stocktake"},
        headers=headers,
    )
    assert res.status_code == 409
    # Valid negative adjustment; WAC unchanged
    res = client.post(
        f"/api/v1/stock-items/{item['id']}/adjust",
        json={"quantity": "-2", "notes": "breakage"},
        headers=headers,
    )
    assert Decimal(res.json()["qty_on_hand"]) == Decimal("8")
    assert Decimal(res.json()["unit_cost"]) == Decimal("50.00")
    # Zero adjustment rejected
    res = client.post(
        f"/api/v1/stock-items/{item['id']}/adjust",
        json={"quantity": "0", "notes": "noop"},
        headers=headers,
    )
    assert res.status_code == 422


def test_doc_number_prefixes_independent(client, db):
    headers = _proc(db)
    project = make_project(db)
    item = _make_item(client, headers)
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "10", "unit_cost": "5.00"},
        headers=headers,
    )
    client.post(
        f"/api/v1/stock-items/{item['id']}/issue",
        json={"project_id": str(project.id), "quantity": "1"},
        headers=headers,
    )
    client.post(
        f"/api/v1/stock-items/{item['id']}/adjust",
        json={"quantity": "1", "notes": "found one"},
        headers=headers,
    )
    docs = [
        m["doc_number"]
        for m in client.get(f"/api/v1/stock-items/{item['id']}/movements", headers=headers).json()[
            "items"
        ]
    ]
    prefixes = {d.split("-")[0] for d in docs}
    assert prefixes == {"GRN", "ISS", "ADJ"}
    assert all(d.endswith("-001") for d in docs)


def test_low_stock_flag(client, db):
    headers = _proc(db)
    item = _make_item(client, headers, reorder_level="100")
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "40", "unit_cost": "1.50"},
        headers=headers,
    )
    body = client.get(f"/api/v1/stock-items/{item['id']}", headers=headers).json()
    assert body["low_stock"] is True
    res = client.get("/api/v1/stock-items?low_stock_only=true", headers=headers)
    assert res.json()["total"] == 1


def test_barcode_assignment_and_lookup(client, db):
    headers = _proc(db)
    item = _make_item(client, headers, barcode="6001234567890")
    assert item["barcode"] == "6001234567890"

    res = client.get("/api/v1/stock-items/by-barcode/6001234567890", headers=headers)
    assert res.status_code == 200
    assert res.json()["id"] == item["id"]

    res = client.get("/api/v1/stock-items/by-barcode/0000000000000", headers=headers)
    assert res.status_code == 404


def test_barcode_uniqueness(client, db):
    headers = _proc(db)
    _make_item(client, headers, code="A-1", barcode="111")
    other = _make_item(client, headers, code="A-2")

    # Duplicate on create
    res = client.post(
        "/api/v1/stock-items",
        json={"code": "A-3", "name": "Dup barcode", "unit": "ea", "barcode": "111"},
        headers=headers,
    )
    assert res.status_code == 409

    # Duplicate on update
    res = client.patch(
        f"/api/v1/stock-items/{other['id']}", json={"barcode": "111"}, headers=headers
    )
    assert res.status_code == 409

    # Re-saving an item's own barcode is not a conflict
    first_id = client.get("/api/v1/stock-items/by-barcode/111", headers=headers).json()["id"]
    res = client.patch(f"/api/v1/stock-items/{first_id}", json={"barcode": "111"}, headers=headers)
    assert res.status_code == 200


def test_inventory_roles(client, db):
    viewer = auth_headers(make_user(db, role=UserRole.viewer))
    site = auth_headers(make_user(db, role=UserRole.site_manager))
    proc = _proc(db)
    project = make_project(db)
    item = _make_item(client, proc)
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "10", "unit_cost": "5.00"},
        headers=proc,
    )
    # Viewer: read yes, write no
    assert client.get("/api/v1/stock-items", headers=viewer).status_code == 200
    assert (
        client.post(
            "/api/v1/stock-items", json={"code": "X", "name": "X", "unit": "ea"}, headers=viewer
        ).status_code
        == 403
    )
    # Site manager: can issue, cannot goods-in
    assert (
        client.post(
            f"/api/v1/stock-items/{item['id']}/issue",
            json={"project_id": str(project.id), "quantity": "1"},
            headers=site,
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/stock-items/{item['id']}/goods-in",
            json={"quantity": "1", "unit_cost": "1"},
            headers=site,
        ).status_code
        == 403
    )
