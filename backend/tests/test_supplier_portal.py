"""Suppliers looking after their own account.

Two things matter more than the rest. A portal link must not become a way to
read somebody else's orders, and an invoice must not become a second payable —
receiving the goods already created one, and owing a supplier twice for one
delivery is the expensive mistake here.
"""

from decimal import Decimal

from app.common.enums import UserRole
from tests.factories import auth_headers, make_project, make_supplier, make_user


def _proc(db):
    return auth_headers(make_user(db, role=UserRole.procurement_officer))


def _link(client, headers, supplier):
    res = client.post(
        f"/api/v1/suppliers/{supplier.id}/portal-links",
        json={"days": 90},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()["url"].rsplit("/", 1)[1]


def _order(client, headers, project, supplier, total="5000"):
    res = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "items": [
                {
                    "description": "Cement",
                    "quantity": "100",
                    "unit": "bag",
                    "unit_price": str(Decimal(total) / 100),
                }
            ],
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


# --- The link ----------------------------------------------------------------


def test_a_link_shows_that_supplier_their_own_orders(client, db):
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)
    order = _order(client, headers, project, supplier)
    token = _link(client, headers, supplier)

    res = client.get(f"/api/v1/supplier-portal/{token}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["supplier_name"] == supplier.name
    assert any(o["doc_number"] == order["doc_number"] for o in body["orders"])


def test_a_link_shows_nobody_else_s_orders(client, db):
    headers = _proc(db)
    project = make_project(db)
    ours = make_supplier(db, name="Ours")
    theirs = make_supplier(db, name="Theirs")
    _order(client, headers, project, theirs)
    token = _link(client, headers, ours)

    body = client.get(f"/api/v1/supplier-portal/{token}").json()
    assert body["orders"] == []


def test_a_revoked_link_stops_working(client, db):
    headers = _proc(db)
    supplier = make_supplier(db)
    res = client.post(
        f"/api/v1/suppliers/{supplier.id}/portal-links", json={"days": 90}, headers=headers
    ).json()
    token = res["url"].rsplit("/", 1)[1]

    assert client.get(f"/api/v1/supplier-portal/{token}").status_code == 200
    client.delete(f"/api/v1/portal-links/{res['id']}", headers=headers)
    assert client.get(f"/api/v1/supplier-portal/{token}").status_code == 404


def test_a_made_up_link_is_refused_the_same_way_as_a_revoked_one(client, db):
    """Different answers would let somebody work out which links exist."""
    res = client.get("/api/v1/supplier-portal/not-a-real-token")
    assert res.status_code == 404


def test_the_staff_side_is_not_reachable_without_logging_in(client, db):
    headers = _proc(db)
    supplier = make_supplier(db)
    assert (
        client.post(f"/api/v1/suppliers/{supplier.id}/portal-links", json={"days": 30}).status_code
        == 401
    )
    assert client.get("/api/v1/supplier-invoices").status_code == 401
    # And still works for someone who is logged in.
    assert client.get("/api/v1/supplier-invoices", headers=headers).status_code == 200


# --- Invoices ----------------------------------------------------------------


def test_an_invoice_records_a_claim_and_does_not_post_again(client, db):
    """Receiving the order already created the payable. Booking the invoice as
    well would owe the supplier twice for one delivery."""
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)
    order = _order(client, headers, project, supplier)
    token = _link(client, headers, supplier)

    # Reading the books is not a procurement role, so this check logs in as
    # somebody who can.
    books = auth_headers(make_user(db, role=UserRole.admin))
    before = client.get("/api/v1/accounting/trial-balance", headers=books).json()
    res = client.post(
        f"/api/v1/supplier-portal/{token}/invoices",
        json={"purchase_order_id": order["id"], "reference": "INV-99", "amount": "5000"},
    )
    assert res.status_code == 201, res.text
    after = client.get("/api/v1/accounting/trial-balance", headers=books).json()

    assert Decimal(after["total_credit"]) == Decimal(before["total_credit"])
    assert Decimal(after["total_debit"]) == Decimal(before["total_debit"])


def test_the_same_invoice_number_cannot_be_submitted_twice(client, db):
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)
    order = _order(client, headers, project, supplier)
    token = _link(client, headers, supplier)

    body = {"purchase_order_id": order["id"], "reference": "INV-100", "amount": "5000"}
    assert client.post(f"/api/v1/supplier-portal/{token}/invoices", json=body).status_code == 201
    again = client.post(f"/api/v1/supplier-portal/{token}/invoices", json=body)
    assert again.status_code == 409
    assert "already been submitted" in again.json()["error"]["detail"]


def test_an_invoice_cannot_be_hung_on_another_supplier_s_order(client, db):
    headers = _proc(db)
    project = make_project(db)
    ours = make_supplier(db, name="Ours")
    theirs = make_supplier(db, name="Theirs")
    their_order = _order(client, headers, project, theirs)
    token = _link(client, headers, ours)

    res = client.post(
        f"/api/v1/supplier-portal/{token}/invoices",
        json={"purchase_order_id": their_order["id"], "amount": "5000"},
    )
    assert res.status_code == 404


def test_billing_more_than_was_ordered_is_flagged(client, db):
    """The reason the portal earns its keep: caught before it is paid."""
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)
    order = _order(client, headers, project, supplier, total="5000")
    token = _link(client, headers, supplier)

    client.post(
        f"/api/v1/supplier-portal/{token}/invoices",
        json={"purchase_order_id": order["id"], "reference": "INV-7", "amount": "6200"},
    )

    rows = client.get("/api/v1/supplier-invoices/matching", headers=headers).json()
    row = next(r for r in rows if r["reference"] == "INV-7")
    assert Decimal(row["variance"]) == Decimal("1200.00")
    assert row["issue"] == "Over the order"


def test_rounding_is_not_treated_as_a_dispute(client, db):
    """A system that queries three cents is a system people stop reading."""
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)
    order = _order(client, headers, project, supplier, total="5000")
    token = _link(client, headers, supplier)

    client.post(
        f"/api/v1/supplier-portal/{token}/invoices",
        json={"purchase_order_id": order["id"], "reference": "INV-8", "amount": "5000.40"},
    )

    rows = client.get("/api/v1/supplier-invoices/matching", headers=headers).json()
    assert all(r["reference"] != "INV-8" for r in rows)


def test_an_invoice_with_no_order_is_a_different_problem(client, db):
    headers = _proc(db)
    supplier = make_supplier(db)
    token = _link(client, headers, supplier)

    client.post(
        f"/api/v1/supplier-portal/{token}/invoices",
        json={"reference": "INV-9", "amount": "800"},
    )

    rows = client.get("/api/v1/supplier-invoices/matching", headers=headers).json()
    row = next(r for r in rows if r["reference"] == "INV-9")
    assert row["issue"] == "No order given"
    assert row["variance"] is None


def test_a_query_has_to_say_what_is_wrong(client, db):
    """A query with no reason gets resubmitted unchanged."""
    headers = _proc(db)
    supplier = make_supplier(db)
    token = _link(client, headers, supplier)
    invoice = client.post(
        f"/api/v1/supplier-portal/{token}/invoices",
        json={"reference": "INV-10", "amount": "800"},
    ).json()

    res = client.post(
        f"/api/v1/supplier-invoices/{invoice['id']}/decide",
        json={"accept": False},
        headers=headers,
    )
    assert res.status_code == 422


def test_the_supplier_sees_why_their_invoice_was_queried(client, db):
    headers = _proc(db)
    supplier = make_supplier(db)
    token = _link(client, headers, supplier)
    invoice = client.post(
        f"/api/v1/supplier-portal/{token}/invoices",
        json={"reference": "INV-11", "amount": "800"},
    ).json()

    client.post(
        f"/api/v1/supplier-invoices/{invoice['id']}/decide",
        json={"accept": False, "note": "Send the delivery note with it"},
        headers=headers,
    )

    body = client.get(f"/api/v1/supplier-portal/{token}").json()
    row = next(i for i in body["invoices"] if i["reference"] == "INV-11")
    assert row["status"] == "queried"
    assert row["note"] == "Send the delivery note with it"


def test_a_decision_is_made_once(client, db):
    headers = _proc(db)
    supplier = make_supplier(db)
    token = _link(client, headers, supplier)
    invoice = client.post(
        f"/api/v1/supplier-portal/{token}/invoices",
        json={"reference": "INV-12", "amount": "800"},
    ).json()

    url = f"/api/v1/supplier-invoices/{invoice['id']}/decide"
    assert client.post(url, json={"accept": True}, headers=headers).status_code == 200
    assert client.post(url, json={"accept": True}, headers=headers).status_code == 409
