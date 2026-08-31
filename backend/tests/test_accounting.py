"""Double-entry posting, and the automatic journals behind the operations."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.common.enums import UserRole
from app.modules.accounting import service as accounting
from app.modules.accounting.models import Account, GeneralLedger, Journal
from tests.factories import (
    auth_headers,
    make_boq_item,
    make_boq_section,
    make_project,
    make_supplier,
    make_user,
)


def _admin(db):
    return auth_headers(make_user(db, role=UserRole.admin))


def _account(db, code):
    return db.scalar(select(Account).where(Account.code == code))


def _balance(client, headers, code):
    rows = client.get("/api/v1/accounting/accounts", headers=headers).json()
    return Decimal(next(a["balance"] for a in rows if a["code"] == code))


# --- The engine --------------------------------------------------------------


def test_the_chart_is_created_once_and_only_once(client, db):
    headers = _admin(db)
    first = client.get("/api/v1/accounting/accounts", headers=headers).json()
    second = client.get("/api/v1/accounting/accounts", headers=headers).json()
    assert len(first) == len(second) == len(accounting.DEFAULT_CHART)
    assert all(a["is_system"] for a in first)


def test_normal_balance_is_derived_not_configured(client, db):
    """An asset that credits normally is a bug, not a setting."""
    headers = _admin(db)
    rows = client.get("/api/v1/accounting/accounts", headers=headers).json()
    by_code = {a["code"]: a for a in rows}
    assert by_code["1000"]["normal_balance"] == "debit"
    assert by_code["2000"]["normal_balance"] == "credit"
    assert by_code["4000"]["normal_balance"] == "credit"
    assert by_code["5000"]["normal_balance"] == "debit"


def test_an_unbalanced_journal_is_refused_at_write_time(client, db):
    headers = _admin(db)
    accounting.ensure_chart(db)
    res = client.post(
        "/api/v1/accounting/journals",
        json={
            "journal_date": str(date.today()),
            "memo": "Wrong",
            "lines": [
                {"account_id": str(_account(db, "1000").id), "debit": "100"},
                {"account_id": str(_account(db, "4000").id), "credit": "90"},
            ],
        },
        headers=headers,
    )
    assert res.status_code == 422
    assert "does not balance" in res.json()["error"]["detail"]


def test_a_line_cannot_be_both_sides_or_neither(client, db):
    headers = _admin(db)
    accounting.ensure_chart(db)
    for line in ({"debit": "10", "credit": "10"}, {"debit": "0", "credit": "0"}):
        res = client.post(
            "/api/v1/accounting/journals",
            json={
                "journal_date": str(date.today()),
                "memo": "Bad line",
                "lines": [
                    {"account_id": str(_account(db, "1000").id), **line},
                    {"account_id": str(_account(db, "4000").id), "credit": "10"},
                ],
            },
            headers=headers,
        )
        assert res.status_code == 422


def test_posting_moves_balances_in_each_accounts_own_direction(client, db):
    headers = _admin(db)
    accounting.ensure_chart(db)
    created = client.post(
        "/api/v1/accounting/journals",
        json={
            "journal_date": str(date.today()),
            "memo": "Owner puts money in",
            "lines": [
                {"account_id": str(_account(db, "1000").id), "debit": "5000"},
                {"account_id": str(_account(db, "3000").id), "credit": "5000"},
            ],
        },
        headers=headers,
    ).json()
    assert created["status"] == "draft"
    assert _balance(client, headers, "1000") == 0  # nothing until it is posted

    posted = client.post(
        f"/api/v1/accounting/journals/{created['id']}/post", headers=headers
    ).json()
    assert posted["status"] == "posted"
    # The asset rose on a debit and the equity rose on a credit: both positive.
    assert _balance(client, headers, "1000") == Decimal("5000.00")
    assert _balance(client, headers, "3000") == Decimal("5000.00")


def test_a_journal_cannot_be_posted_twice(client, db):
    headers = _admin(db)
    accounting.ensure_chart(db)
    created = client.post(
        "/api/v1/accounting/journals",
        json={
            "journal_date": str(date.today()),
            "memo": "Once",
            "lines": [
                {"account_id": str(_account(db, "1000").id), "debit": "10"},
                {"account_id": str(_account(db, "3000").id), "credit": "10"},
            ],
        },
        headers=headers,
    ).json()
    assert client.post(
        f"/api/v1/accounting/journals/{created['id']}/post", headers=headers
    ).status_code == 200
    assert client.post(
        f"/api/v1/accounting/journals/{created['id']}/post", headers=headers
    ).status_code == 409


def test_a_mistake_is_reversed_never_deleted(client, db):
    """A ledger you can edit is not evidence of anything."""
    headers = _admin(db)
    accounting.ensure_chart(db)
    created = client.post(
        "/api/v1/accounting/journals",
        json={
            "journal_date": str(date.today()),
            "memo": "Typo",
            "lines": [
                {"account_id": str(_account(db, "1000").id), "debit": "250"},
                {"account_id": str(_account(db, "3000").id), "credit": "250"},
            ],
        },
        headers=headers,
    ).json()
    client.post(f"/api/v1/accounting/journals/{created['id']}/post", headers=headers)

    reversal = client.post(
        f"/api/v1/accounting/journals/{created['id']}/reverse", headers=headers
    ).json()
    assert reversal["reversal_of"] == created["id"]
    assert _balance(client, headers, "1000") == 0

    # The original is still there, marked, and both sets of rows survive
    original = client.get(
        f"/api/v1/accounting/journals/{created['id']}", headers=headers
    ).json()
    assert original["status"] == "reversed"
    assert db.scalar(select(GeneralLedger).where(GeneralLedger.journal_id == created["id"]))

    # And it cannot be reversed a second time
    assert client.post(
        f"/api/v1/accounting/journals/{created['id']}/reverse", headers=headers
    ).status_code == 409


def test_the_ledger_carries_the_running_balance(client, db):
    headers = _admin(db)
    accounting.ensure_chart(db)
    bank = _account(db, "1000")
    for amount in ("100", "40"):
        created = client.post(
            "/api/v1/accounting/journals",
            json={
                "journal_date": str(date.today()),
                "memo": f"Deposit {amount}",
                "lines": [
                    {"account_id": str(bank.id), "debit": amount},
                    {"account_id": str(_account(db, "3000").id), "credit": amount},
                ],
            },
            headers=headers,
        ).json()
        client.post(f"/api/v1/accounting/journals/{created['id']}/post", headers=headers)

    rows = client.get(
        f"/api/v1/accounting/accounts/{bank.id}/ledger", headers=headers
    ).json()["items"]
    assert [Decimal(r["balance_after"]) for r in rows] == [Decimal("100.00"), Decimal("140.00")]


# --- Automatic posting -------------------------------------------------------


def test_a_project_cost_posts_itself(client, db):
    """One cost, one journal: debit the works account, credit where it came from.

    The works account follows the BOQ item's category, because a cost entry
    carries no category of its own.
    """
    headers = _admin(db)
    project = make_project(db)
    item = make_boq_item(db, make_boq_section(db, project))
    client.post(
        f"/api/v1/projects/{project.id}/cost-entries",
        json={
            "boq_item_id": str(item.id),
            "entry_date": str(date.today()),
            "amount": "1500.00",
            "description": "Sand delivery",
            "source": "manual",
        },
        headers=headers,
    )

    assert _balance(client, headers, "5000") == Decimal("1500.00")  # materials
    assert _balance(client, headers, "2100") == Decimal("1500.00")  # accrued costs


def test_a_cost_with_no_boq_line_lands_in_other_rather_than_a_guess(client, db):
    headers = _admin(db)
    project = make_project(db)
    client.post(
        f"/api/v1/projects/{project.id}/cost-entries",
        json={
            "entry_date": str(date.today()),
            "amount": "200.00",
            "description": "Unbooked",
            "source": "manual",
        },
        headers=headers,
    )
    assert _balance(client, headers, "5900") == Decimal("200.00")


def test_the_credit_side_follows_where_the_cost_came_from(client, db):
    headers = _admin(db)
    project = make_project(db)
    site = auth_headers(make_user(db, role=UserRole.site_manager))
    claim = client.post(
        f"/api/v1/projects/{project.id}/expenses",
        json={
            "category": "fuel",
            "expense_date": str(date.today()),
            "amount": "80.00",
            "description": "Diesel",
        },
        headers=site,
    ).json()
    client.post(f"/api/v1/expenses/{claim['id']}/approve", headers=headers)

    # An approved expense is a cost that has been incurred but not invoiced
    assert _balance(client, headers, "2100") == Decimal("80.00")


def test_receiving_a_purchase_order_debits_works_and_credits_the_supplier(client, db):
    headers = _admin(db)
    project = make_project(db)
    supplier = make_supplier(db, name="Blue Circle")
    po = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "items": [
                {"description": "Cement", "unit": "bag", "quantity": "10", "unit_price": "12.00"}
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

    assert _balance(client, headers, "2000") == Decimal("120.00")  # accounts payable
    assert _balance(client, headers, "5900") + _balance(client, headers, "5000") == Decimal(
        "120.00"
    )


def test_certifying_work_recognises_revenue_and_holds_retention(client, db):
    headers = _admin(db)
    project = make_project(db, contract_value=Decimal("100000"), retention_pct=Decimal("5"))
    valuation = client.post(
        f"/api/v1/projects/{project.id}/valuations",
        json={"period_end": str(date.today()), "gross_valuation": "10000"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/valuations/{valuation['id']}/issue", json={}, headers=headers)

    assert _balance(client, headers, "4000") == Decimal("10000.00")  # revenue
    assert _balance(client, headers, "1200") == Decimal("500.00")  # retention held
    assert _balance(client, headers, "1100") == Decimal("9500.00")  # receivable


def test_retention_is_not_recognised_twice_across_certificates(client, db):
    """Retention is cumulative on this model, so posting the cumulative figure
    every month would inflate both revenue and the retention asset."""
    headers = _admin(db)
    project = make_project(db, contract_value=Decimal("100000"), retention_pct=Decimal("5"))
    for gross in ("10000", "25000"):
        valuation = client.post(
            f"/api/v1/projects/{project.id}/valuations",
            json={"period_end": str(date.today()), "gross_valuation": gross},
            headers=headers,
        ).json()
        client.post(f"/api/v1/valuations/{valuation['id']}/issue", json={}, headers=headers)

    # Cumulative gross is 25000, of which 5% is held
    assert _balance(client, headers, "4000") == Decimal("25000.00")
    assert _balance(client, headers, "1200") == Decimal("1250.00")
    assert _balance(client, headers, "1100") == Decimal("23750.00")


def test_stock_arriving_is_an_asset_swap_not_a_cost(client, db):
    headers = _admin(db)
    project = make_project(db)
    supplier = make_supplier(db)
    po = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "items": [
                {"description": "Rebar", "unit": "t", "quantity": "2", "unit_price": "500.00"}
            ],
        },
        headers=headers,
    ).json()
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)
    detail = client.get(f"/api/v1/purchase-orders/{po['id']}", headers=headers).json()
    received = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        json={
            "destination": "store",
            "store_lines": [
                {
                    "po_item_id": detail["items"][0]["id"],
                    "new_item": {
                        "code": "REBAR-T",
                        "name": "Rebar",
                        "unit": "t",
                        "reorder_level": "0",
                    },
                }
            ],
        },
        headers=headers,
    )
    assert received.status_code == 200, received.text

    assert _balance(client, headers, "1300") == Decimal("1000.00")  # inventory
    assert _balance(client, headers, "2000") == Decimal("1000.00")  # payable
    # Nothing has been charged to a job yet
    assert _balance(client, headers, "5000") == 0


# --- Statements --------------------------------------------------------------


def test_the_trial_balance_agrees(client, db):
    headers = _admin(db)
    project = make_project(db, contract_value=Decimal("50000"), retention_pct=Decimal("5"))
    client.post(
        f"/api/v1/projects/{project.id}/cost-entries",
        json={
            "entry_date": str(date.today()),
            "amount": "700.00",
            "description": "Gang",
            "source": "manual",
        },
        headers=headers,
    )
    valuation = client.post(
        f"/api/v1/projects/{project.id}/valuations",
        json={"period_end": str(date.today()), "gross_valuation": "4000"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/valuations/{valuation['id']}/issue", json={}, headers=headers)

    body = client.get("/api/v1/accounting/trial-balance", headers=headers).json()
    assert body["balanced"] is True
    assert Decimal(body["total_debit"]) == Decimal(body["total_credit"])


def test_the_income_statement_reports_the_result(client, db):
    headers = _admin(db)
    project = make_project(db, contract_value=Decimal("50000"))
    client.post(
        f"/api/v1/projects/{project.id}/cost-entries",
        json={
            "entry_date": str(date.today()),
            "amount": "1000.00",
            "description": "Blocks",
            "source": "manual",
        },
        headers=headers,
    )
    valuation = client.post(
        f"/api/v1/projects/{project.id}/valuations",
        json={"period_end": str(date.today()), "gross_valuation": "3000"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/valuations/{valuation['id']}/issue", json={}, headers=headers)

    body = client.get("/api/v1/accounting/income-statement", headers=headers).json()
    assert Decimal(body["revenue_total"]) == Decimal("3000.00")
    assert Decimal(body["expense_total"]) == Decimal("1000.00")
    assert Decimal(body["net_result"]) == Decimal("2000.00")


def test_the_balance_sheet_balances(client, db):
    headers = _admin(db)
    project = make_project(db, contract_value=Decimal("50000"), retention_pct=Decimal("10"))
    client.post(
        f"/api/v1/projects/{project.id}/cost-entries",
        json={
            "entry_date": str(date.today()),
            "amount": "450.00",
            "description": "Excavator",
            "source": "manual",
        },
        headers=headers,
    )
    valuation = client.post(
        f"/api/v1/projects/{project.id}/valuations",
        json={"period_end": str(date.today()), "gross_valuation": "8000"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/valuations/{valuation['id']}/issue", json={}, headers=headers)

    body = client.get("/api/v1/accounting/balance-sheet", headers=headers).json()
    assert body["balanced"] is True
    assert Decimal(body["asset_total"]) == Decimal(body["liability_total"]) + Decimal(
        body["equity_total"]
    ) + Decimal(body["result_for_period"])


def test_the_unposted_control_is_empty_when_posting_works(client, db):
    headers = _admin(db)
    project = make_project(db)
    client.post(
        f"/api/v1/projects/{project.id}/cost-entries",
        json={
            "entry_date": str(date.today()),
            "amount": "60.00",
            "description": "Nails",
            "source": "manual",
        },
        headers=headers,
    )
    assert client.get("/api/v1/accounting/unposted", headers=headers).json() == []


def test_a_gap_in_the_ledger_is_visible_and_fixable(client, db):
    """The automatic posters never raise into the operation that triggered
    them, so this control is what stops a failure being invisible."""
    headers = _admin(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    make_boq_item(db, section)
    client.post(
        f"/api/v1/projects/{project.id}/cost-entries",
        json={
            "entry_date": str(date.today()),
            "amount": "90.00",
            "description": "Orphan",
            "source": "manual",
        },
        headers=headers,
    )
    # Simulate the journal having failed to write
    journal = db.scalar(select(Journal).where(Journal.source == "cost_entry"))
    db.delete(journal)
    db.flush()

    unposted = client.get("/api/v1/accounting/unposted", headers=headers).json()
    assert len(unposted) == 1
    assert Decimal(unposted[0]["amount"]) == Decimal("90.00")

    assert client.post("/api/v1/accounting/unposted/post", headers=headers).json()["posted"] == 1
    assert client.get("/api/v1/accounting/unposted", headers=headers).json() == []


def test_the_books_are_not_general_reading(client, db):
    for role in (UserRole.site_manager, UserRole.procurement_officer, UserRole.viewer):
        headers = auth_headers(make_user(db, role=role))
        assert client.get("/api/v1/accounting/trial-balance", headers=headers).status_code == 403
        assert client.get("/api/v1/accounting/accounts", headers=headers).status_code == 403


def test_a_system_account_cannot_be_switched_off(client, db):
    headers = _admin(db)
    accounting.ensure_chart(db)
    payable = _account(db, "2000")
    res = client.patch(
        f"/api/v1/accounting/accounts/{payable.id}",
        json={"is_active": False},
        headers=headers,
    )
    assert res.status_code == 409
    assert "automatic posting" in res.json()["error"]["detail"]


def test_the_control_covers_revenue_as_well_as_cost(client, db):
    """A book carrying every cost and no revenue does not read as incomplete,
    it reads as a catastrophic loss."""
    headers = _admin(db)
    project = make_project(db, contract_value=Decimal("80000"), retention_pct=Decimal("5"))
    valuation = client.post(
        f"/api/v1/projects/{project.id}/valuations",
        json={"period_end": str(date.today()), "gross_valuation": "12000"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/valuations/{valuation['id']}/issue", json={}, headers=headers)

    # Simulate a certificate that never reached the ledger
    journal = db.scalar(select(Journal).where(Journal.source == "valuation"))
    db.delete(journal)
    db.flush()

    unposted = client.get("/api/v1/accounting/unposted", headers=headers).json()
    assert any("certified" in row["description"] for row in unposted)

    assert client.post("/api/v1/accounting/unposted/post", headers=headers).json()["posted"] == 1
    assert client.get("/api/v1/accounting/unposted", headers=headers).json() == []
    # Read the ledger rather than the cached account balance: deleting the
    # journal above cascaded its ledger rows but left the cache behind, which
    # is only reachable from a test — the product never deletes a journal.
    income = client.get("/api/v1/accounting/income-statement", headers=headers).json()
    assert Decimal(income["revenue_total"]) == Decimal("12000.00")


def test_stock_received_directly_reaches_the_books(client, db):
    """Production showed inventory going negative: stock was being issued out
    of an account nothing had ever been received into, because only purchase
    orders posted. Every receipt goes through goods-in, so that is where it
    belongs."""
    headers = _admin(db)
    item = client.post(
        "/api/v1/stock-items",
        json={"code": "SAND-1", "name": "Sand", "unit": "m3", "reorder_level": "0"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "20", "unit_cost": "15.00", "reference": "Opening stock"},
        headers=headers,
    )

    assert _balance(client, headers, "1300") == Decimal("300.00")
    assert _balance(client, headers, "2000") == Decimal("300.00")


def test_issuing_stock_never_drives_inventory_below_what_arrived(client, db):
    headers = _admin(db)
    project = make_project(db)
    item = client.post(
        "/api/v1/stock-items",
        json={"code": "CEM-1", "name": "Cement", "unit": "bag", "reorder_level": "0"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "100", "unit_cost": "12.00"},
        headers=headers,
    )
    client.post(
        f"/api/v1/stock-items/{item['id']}/issue",
        json={"project_id": str(project.id), "quantity": "30"},
        headers=headers,
    )

    # 1200 in, 360 issued to the job: the asset is what is left, not a deficit
    assert _balance(client, headers, "1300") == Decimal("840.00")
    assert _balance(client, headers, "5900") == Decimal("360.00")
