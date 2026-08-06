"""Who owes what, for how long, and settling it."""

from datetime import date, timedelta
from decimal import Decimal

from app.common.enums import UserRole
from tests.factories import (
    auth_headers,
    make_client_record,
    make_project,
    make_supplier,
    make_user,
)


def _admin(db):
    return auth_headers(make_user(db, role=UserRole.admin))


def _balance(client, headers, code):
    rows = client.get("/api/v1/accounting/accounts", headers=headers).json()
    return Decimal(next(a["balance"] for a in rows if a["code"] == code))


def _received_po(client, db, headers, project, supplier, amount="1000.00", received=None):
    po = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "items": [
                {"description": "Cement", "unit": "bag", "quantity": "1", "unit_price": amount}
            ],
        },
        headers=headers,
    ).json()
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)
    body = {"destination": "project"}
    if received:
        body["received_date"] = str(received)
    client.post(f"/api/v1/purchase-orders/{po['id']}/receive", json=body, headers=headers)
    return po


def _issued_valuation(client, headers, project, gross="10000", issued=None):
    valuation = client.post(
        f"/api/v1/projects/{project.id}/valuations",
        json={"period_end": str(date.today()), "gross_valuation": gross},
        headers=headers,
    ).json()
    body = {"issued_date": str(issued)} if issued else {}
    client.post(f"/api/v1/valuations/{valuation['id']}/issue", json=body, headers=headers)
    return valuation


# --- Receivables -------------------------------------------------------------


def test_an_issued_certificate_appears_in_receivables(client, db):
    headers = _admin(db)
    record = make_client_record(db, name="Riverside Group")
    project = make_project(db, client=record, contract_value=Decimal("100000"))
    _issued_valuation(client, headers, project, "10000")

    body = client.get("/api/v1/accounting/receivables", headers=headers).json()
    party = next(p for p in body["parties"] if p["party_name"] == "Riverside Group")
    assert Decimal(party["total"]) == Decimal("10000.00")
    assert Decimal(body["total"]) == Decimal("10000.00")


def test_receivables_age_into_buckets_from_the_issue_date(client, db):
    headers = _admin(db)
    record = make_client_record(db, name="Slow Payer")
    project = make_project(db, client=record, contract_value=Decimal("500000"))
    _issued_valuation(client, headers, project, "5000", issued=date.today() - timedelta(days=100))

    body = client.get("/api/v1/accounting/receivables", headers=headers).json()
    party = next(p for p in body["parties"] if p["party_name"] == "Slow Payer")
    assert Decimal(party["buckets"]["Over 90 days"]) == Decimal("5000.00")
    assert Decimal(party["buckets"]["Current"]) == 0
    assert party["documents"][0]["days"] >= 100


def test_retention_is_not_chased_as_a_debt(client, db):
    """It is withheld by agreement until the defects period ends, so ageing it
    would show every finished job as a debt problem."""
    headers = _admin(db)
    record = make_client_record(db)
    project = make_project(
        db, client=record, contract_value=Decimal("100000"), retention_pct=Decimal("10")
    )
    _issued_valuation(client, headers, project, "10000")

    body = client.get("/api/v1/accounting/receivables", headers=headers).json()
    # Gross 10000 less 10% retention: only the certified 9000 is owed now
    assert Decimal(body["total"]) == Decimal("9000.00")


def test_paying_a_certificate_clears_the_receivable_in_the_books(client, db):
    """Without this the receivable only ever grew: issuing debited it and
    nothing ever credited it back."""
    headers = _admin(db)
    record = make_client_record(db)
    project = make_project(db, client=record, contract_value=Decimal("100000"))
    valuation = _issued_valuation(client, headers, project, "10000")
    assert _balance(client, headers, "1100") == Decimal("10000.00")

    res = client.post(
        f"/api/v1/valuations/{valuation['id']}/pay", json={}, headers=headers
    )
    assert res.status_code == 200

    assert _balance(client, headers, "1100") == 0
    assert _balance(client, headers, "1000") == Decimal("10000.00")
    assert client.get("/api/v1/accounting/receivables", headers=headers).json()["total"] == "0.00"


# --- Payables ----------------------------------------------------------------


def test_a_received_order_shows_as_owed(client, db):
    headers = _admin(db)
    project = make_project(db)
    supplier = make_supplier(db, name="Blue Circle")
    _received_po(client, db, headers, project, supplier, "1200.00")

    body = client.get("/api/v1/accounting/payables", headers=headers).json()
    party = next(p for p in body["parties"] if p["party_name"] == "Blue Circle")
    assert Decimal(party["total"]) == Decimal("1200.00")


def test_payables_age_from_delivery_not_from_the_order(client, db):
    """The debt becomes real when the goods arrive; ageing from the order date
    would chase something that has not been delivered."""
    headers = _admin(db)
    project = make_project(db)
    supplier = make_supplier(db, name="Late Delivery")
    _received_po(
        client, db, headers, project, supplier, "800.00",
        received=date.today() - timedelta(days=75),
    )

    body = client.get("/api/v1/accounting/payables", headers=headers).json()
    party = next(p for p in body["parties"] if p["party_name"] == "Late Delivery")
    assert Decimal(party["buckets"]["61 to 90 days"]) == Decimal("800.00")


def test_paying_a_supplier_clears_the_payable_and_the_bank(client, db):
    headers = _admin(db)
    project = make_project(db)
    supplier = make_supplier(db, name="Blue Circle")
    po = _received_po(client, db, headers, project, supplier, "1000.00")
    assert _balance(client, headers, "2000") == Decimal("1000.00")

    res = client.post(
        "/api/v1/accounting/payments",
        json={
            "supplier_id": str(supplier.id),
            "amount": "1000.00",
            "method": "Bank transfer",
            "allocations": [{"purchase_order_id": po["id"], "amount": "1000.00"}],
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    assert res.json()["doc_number"].startswith("PAY")

    assert _balance(client, headers, "2000") == 0
    assert _balance(client, headers, "1000") == Decimal("-1000.00")
    assert client.get("/api/v1/accounting/payables", headers=headers).json()["total"] == "0.00"


def test_a_part_payment_leaves_the_rest_outstanding(client, db):
    headers = _admin(db)
    project = make_project(db)
    supplier = make_supplier(db, name="Part Paid")
    po = _received_po(client, db, headers, project, supplier, "1000.00")

    client.post(
        "/api/v1/accounting/payments",
        json={
            "supplier_id": str(supplier.id),
            "amount": "400.00",
            "allocations": [{"purchase_order_id": po["id"], "amount": "400.00"}],
        },
        headers=headers,
    )

    body = client.get("/api/v1/accounting/payables", headers=headers).json()
    party = next(p for p in body["parties"] if p["party_name"] == "Part Paid")
    assert Decimal(party["total"]) == Decimal("600.00")
    assert Decimal(party["documents"][0]["amount"]) == Decimal("1000.00")
    assert Decimal(party["documents"][0]["outstanding"]) == Decimal("600.00")


def test_an_order_cannot_be_paid_twice_over(client, db):
    headers = _admin(db)
    project = make_project(db)
    supplier = make_supplier(db)
    po = _received_po(client, db, headers, project, supplier, "500.00")

    def pay(amount):
        return client.post(
            "/api/v1/accounting/payments",
            json={
                "supplier_id": str(supplier.id),
                "amount": amount,
                "allocations": [{"purchase_order_id": po["id"], "amount": amount}],
            },
            headers=headers,
        )

    assert pay("500.00").status_code == 201
    second = pay("500.00")
    assert second.status_code == 422
    assert "outstanding" in second.json()["error"]["detail"]


def test_allocations_have_to_add_up_to_the_payment(client, db):
    """Money with no invoice against it is a credit on account, not a payment,
    and pretending otherwise makes both the ageing and the ledger wrong."""
    headers = _admin(db)
    project = make_project(db)
    supplier = make_supplier(db)
    po = _received_po(client, db, headers, project, supplier, "900.00")

    res = client.post(
        "/api/v1/accounting/payments",
        json={
            "supplier_id": str(supplier.id),
            "amount": "900.00",
            "allocations": [{"purchase_order_id": po["id"], "amount": "500.00"}],
        },
        headers=headers,
    )
    assert res.status_code == 422
    assert "come to" in res.json()["error"]["detail"]


def test_an_order_that_has_not_arrived_cannot_be_paid(client, db):
    headers = _admin(db)
    project = make_project(db)
    supplier = make_supplier(db)
    po = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "items": [
                {"description": "Cement", "unit": "bag", "quantity": "1", "unit_price": "100"}
            ],
        },
        headers=headers,
    ).json()
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)

    res = client.post(
        "/api/v1/accounting/payments",
        json={
            "supplier_id": str(supplier.id),
            "amount": "100.00",
            "allocations": [{"purchase_order_id": po["id"], "amount": "100.00"}],
        },
        headers=headers,
    )
    assert res.status_code == 409
    assert "not been received" in res.json()["error"]["detail"]


def test_paying_another_suppliers_order_is_refused(client, db):
    headers = _admin(db)
    project = make_project(db)
    theirs, mine = make_supplier(db, name="Theirs"), make_supplier(db, name="Mine")
    po = _received_po(client, db, headers, project, theirs, "300.00")

    res = client.post(
        "/api/v1/accounting/payments",
        json={
            "supplier_id": str(mine.id),
            "amount": "300.00",
            "allocations": [{"purchase_order_id": po["id"], "amount": "300.00"}],
        },
        headers=headers,
    )
    assert res.status_code == 422
    assert "different supplier" in res.json()["error"]["detail"]


def test_open_orders_show_what_is_left_to_pay(client, db):
    headers = _admin(db)
    project = make_project(db)
    supplier = make_supplier(db)
    po = _received_po(client, db, headers, project, supplier, "1000.00")
    client.post(
        "/api/v1/accounting/payments",
        json={
            "supplier_id": str(supplier.id),
            "amount": "250.00",
            "allocations": [{"purchase_order_id": po["id"], "amount": "250.00"}],
        },
        headers=headers,
    )

    open_orders = client.get(
        f"/api/v1/accounting/suppliers/{supplier.id}/open-orders", headers=headers
    ).json()
    assert len(open_orders) == 1
    assert Decimal(open_orders[0]["outstanding"]) == Decimal("750.00")


def test_the_books_still_balance_after_settling_both_sides(client, db):
    headers = _admin(db)
    record = make_client_record(db)
    project = make_project(db, client=record, contract_value=Decimal("100000"))
    supplier = make_supplier(db)
    po = _received_po(client, db, headers, project, supplier, "700.00")
    valuation = _issued_valuation(client, headers, project, "5000")

    client.post(
        "/api/v1/accounting/payments",
        json={
            "supplier_id": str(supplier.id),
            "amount": "700.00",
            "allocations": [{"purchase_order_id": po["id"], "amount": "700.00"}],
        },
        headers=headers,
    )
    client.post(f"/api/v1/valuations/{valuation['id']}/pay", json={}, headers=headers)

    trial = client.get("/api/v1/accounting/trial-balance", headers=headers).json()
    assert trial["balanced"] is True


def test_ageing_is_not_general_reading(client, db):
    for role in (UserRole.site_manager, UserRole.procurement_officer, UserRole.viewer):
        headers = auth_headers(make_user(db, role=role))
        assert client.get("/api/v1/accounting/receivables", headers=headers).status_code == 403
        assert client.get("/api/v1/accounting/payables", headers=headers).status_code == 403
