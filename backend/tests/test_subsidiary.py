"""Per-party ledgers, and the invariant that makes them trustworthy."""

from datetime import date
from decimal import Decimal

from app.common.enums import UserRole
from app.modules.accounting import service as ledger
from app.modules.accounting import subsidiary
from tests.factories import (
    auth_headers,
    make_client_record,
    make_project,
    make_supplier,
    make_user,
)


def _admin(db):
    return auth_headers(make_user(db, role=UserRole.admin))


def _received_po(client, headers, project, supplier, amount="1000.00"):
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
    client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        json={"destination": "project"},
        headers=headers,
    )
    return po


def _issued_valuation(client, headers, project, gross="10000"):
    valuation = client.post(
        f"/api/v1/projects/{project.id}/valuations",
        json={"period_end": str(date.today()), "gross_valuation": gross},
        headers=headers,
    ).json()
    client.post(f"/api/v1/valuations/{valuation['id']}/issue", json={}, headers=headers)
    return valuation


def _pockets(client, headers, entity_type=None):
    query = f"?entity_type={entity_type}" if entity_type else ""
    return client.get(f"/api/v1/accounting/subsidiary{query}", headers=headers).json()


def test_a_certificate_lands_in_that_clients_ledger(client, db):
    """The general ledger says the company is owed money. This says who owes
    which part of it."""
    headers = _admin(db)
    record = make_client_record(db, name="Riverside Group")
    project = make_project(db, client=record, contract_value=Decimal("100000"))
    _issued_valuation(client, headers, project, "10000")

    pockets = _pockets(client, headers, "client")
    assert len(pockets) == 1
    assert pockets[0]["name"] == "Riverside Group"
    assert Decimal(pockets[0]["balance"]) == Decimal("10000.00")
    assert pockets[0]["code"].startswith("CL/")


def test_a_delivery_lands_in_that_suppliers_ledger(client, db):
    headers = _admin(db)
    project = make_project(db)
    supplier = make_supplier(db, name="Blue Circle")
    _received_po(client, headers, project, supplier, "1200.00")

    pockets = _pockets(client, headers, "supplier")
    assert len(pockets) == 1
    assert pockets[0]["name"] == "Blue Circle"
    assert Decimal(pockets[0]["balance"]) == Decimal("1200.00")


def test_the_pockets_always_add_up_to_their_control(client, db):
    """The invariant the whole design rests on. A difference means posting has
    written one without the other."""
    headers = _admin(db)
    first = make_client_record(db, name="First Client")
    second = make_client_record(db, name="Second Client")
    supplier = make_supplier(db)
    project_a = make_project(db, client=first, contract_value=Decimal("100000"))
    project_b = make_project(db, client=second, contract_value=Decimal("100000"))

    _issued_valuation(client, headers, project_a, "8000")
    _issued_valuation(client, headers, project_b, "3000")
    _received_po(client, headers, project_a, supplier, "1500.00")

    rows = client.get("/api/v1/accounting/subsidiary-reconciliation", headers=headers).json()
    assert rows, "expected at least one control account to reconcile"
    for row in rows:
        assert row["in_agreement"] is True, row
        assert Decimal(row["difference"]) == 0


def test_paying_moves_the_party_ledger_too(client, db):
    headers = _admin(db)
    record = make_client_record(db)
    project = make_project(db, client=record, contract_value=Decimal("100000"))
    valuation = _issued_valuation(client, headers, project, "10000")

    pocket = _pockets(client, headers, "client")[0]
    assert Decimal(pocket["balance"]) == Decimal("10000.00")

    client.post(f"/api/v1/valuations/{valuation['id']}/pay", json={}, headers=headers)

    settled = _pockets(client, headers, "client")[0]
    assert Decimal(settled["balance"]) == 0
    rows = client.get("/api/v1/accounting/subsidiary-reconciliation", headers=headers).json()
    assert all(row["in_agreement"] for row in rows)


def test_paying_a_supplier_moves_their_ledger(client, db):
    headers = _admin(db)
    project = make_project(db)
    supplier = make_supplier(db, name="Blue Circle")
    po = _received_po(client, headers, project, supplier, "900.00")

    client.post(
        "/api/v1/accounting/payments",
        json={
            "supplier_id": str(supplier.id),
            "amount": "900.00",
            "allocations": [{"purchase_order_id": po["id"], "amount": "900.00"}],
        },
        headers=headers,
    )

    assert Decimal(_pockets(client, headers, "supplier")[0]["balance"]) == 0
    rows = client.get("/api/v1/accounting/subsidiary-reconciliation", headers=headers).json()
    assert all(row["in_agreement"] for row in rows)


def test_a_statement_reads_as_a_running_account(client, db):
    """What you would actually send someone: every movement, with the balance
    after each one."""
    headers = _admin(db)
    record = make_client_record(db, name="Statement Client")
    project = make_project(db, client=record, contract_value=Decimal("200000"))
    _issued_valuation(client, headers, project, "5000")
    _issued_valuation(client, headers, project, "12000")

    pocket = _pockets(client, headers, "client")[0]
    body = client.get(
        f"/api/v1/accounting/subsidiary/{pocket['id']}/statement", headers=headers
    ).json()

    assert body["name"] == "Statement Client"
    assert len(body["entries"]) == 2
    running = [Decimal(e["balance_after"]) for e in body["entries"]]
    assert running == sorted(running), "the balance should build, not jump about"
    assert Decimal(body["closing_balance"]) == running[-1]


def test_a_pocket_cannot_carry_a_line_posted_elsewhere(client, db):
    """Otherwise the pocket and its control drift apart silently, which is the
    exact failure this design exists to prevent."""
    import pytest

    from app.core.exceptions import ValidationFailedError

    headers = _admin(db)
    record = make_client_record(db)
    make_project(db, client=record)
    ledger.ensure_chart(db)
    pocket = subsidiary.pocket_for(db, "client", record.id)

    journal = ledger.create_journal(
        db,
        journal_date=date.today(),
        memo="Wrong account for this pocket",
        lines=[
            # Bank, not the receivable control this pocket sits under
            {"account_code": ledger.BANK, "debit": "100", "subsidiary_id": pocket.id},
            {"account_code": ledger.ACCRUED_COSTS, "credit": "100"},
        ],
    )
    with pytest.raises(ValidationFailedError, match="cannot carry a line"):
        ledger.post(db, journal.id)


def test_a_party_ledger_is_created_only_when_it_is_used(client, db):
    """A supplier who has never been transacted with is noise on every report
    that lists them."""
    headers = _admin(db)
    make_supplier(db, name="Never Used")
    assert _pockets(client, headers, "supplier") == []


def test_party_ledgers_are_not_general_reading(client, db):
    for role in (UserRole.site_manager, UserRole.viewer):
        headers = auth_headers(make_user(db, role=role))
        assert client.get("/api/v1/accounting/subsidiary", headers=headers).status_code == 403
