"""The chart of accounts, and the rules that keep it a chart."""

from datetime import date
from decimal import Decimal

import pytest

from app.common.enums import AccountType, UserRole
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.accounting import hierarchy, service
from app.modules.accounting.models import Account, ExchangeRate, FiscalPeriod
from tests.factories import auth_headers, make_user


def _new(code, kind, **kw):
    return Account(code=code, name=kw.pop("name", "Test"), account_type=kind, **kw)


def test_the_code_decides_where_an_account_belongs(client, db):
    """A glance at 2100 should tell you it is a current liability without
    opening anything."""
    service.ensure_chart(db)
    account = _new("2300", AccountType.liability, name="VAT Payable")
    service.classify(db, account)
    assert account.account_subclass == "current_liabilities"
    assert account.account_class == "liability"
    assert account.report_type == "balance_sheet"
    assert account.normal_balance == "credit"


def test_a_class_cannot_borrow_another_subclasses_range(client, db):
    service.ensure_chart(db)
    with pytest.raises(ValidationFailedError, match="cannot sit in Current Assets"):
        service.classify(db, _new("1500", AccountType.liability))
    with pytest.raises(ValidationFailedError, match="cannot sit in Cost of Works"):
        service.classify(db, _new("5500", AccountType.revenue))


def test_a_code_outside_every_range_is_refused(client, db):
    service.ensure_chart(db)
    with pytest.raises(ValidationFailedError, match="outside every range"):
        service.classify(db, _new("99999", AccountType.asset))


def test_an_explicit_subclass_that_disagrees_with_the_code_is_refused(client, db):
    service.ensure_chart(db)
    account = _new("2500", AccountType.liability, account_subclass="current_assets")
    with pytest.raises(ValidationFailedError, match="owns 1000 to 1999"):
        service.classify(db, account)


def test_sub_accounts_hang_off_a_parent_in_the_same_part_of_the_chart(client, db):
    service.ensure_chart(db)
    materials = service.account_by_code(db, "5000")
    cement = _new("5010", AccountType.expense, name="Cement", parent_id=materials.id)
    service.classify(db, cement)
    assert cement.account_subclass == materials.account_subclass

    stray = _new("2400", AccountType.liability, name="Wrong", parent_id=materials.id)
    with pytest.raises(ValidationFailedError, match="different part of the chart"):
        service.classify(db, stray)


def test_a_sub_account_holds_the_same_currency_as_its_parent(client, db):
    service.ensure_chart(db)
    materials = service.account_by_code(db, "5000")
    other = _new("5020", AccountType.expense, name="Steel ZWL",
                 parent_id=materials.id, currency="ZWL")
    with pytest.raises(ValidationFailedError, match="same currency"):
        service.classify(db, other)


def test_the_seeded_chart_classifies_itself(client, db):
    service.ensure_chart(db)
    from sqlalchemy import select

    for account in db.scalars(select(Account)):
        assert account.account_subclass == hierarchy.subclass_for_code(account.code)
        assert account.report_type in hierarchy.REPORTS


# --- Posting rules -----------------------------------------------------------


def _post(db, lines, when=None, user=None):
    journal = service.create_journal(
        db,
        journal_date=when or date.today(),
        memo="Test",
        lines=lines,
    )
    return service.post(db, journal.id, user)


def test_a_heading_cannot_be_posted_to(client, db):
    """Posting to a grouping account is how a chart quietly stops adding up."""
    service.ensure_chart(db)
    heading = service.account_by_code(db, "5000")
    heading.is_postable = False
    db.flush()

    with pytest.raises(ValidationFailedError, match="is a heading"):
        _post(db, [
            {"account_code": "5000", "debit": "10"},
            {"account_code": "2100", "credit": "10"},
        ])


def test_a_journal_moves_one_currency(client, db):
    """Two currencies in one journal cannot balance in either of them."""
    service.ensure_chart(db)
    zwl = _new("2400", AccountType.liability, name="ZWL Creditors", currency="ZWL")
    service.classify(db, zwl)
    db.add(zwl)
    db.flush()

    with pytest.raises(ValidationFailedError, match="moves one currency"):
        _post(db, [
            {"account_code": "5900", "debit": "10"},
            {"account_id": zwl.id, "credit": "10"},
        ])


def test_a_closed_month_does_not_move(client, db):
    """Reporting a number and then letting it change afterwards is worse than
    not reporting it."""
    service.ensure_chart(db)
    when = date(2026, 4, 15)
    db.add(
        FiscalPeriod(
            year=2026, month=4, starts_on=date(2026, 4, 1),
            ends_on=date(2026, 4, 30), is_closed=True,
        )
    )
    db.flush()

    with pytest.raises(ConflictError, match="closed"):
        _post(db, [
            {"account_code": "5900", "debit": "50"},
            {"account_code": "2100", "credit": "50"},
        ], when=when)

    # An open month is unaffected
    assert _post(db, [
        {"account_code": "5900", "debit": "50"},
        {"account_code": "2100", "credit": "50"},
    ], when=date(2026, 5, 15))


# --- Currency ----------------------------------------------------------------


def test_a_rate_stands_until_it_is_replaced(client, db):
    """A journal posted in March keeps translating at March's rate, whatever
    today's is."""
    db.add_all([
        ExchangeRate(from_currency="USD", to_currency="ZWL", rate="30.5",
                     effective_date=date(2026, 3, 1)),
        ExchangeRate(from_currency="USD", to_currency="ZWL", rate="41.25",
                     effective_date=date(2026, 6, 1)),
    ])
    db.flush()

    assert service.rate_on(db, "USD", "ZWL", date(2026, 3, 15)) == Decimal("30.5")
    assert service.rate_on(db, "USD", "ZWL", date(2026, 5, 31)) == Decimal("30.5")
    assert service.rate_on(db, "USD", "ZWL", date(2026, 7, 1)) == Decimal("41.25")


def test_the_same_currency_is_always_one(client, db):
    assert service.rate_on(db, "USD", "USD", date.today()) == 1


def test_a_missing_rate_raises_rather_than_assuming_parity(client, db):
    """A wrong number here is worse than no number."""
    with pytest.raises(NotFoundError, match="No USD/ZWL rate"):
        service.rate_on(db, "USD", "ZWL", date(2020, 1, 1))
