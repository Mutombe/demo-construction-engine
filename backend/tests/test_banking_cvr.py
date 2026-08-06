"""Bank reconciliation, and whether a job is making money."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.common.enums import UserRole
from app.core.exceptions import ConflictError, ValidationFailedError
from app.modules.accounting import banking, service as ledger
from app.modules.accounting.models import BankAccount
from tests.factories import (
    auth_headers,
    make_boq_item,
    make_boq_section,
    make_client_record,
    make_project,
    make_supplier,
    make_user,
)

TODAY = date(2026, 9, 30)


def _admin(db):
    return auth_headers(make_user(db, role=UserRole.admin))


def _bank(db, opening="0.00"):
    ledger.ensure_chart(db)
    account = BankAccount(
        name="Main Current Account",
        bank_name="Demo Bank",
        currency="USD",
        gl_account_id=ledger.account_by_code(db, ledger.BANK).id,
        opening_balance=Decimal(opening),
    )
    db.add(account)
    db.flush()
    return account


def _cash_journal(db, amount, when=TODAY, incoming=True, memo="Movement"):
    lines = (
        [
            {"account_code": ledger.BANK, "debit": amount},
            {"account_code": ledger.CONTRACT_REVENUE, "credit": amount},
        ]
        if incoming
        else [
            {"account_code": ledger.ACCRUED_COSTS, "debit": amount},
            {"account_code": ledger.BANK, "credit": amount},
        ]
    )
    journal = ledger.create_journal(db, journal_date=when, memo=memo, lines=lines)
    return ledger.post(db, journal.id)


class _Line:
    def __init__(self, when, description, amount, reference=None):
        self.transaction_date = when
        self.description = description
        self.amount = Decimal(amount)
        self.reference = reference


# --- Bank reconciliation -----------------------------------------------------


def test_the_books_and_the_statement_agree_when_everything_is_matched(client, db):
    account = _bank(db)
    journal = _cash_journal(db, "5000", memo="Client receipt")
    banking.import_lines(db, account.id, [_Line(TODAY, "Client receipt", "5000")])

    line = banking.unmatched_statement_lines(db, account.id)[0]
    banking.match(db, line.id, journal.id)

    result = banking.summary(db, account.id, TODAY, Decimal("5000"))
    assert result["reconciled"] is True
    assert result["difference"] == 0
    assert result["deposits_in_transit"] == 0


def test_money_in_the_books_but_not_on_the_statement_is_in_transit(client, db):
    """The legitimate reason the two disagree, and the report has to name it
    rather than call it a difference."""
    account = _bank(db)
    _cash_journal(db, "800", memo="Banked late on Friday")

    result = banking.summary(db, account.id, TODAY, Decimal("0"))
    assert result["deposits_in_transit"] == Decimal("800.00")
    assert result["book_balance"] == Decimal("800.00")
    # Statement + in transit explains the books exactly
    assert result["reconciled"] is True


def test_a_payment_not_yet_cleared_shows_as_unpresented(client, db):
    account = _bank(db, opening="2000")
    _cash_journal(db, "300", incoming=False, memo="Cheque to supplier")

    result = banking.summary(db, account.id, TODAY, Decimal("2000"))
    assert result["unpresented_payments"] == Decimal("300.00")
    assert result["book_balance"] == Decimal("1700.00")
    assert result["reconciled"] is True


def test_an_unexplained_difference_is_reported_not_hidden(client, db):
    """A reconciliation that balances by adjusting the books to match the bank
    is not a reconciliation."""
    account = _bank(db)
    banking.import_lines(db, account.id, [_Line(TODAY, "Bank charges", "-45")])

    result = banking.summary(db, account.id, TODAY, Decimal("-45"))
    assert result["reconciled"] is False
    assert result["difference"] == Decimal("45.00")


def test_matching_to_a_journal_that_never_touched_the_bank_is_refused(client, db):
    """It would explain nothing and quietly hide the real difference."""
    account = _bank(db)
    elsewhere = ledger.create_journal(
        db,
        journal_date=TODAY,
        memo="Nothing to do with the bank",
        lines=[
            {"account_code": "5900", "debit": "100"},
            {"account_code": ledger.ACCRUED_COSTS, "credit": "100"},
        ],
    )
    ledger.post(db, elsewhere.id)
    banking.import_lines(db, account.id, [_Line(TODAY, "Mystery", "100")])
    line = banking.unmatched_statement_lines(db, account.id)[0]

    with pytest.raises(ValidationFailedError, match="does not move"):
        banking.match(db, line.id, elsewhere.id)


def test_a_line_cannot_be_matched_twice(client, db):
    account = _bank(db)
    journal = _cash_journal(db, "120")
    banking.import_lines(db, account.id, [_Line(TODAY, "Receipt", "120")])
    line = banking.unmatched_statement_lines(db, account.id)[0]
    banking.match(db, line.id, journal.id)

    with pytest.raises(ConflictError, match="already matched"):
        banking.match(db, line.id, journal.id)


def test_suggestions_pair_a_line_with_the_journal_that_probably_caused_it(client, db):
    account = _bank(db)
    journal = _cash_journal(db, "2500", when=TODAY - timedelta(days=2))
    banking.import_lines(db, account.id, [_Line(TODAY, "Deposit", "2500")])

    suggestions = banking.suggest_matches(db, account.id)
    assert len(suggestions) == 1
    assert suggestions[0]["journal_id"] == journal.id
    assert suggestions[0]["days_apart"] == 2


def test_a_suggestion_is_not_offered_across_a_long_gap(client, db):
    account = _bank(db)
    _cash_journal(db, "700", when=TODAY - timedelta(days=45))
    banking.import_lines(db, account.id, [_Line(TODAY, "Unrelated", "700")])

    assert banking.suggest_matches(db, account.id) == []


def test_reimporting_the_same_statement_does_not_duplicate_it(client, db):
    account = _bank(db)
    rows = [_Line(TODAY, "Receipt", "400", reference="TX1")]
    assert banking.import_lines(db, account.id, rows) == 1
    assert banking.import_lines(db, account.id, rows) == 0


def test_a_reconciliation_cannot_be_signed_off_while_it_is_still_out(client, db):
    """The whole value is that finishing it means something."""
    account = _bank(db)
    banking.import_lines(db, account.id, [_Line(TODAY, "Charges", "-30")])

    with pytest.raises(ConflictError, match="still unexplained"):
        banking.complete(db, account.id, TODAY, Decimal("-30"))


def test_a_balanced_reconciliation_is_recorded(client, db):
    account = _bank(db)
    journal = _cash_journal(db, "900")
    banking.import_lines(db, account.id, [_Line(TODAY, "Receipt", "900")])
    line = banking.unmatched_statement_lines(db, account.id)[0]
    banking.match(db, line.id, journal.id)

    record = banking.complete(db, account.id, TODAY, Decimal("900"))
    assert record.is_complete is True
    assert record.book_balance == Decimal("900.00")

    with pytest.raises(ConflictError, match="already been reconciled"):
        banking.complete(db, account.id, TODAY, Decimal("900"))


# --- Cost value reconciliation -----------------------------------------------


def _job(db, client_api, headers, budget="100000", contract="120000"):
    record = make_client_record(db)
    project = make_project(db, client=record, contract_value=Decimal(contract))
    section = make_boq_section(db, project)
    make_boq_item(db, section, quantity=Decimal("1"), rate=Decimal(budget))
    return project


def test_margin_is_what_was_certified_less_what_it_cost(client, db):
    headers = _admin(db)
    project = _job(db, client, headers)
    client.post(
        f"/api/v1/projects/{project.id}/cost-entries",
        json={"entry_date": str(TODAY), "amount": "40000", "description": "Spend",
              "source": "manual"},
        headers=headers,
    )
    valuation = client.post(
        f"/api/v1/projects/{project.id}/valuations",
        json={"period_end": str(TODAY), "gross_valuation": "60000"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/valuations/{valuation['id']}/issue", json={}, headers=headers)

    body = client.get(f"/api/v1/accounting/cvr/{project.id}", headers=headers).json()
    assert Decimal(body["certified_to_date"]) == Decimal("60000.00")
    assert Decimal(body["cost_to_date"]) == Decimal("40000.00")
    assert Decimal(body["margin_to_date"]) == Decimal("20000.00")


def test_billing_ahead_of_the_work_is_flagged(client, db):
    """The trap the report exists to catch: cash is fine, the margin is
    imaginary, and it reverses as the certificate catches up."""
    headers = _admin(db)
    project = _job(db, client, headers, budget="100000", contract="100000")
    client.post(
        f"/api/v1/projects/{project.id}/cost-entries",
        json={"entry_date": str(TODAY), "amount": "10000", "description": "Early spend",
              "source": "manual"},
        headers=headers,
    )
    valuation = client.post(
        f"/api/v1/projects/{project.id}/valuations",
        json={"period_end": str(TODAY), "gross_valuation": "50000"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/valuations/{valuation['id']}/issue", json={}, headers=headers)

    body = client.get(f"/api/v1/accounting/cvr/{project.id}", headers=headers).json()
    # A tenth of the budget spent implies a tenth earned, but half is billed
    assert body["billing_status"] == "over_billed"
    assert Decimal(body["earned_value"]) == Decimal("10000.00")
    assert Decimal(body["billing_position"]) == Decimal("40000.00")


def test_work_done_and_not_yet_billed_is_flagged_the_other_way(client, db):
    headers = _admin(db)
    project = _job(db, client, headers, budget="100000", contract="100000")
    client.post(
        f"/api/v1/projects/{project.id}/cost-entries",
        json={"entry_date": str(TODAY), "amount": "50000", "description": "Spend",
              "source": "manual"},
        headers=headers,
    )
    valuation = client.post(
        f"/api/v1/projects/{project.id}/valuations",
        json={"period_end": str(TODAY), "gross_valuation": "20000"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/valuations/{valuation['id']}/issue", json={}, headers=headers)

    body = client.get(f"/api/v1/accounting/cvr/{project.id}", headers=headers).json()
    assert body["billing_status"] == "under_billed"


def test_committed_cost_counts_toward_what_the_job_is_heading_for(client, db):
    headers = _admin(db)
    project = _job(db, client, headers)
    supplier = make_supplier(db)
    po = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "items": [
                {"description": "Steel", "unit": "t", "quantity": "2", "unit_price": "3000"}
            ],
        },
        headers=headers,
    ).json()
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)

    body = client.get(f"/api/v1/accounting/cvr/{project.id}", headers=headers).json()
    assert Decimal(body["committed"]) == Decimal("6000.00")
    assert Decimal(body["known_cost"]) == Decimal("6000.00")


def test_a_percentage_with_nothing_to_divide_by_is_not_zero(client, db):
    """0% and "no basis to say" are different answers."""
    headers = _admin(db)
    project = make_project(db, contract_value=Decimal("0"))
    body = client.get(f"/api/v1/accounting/cvr/{project.id}", headers=headers).json()
    assert body["margin_pct"] is None


def test_the_portfolio_leads_with_the_worst_job(client, db):
    headers = _admin(db)
    healthy = _job(db, client, headers, budget="10000", contract="20000")
    sick = _job(db, client, headers, budget="10000", contract="20000")
    for project, spend, certified in ((healthy, "2000", "10000"), (sick, "9000", "10000")):
        client.post(
            f"/api/v1/projects/{project.id}/cost-entries",
            json={"entry_date": str(TODAY), "amount": spend, "description": "Spend",
                  "source": "manual"},
            headers=headers,
        )
        valuation = client.post(
            f"/api/v1/projects/{project.id}/valuations",
            json={"period_end": str(TODAY), "gross_valuation": certified},
            headers=headers,
        ).json()
        client.post(f"/api/v1/valuations/{valuation['id']}/issue", json={}, headers=headers)

    rows = client.get("/api/v1/accounting/cvr", headers=headers).json()
    codes = [r["project_code"] for r in rows]
    assert codes.index(sick.code) < codes.index(healthy.code)


def test_the_books_are_not_general_reading(client, db):
    for role in (UserRole.site_manager, UserRole.viewer):
        headers = auth_headers(make_user(db, role=role))
        assert client.get("/api/v1/accounting/cvr", headers=headers).status_code == 403
        assert client.get(
            "/api/v1/accounting/bank-accounts", headers=headers
        ).status_code == 403
