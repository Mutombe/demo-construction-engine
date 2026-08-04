"""Delivery tracking, supplier scorecards and the stock reorder loop."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.common.enums import PoStatus, UserRole
from app.modules.notifications.models import Notification
from app.modules.procurement.models import PurchaseOrder
from tests.factories import auth_headers, make_project, make_supplier, make_user


def _proc(db):
    return auth_headers(make_user(db, role=UserRole.procurement_officer))


def _make_po(client, headers, project_id, supplier_id, *, price="100.00", qty="10", **kw):
    payload = {
        "supplier_id": str(supplier_id),
        "items": [
            {"description": "Cement", "unit": "bag", "quantity": qty, "unit_price": price}
        ],
        **kw,
    }
    res = client.post(
        f"/api/v1/projects/{project_id}/purchase-orders", json=payload, headers=headers
    )
    assert res.status_code == 201
    return res.json()


def test_issued_po_past_expected_date_is_overdue(client, db):
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)
    past = date.today() - timedelta(days=4)

    po = _make_po(
        client, headers, project.id, supplier.id, expected_delivery=str(past)
    )
    # Drafts are not overdue — nothing has been sent to the supplier yet
    assert po["is_overdue"] is False

    issued = client.post(
        f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers
    ).json()
    assert issued["is_overdue"] is True
    assert issued["days_overdue"] == 4

    # Receiving it clears the flag
    received = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        json={"destination": "project"},
        headers=headers,
    ).json()
    assert received["is_overdue"] is False
    assert received["days_overdue"] == 0


def test_po_without_expected_date_is_never_overdue(client, db):
    headers = _proc(db)
    project = make_project(db)
    po = _make_po(client, headers, project.id, make_supplier(db).id)
    issued = client.post(
        f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers
    ).json()
    assert issued["is_overdue"] is False


def test_procurement_pulse_and_deduped_overdue_notification(client, db):
    headers = _proc(db)
    officer = make_user(db, role=UserRole.procurement_officer)
    project = make_project(db)
    supplier = make_supplier(db)
    po = _make_po(
        client,
        headers,
        project.id,
        supplier.id,
        expected_delivery=str(date.today() - timedelta(days=2)),
    )
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)

    # Site raises a requisition that nobody has actioned
    site = auth_headers(make_user(db, role=UserRole.site_manager))
    client.post(
        f"/api/v1/projects/{project.id}/requisitions",
        json={"items": [{"description": "Sand", "unit": "m3", "quantity": "5"}]},
        headers=site,
    )

    pulse = client.get("/api/v1/dashboard/procurement-pulse", headers=headers).json()
    assert pulse["overdue_deliveries"] == 1
    assert pulse["open_requisitions"] == 1
    assert Decimal(pulse["overdue_value"]) == Decimal("1000.00")
    assert pulse["deliveries"][0]["doc_number"] == po["doc_number"]
    assert pulse["deliveries"][0]["days_overdue"] == 2

    def overdue_notices():
        return db.scalars(
            select(Notification).where(
                Notification.user_id == officer.id, Notification.type == "po_overdue"
            )
        ).all()

    assert len(overdue_notices()) == 1
    # Reading the pulse again must not re-notify about the same PO
    client.get("/api/v1/dashboard/procurement-pulse", headers=headers)
    assert len(overdue_notices()) == 1


def test_supplier_scorecard_measures_delivery_and_response(client, db):
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)

    # One delivered late by 3 days, one delivered early
    late = _make_po(
        client,
        headers,
        project.id,
        supplier.id,
        expected_delivery=str(date.today() - timedelta(days=10)),
    )
    client.post(f"/api/v1/purchase-orders/{late['id']}/issue", headers=headers)
    client.post(
        f"/api/v1/purchase-orders/{late['id']}/receive",
        json={
            "destination": "project",
            "received_date": str(date.today() - timedelta(days=7)),
        },
        headers=headers,
    )

    early = _make_po(
        client,
        headers,
        project.id,
        supplier.id,
        expected_delivery=str(date.today() - timedelta(days=5)),
    )
    client.post(f"/api/v1/purchase-orders/{early['id']}/issue", headers=headers)
    client.post(
        f"/api/v1/purchase-orders/{early['id']}/receive",
        json={
            "destination": "project",
            "received_date": str(date.today() - timedelta(days=6)),
        },
        headers=headers,
    )

    # And one still outstanding, already overdue
    open_late = _make_po(
        client,
        headers,
        project.id,
        supplier.id,
        expected_delivery=str(date.today() - timedelta(days=1)),
    )
    client.post(f"/api/v1/purchase-orders/{open_late['id']}/issue", headers=headers)

    activity = client.get(
        f"/api/v1/suppliers/{supplier.id}/activity", headers=headers
    ).json()
    card = activity["scorecard"]
    assert card["delivered_count"] == 2
    assert card["on_time_count"] == 1
    assert Decimal(card["on_time_pct"]) == Decimal("50.0")
    assert Decimal(card["avg_delay_days"]) == Decimal("3.0")  # only the late one counts
    assert card["open_overdue_count"] == 1


def test_scorecard_is_honest_about_no_history(client, db):
    headers = _proc(db)
    supplier = make_supplier(db)
    card = client.get(
        f"/api/v1/suppliers/{supplier.id}/activity", headers=headers
    ).json()["scorecard"]
    assert card["delivered_count"] == 0
    assert card["on_time_pct"] is None  # not a misleading 0%
    assert card["avg_delay_days"] is None
    assert card["avg_quote_response_days"] is None


def test_reorder_suggestions_use_last_delivery_supplier_and_price(client, db):
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db, name="Blue Circle")

    item = client.post(
        "/api/v1/stock-items",
        json={"code": "CEM-425", "name": "Cement", "unit": "bag", "reorder_level": "100"},
        headers=headers,
    ).json()

    # Deliver stock through a PO so the supplier/price link exists
    po = _make_po(
        client, headers, project.id, supplier.id, price="12.40", qty="30"
    )
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)
    client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        json={
            "destination": "store",
            "store_lines": [
                {
                    "po_item_id": po["items"][0]["id"],
                    "stock_item_id": item["id"],
                }
            ],
        },
        headers=headers,
    )

    suggestions = client.get(
        "/api/v1/stock-items/reorder-suggestions", headers=headers
    ).json()
    assert suggestions["without_supplier"] == 0
    row = next(s for s in suggestions["items"] if s["stock_item_id"] == item["id"])
    # 30 on hand against a 100 reorder level -> top up to 200
    assert Decimal(row["suggested_quantity"]) == Decimal("170.000")
    assert Decimal(row["last_unit_cost"]) == Decimal("12.40")
    assert Decimal(row["estimated_cost"]) == Decimal("2108.00")
    assert row["supplier_name"] == "Blue Circle"
    assert row["last_po_number"] == po["doc_number"]

    # One click raises a draft PO for that supplier
    result = client.post(
        "/api/v1/stock-items/reorder",
        json={"project_id": str(project.id), "stock_item_ids": [item["id"]]},
        headers=headers,
    )
    assert result.status_code == 201
    body = result.json()
    assert len(body["po_ids"]) == 1
    assert body["skipped_items"] == []

    reorder_po = db.get(PurchaseOrder, body["po_ids"][0])
    assert reorder_po.status == PoStatus.draft  # human issues it
    assert reorder_po.supplier_id == supplier.id
    assert reorder_po.total_amount == Decimal("2108.00")


def test_reorder_skips_items_with_no_purchase_history(client, db):
    headers = _proc(db)
    project = make_project(db)
    item = client.post(
        "/api/v1/stock-items",
        json={"code": "NEW-1", "name": "Never bought", "unit": "ea", "reorder_level": "10"},
        headers=headers,
    ).json()

    suggestions = client.get(
        "/api/v1/stock-items/reorder-suggestions", headers=headers
    ).json()
    row = next(s for s in suggestions["items"] if s["stock_item_id"] == item["id"])
    assert row["supplier_id"] is None
    assert suggestions["without_supplier"] == 1

    body = client.post(
        "/api/v1/stock-items/reorder",
        json={"project_id": str(project.id), "stock_item_ids": [item["id"]]},
        headers=headers,
    ).json()
    assert body["po_ids"] == []
    assert body["skipped_items"] == ["NEW-1"]


def test_reorder_groups_lines_by_supplier(client, db):
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)
    codes = ["A-1", "A-2"]
    item_ids = []
    for code in codes:
        item = client.post(
            "/api/v1/stock-items",
            json={"code": code, "name": code, "unit": "ea", "reorder_level": "10"},
            headers=headers,
        ).json()
        po = _make_po(client, headers, project.id, supplier.id, price="5.00", qty="2")
        client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)
        client.post(
            f"/api/v1/purchase-orders/{po['id']}/receive",
            json={
                "destination": "store",
                "store_lines": [
                    {"po_item_id": po["items"][0]["id"], "stock_item_id": item["id"]}
                ],
            },
            headers=headers,
        )
        item_ids.append(item["id"])

    body = client.post(
        "/api/v1/stock-items/reorder",
        json={"project_id": str(project.id), "stock_item_ids": item_ids},
        headers=headers,
    ).json()
    # Both items share a supplier -> one PO with two lines
    assert len(body["po_ids"]) == 1
    po = db.get(PurchaseOrder, body["po_ids"][0])
    assert len(po.items) == 2


def test_reorder_requires_write_role(client, db):
    project = make_project(db)
    site = auth_headers(make_user(db, role=UserRole.site_manager))
    res = client.post(
        "/api/v1/stock-items/reorder",
        json={"project_id": str(project.id), "stock_item_ids": []},
        headers=site,
    )
    assert res.status_code in (403, 422)
