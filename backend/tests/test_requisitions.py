from decimal import Decimal
from datetime import date, timedelta

from sqlalchemy import select

from app.common.enums import RequisitionStatus, UserRole
from app.modules.notifications.models import Notification
from app.modules.requisitions.models import Requisition
from tests.factories import (
    auth_headers,
    make_boq_item,
    make_boq_section,
    make_project,
    make_supplier,
    make_user,
)


def _site(db):
    return auth_headers(make_user(db, role=UserRole.site_manager))


def _proc(db):
    return auth_headers(make_user(db, role=UserRole.procurement_officer))


def _create(client, headers, project_id, **kw):
    payload = {
        "needed_by": kw.pop("needed_by", str(date.today() + timedelta(days=7))),
        "items": kw.pop(
            "items",
            [{"description": "Cement 42.5N", "unit": "bag", "quantity": "200"}],
        ),
        **kw,
    }
    return client.post(
        f"/api/v1/projects/{project_id}/requisitions", json=payload, headers=headers
    )


def test_site_raises_requisition_and_procurement_is_notified(client, db):
    project = make_project(db)
    procurement = make_user(db, role=UserRole.procurement_officer)
    headers = _site(db)

    res = _create(client, headers, project.id, notes="Slab pour on Friday")
    assert res.status_code == 201
    body = res.json()
    year = date.today().year
    assert body["doc_number"] == f"REQ-{year}-001"
    assert body["status"] == "open"
    assert body["item_count"] == 1
    assert body["age_days"] == 0
    assert body["project_name"] == project.name

    notifications = db.scalars(
        select(Notification).where(Notification.user_id == procurement.id)
    ).all()
    assert any(n.type == "requisition_created" for n in notifications)


def test_aging_queue_orders_oldest_open_first(client, db):
    project = make_project(db)
    headers = _site(db)
    first = _create(client, headers, project.id).json()
    second = _create(client, headers, project.id).json()

    # Backdate the first so it is unambiguously older
    db.get(Requisition, first["id"]).created_at = db.get(
        Requisition, first["id"]
    ).created_at - timedelta(days=5)
    db.flush()

    listed = client.get("/api/v1/requisitions", headers=headers).json()
    assert [r["doc_number"] for r in listed["items"]] == [
        first["doc_number"],
        second["doc_number"],
    ]
    aged = listed["items"][0]
    assert aged["age_days"] == 5
    assert aged["is_urgent"] is True  # older than the 3-day threshold
    assert listed["items"][1]["is_urgent"] is False


def test_convert_to_rfq_copies_lines_and_closes_requisition(client, db):
    project = make_project(db)
    section = make_boq_section(db, project)
    boq_item = make_boq_item(db, section, description="Concrete C25", unit="m3")
    site = _site(db)
    requisition = _create(
        client,
        site,
        project.id,
        items=[
            {
                "boq_item_id": str(boq_item.id),
                "description": "Concrete C25",
                "unit": "m3",
                "quantity": "40",
            }
        ],
    ).json()

    res = client.post(
        f"/api/v1/requisitions/{requisition['id']}/convert-to-rfq", headers=_proc(db)
    )
    assert res.status_code == 200
    rfq = res.json()
    assert rfq["status"] == "draft"
    assert len(rfq["items"]) == 1
    assert rfq["items"][0]["boq_item_id"] == str(boq_item.id)

    after = client.get(f"/api/v1/requisitions/{requisition['id']}", headers=site).json()
    assert after["status"] == "actioned"
    assert after["rfq_id"] == rfq["id"]
    assert after["actioned_at"] is not None

    # Already actioned -> cannot convert again
    assert (
        client.post(
            f"/api/v1/requisitions/{requisition['id']}/convert-to-rfq", headers=_proc(db)
        ).status_code
        == 409
    )


def test_convert_to_po_prices_from_last_purchase(client, db):
    project = make_project(db)
    section = make_boq_section(db, project)
    boq_item = make_boq_item(db, section, description="Rebar Y12", unit="kg")
    supplier = make_supplier(db)
    proc = _proc(db)

    # Establish a price history for this BOQ item with that supplier
    client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "items": [
                {
                    "boq_item_id": str(boq_item.id),
                    "description": "Rebar Y12",
                    "unit": "kg",
                    "quantity": "100",
                    "unit_price": "9.50",
                }
            ],
        },
        headers=proc,
    )

    requisition = _create(
        client,
        _site(db),
        project.id,
        items=[
            {
                "boq_item_id": str(boq_item.id),
                "description": "Rebar Y12",
                "unit": "kg",
                "quantity": "300",
            }
        ],
    ).json()

    res = client.post(
        f"/api/v1/requisitions/{requisition['id']}/convert-to-po",
        json={"supplier_id": str(supplier.id)},
        headers=proc,
    )
    assert res.status_code == 200
    po = res.json()
    assert po["status"] == "draft"  # drafts only; a human issues it
    assert po["items"][0]["unit_price"] == "9.50"
    assert po["total_amount"] == "2850.00"  # 300 x 9.50
    # needed_by carries into the expected delivery date
    assert po["expected_delivery"] == requisition["needed_by"]


def test_convert_to_po_without_price_history_is_zero_priced(client, db):
    project = make_project(db)
    supplier = make_supplier(db)
    requisition = _create(client, _site(db), project.id).json()

    po = client.post(
        f"/api/v1/requisitions/{requisition['id']}/convert-to-po",
        json={"supplier_id": str(supplier.id)},
        headers=_proc(db),
    ).json()
    assert po["items"][0]["unit_price"] == "0.00"
    assert po["total_amount"] == "0.00"


def test_cancel_and_foreign_boq_item_guard(client, db):
    project = make_project(db)
    other = make_project(db)
    foreign_item = make_boq_item(db, make_boq_section(db, other))
    site = _site(db)

    res = _create(
        client,
        site,
        project.id,
        items=[
            {
                "boq_item_id": str(foreign_item.id),
                "description": "Wrong project",
                "unit": "ea",
                "quantity": "1",
            }
        ],
    )
    assert res.status_code == 422

    requisition = _create(client, site, project.id).json()
    assert (
        client.post(
            f"/api/v1/requisitions/{requisition['id']}/cancel", headers=site
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/requisitions/{requisition['id']}/cancel", headers=site
        ).status_code
        == 409
    )
    # Cancelled requisitions cannot be converted
    assert (
        client.post(
            f"/api/v1/requisitions/{requisition['id']}/convert-to-rfq", headers=_proc(db)
        ).status_code
        == 409
    )


def test_requisition_rbac(client, db):
    project = make_project(db)
    viewer = auth_headers(make_user(db, role=UserRole.viewer))
    assert _create(client, viewer, project.id).status_code == 403
    # Viewers may still read the queue
    assert client.get("/api/v1/requisitions", headers=viewer).status_code == 200

    requisition = _create(client, _site(db), project.id).json()
    # Site raises but does not action
    assert (
        client.post(
            f"/api/v1/requisitions/{requisition['id']}/convert-to-rfq", headers=_site(db)
        ).status_code
        == 403
    )


def test_filter_by_status_and_project(client, db):
    project = make_project(db)
    other = make_project(db)
    site = _site(db)
    open_req = _create(client, site, project.id).json()
    cancelled = _create(client, site, other.id).json()
    client.post(f"/api/v1/requisitions/{cancelled['id']}/cancel", headers=site)

    by_project = client.get(
        f"/api/v1/requisitions?project_id={project.id}", headers=site
    ).json()
    assert [r["id"] for r in by_project["items"]] == [open_req["id"]]

    by_status = client.get("/api/v1/requisitions?status=cancelled", headers=site).json()
    assert [r["id"] for r in by_status["items"]] == [cancelled["id"]]


# --- Following a line through to what it became ------------------------------


def test_a_line_can_be_opened_even_with_nothing_linked_to_it(client, db):
    """Requisition lines are typed on site and usually carry no bill or stock
    reference. A page that only worked for linked lines would be blank on
    almost every real one."""
    headers = _site(db)
    project = make_project(db)
    res = client.post(
        f"/api/v1/projects/{project.id}/requisitions",
        json={"items": [{"description": "Cement 42.5N 50kg", "unit": "bag",
                         "quantity": "40"}]},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    line_id = res.json()["items"][0]["id"]

    detail = client.get(f"/api/v1/requisition-items/{line_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["description"] == "Cement 42.5N 50kg"
    assert Decimal(body["quantity"]) == Decimal("40.000")
    assert body["matched_by"] == "description"


def test_a_line_finds_the_order_raised_for_it(client, db):
    headers = _site(db)
    proc = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)

    requisition = client.post(
        f"/api/v1/projects/{project.id}/requisitions",
        json={"items": [{"description": "River sand", "unit": "m3", "quantity": "12"}]},
        headers=headers,
    ).json()
    line_id = requisition["items"][0]["id"]

    client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "items": [{"description": "River sand", "unit": "m3", "quantity": "12",
                       "unit_price": "30"}],
        },
        headers=proc,
    )

    body = client.get(f"/api/v1/requisition-items/{line_id}", headers=headers).json()
    assert len(body["orders"]) == 1
    assert body["orders"][0]["supplier_name"] == supplier.name
    assert Decimal(body["ordered_quantity"]) == Decimal("12")


def test_ordering_more_than_was_asked_for_is_visible(client, db):
    headers = _site(db)
    proc = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)

    requisition = client.post(
        f"/api/v1/projects/{project.id}/requisitions",
        json={"items": [{"description": "Rebar Y12", "unit": "tonne", "quantity": "2"}]},
        headers=headers,
    ).json()
    line_id = requisition["items"][0]["id"]

    client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "items": [{"description": "Rebar Y12", "unit": "tonne", "quantity": "5",
                       "unit_price": "900"}],
        },
        headers=proc,
    )

    body = client.get(f"/api/v1/requisition-items/{line_id}", headers=headers).json()
    assert Decimal(body["over_ordered"]) == Decimal("3.000")


def test_another_project_s_order_is_not_credited_to_this_line(client, db):
    """The wording matches across the whole company; the line belongs to one
    job, and only that job's buying counts."""
    headers = _site(db)
    proc = _proc(db)
    ours = make_project(db)
    theirs = make_project(db)
    supplier = make_supplier(db)

    requisition = client.post(
        f"/api/v1/projects/{ours.id}/requisitions",
        json={"items": [{"description": "Shutter ply", "unit": "sheet",
                         "quantity": "20"}]},
        headers=headers,
    ).json()
    line_id = requisition["items"][0]["id"]

    client.post(
        f"/api/v1/projects/{theirs.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "items": [{"description": "Shutter ply", "unit": "sheet", "quantity": "20",
                       "unit_price": "18"}],
        },
        headers=proc,
    )

    body = client.get(f"/api/v1/requisition-items/{line_id}", headers=headers).json()
    assert body["orders"] == []
