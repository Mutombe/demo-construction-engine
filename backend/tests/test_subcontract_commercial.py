"""Variations, back-charges and withholding tax.

Between what a subcontractor claims and what they are paid sit three
deductions, and each one is somebody's monthly argument. The tests here are
mostly about the arguments: that an instruction is not a value change until
somebody agrees it, that recovering remedial work is not income, and that tax
withheld is money still owed rather than money saved.
"""

from datetime import date, timedelta
from decimal import Decimal

from app.common.enums import UserRole
from tests.factories import auth_headers, make_project, make_supplier, make_user

TODAY = date.today()

MANDATORY = (
    "company_registration",
    "tax_clearance",
    "public_liability",
    "workmans_compensation",
)


def _pm(db):
    return auth_headers(make_user(db, role=UserRole.project_manager))


def _live_package(client, db, retention="10", withholding="0", stages=None):
    """An awarded package with one stage certified."""
    project = make_project(db)
    supplier = make_supplier(db)
    headers = _pm(db)

    for doc_type in MANDATORY:
        client.post(
            f"/api/v1/suppliers/{supplier.id}/compliance/documents",
            json={"doc_type": doc_type, "expires_on": str(TODAY + timedelta(days=365))},
            headers=headers,
        )
    client.post(
        f"/api/v1/suppliers/{supplier.id}/vendor-status",
        json={"vendor_status": "approved"},
        headers=headers,
    )

    res = client.post(
        f"/api/v1/projects/{project.id}/subcontracts",
        json={
            "supplier_id": str(supplier.id),
            "title": "Roofing package",
            "value": "100000",
            "retention_pct": retention,
            "withholding_pct": withholding,
            "milestones": stages
            or [
                {"name": "Purlins", "value": "40000"},
                {"name": "Sheeting", "value": "60000"},
            ],
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    contract = res.json()
    client.post(f"/api/v1/subcontracts/{contract['id']}/award", headers=headers)
    return headers, contract, project


def _certify_first(client, headers, contract):
    milestone = contract["milestones"][0]
    client.post(f"/api/v1/milestones/{milestone['id']}/submit", headers=headers)
    res = client.post(
        f"/api/v1/milestones/{milestone['id']}/certify", json={}, headers=headers
    )
    assert res.status_code == 200, res.text


# --- Variations --------------------------------------------------------------


def test_an_instruction_does_not_change_the_package_until_it_is_agreed(client, db):
    """A variation somebody shouted across a site is a claim. Treating it as a
    value change is how a package quietly grows by a third."""
    headers, contract, _ = _live_package(client, db)

    res = client.post(
        f"/api/v1/subcontracts/{contract['id']}/variations",
        json={"title": "Extra ridge flashing", "amount": "8000", "instructed_by": "R. Ncube"},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "pending"

    after = client.get(f"/api/v1/subcontracts/{contract['id']}", headers=headers).json()
    assert Decimal(after["value"]) == Decimal("100000.00")


def test_approving_a_variation_moves_the_contract_value(client, db):
    headers, contract, _ = _live_package(client, db)
    variation = client.post(
        f"/api/v1/subcontracts/{contract['id']}/variations",
        json={"title": "Extra ridge flashing", "amount": "8000"},
        headers=headers,
    ).json()

    client.post(f"/api/v1/variations/{variation['id']}/approve", headers=headers)

    after = client.get(f"/api/v1/subcontracts/{contract['id']}", headers=headers).json()
    assert Decimal(after["value"]) == Decimal("108000.00")


def test_an_omission_takes_value_off(client, db):
    headers, contract, _ = _live_package(client, db)
    variation = client.post(
        f"/api/v1/subcontracts/{contract['id']}/variations",
        json={"title": "Rooflights omitted", "amount": "-12000"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/variations/{variation['id']}/approve", headers=headers)

    after = client.get(f"/api/v1/subcontracts/{contract['id']}", headers=headers).json()
    assert Decimal(after["value"]) == Decimal("88000.00")


def test_an_omission_bigger_than_the_package_is_refused(client, db):
    headers, contract, _ = _live_package(client, db)
    variation = client.post(
        f"/api/v1/subcontracts/{contract['id']}/variations",
        json={"title": "Everything omitted twice over", "amount": "-250000"},
        headers=headers,
    ).json()

    res = client.post(f"/api/v1/variations/{variation['id']}/approve", headers=headers)
    assert res.status_code == 422
    assert "worth more than" in res.json()["error"]["detail"]


def test_the_same_variation_cannot_be_approved_twice(client, db):
    headers, contract, _ = _live_package(client, db)
    variation = client.post(
        f"/api/v1/subcontracts/{contract['id']}/variations",
        json={"title": "Extra flashing", "amount": "5000"},
        headers=headers,
    ).json()

    assert client.post(
        f"/api/v1/variations/{variation['id']}/approve", headers=headers
    ).status_code == 200
    again = client.post(f"/api/v1/variations/{variation['id']}/approve", headers=headers)
    assert again.status_code == 409

    after = client.get(f"/api/v1/subcontracts/{contract['id']}", headers=headers).json()
    assert Decimal(after["value"]) == Decimal("105000.00")


def test_an_approved_variation_is_omitted_rather_than_rejected(client, db):
    """Rejecting one that is already in the value would erase the record of
    having agreed it."""
    headers, contract, _ = _live_package(client, db)
    variation = client.post(
        f"/api/v1/subcontracts/{contract['id']}/variations",
        json={"title": "Extra flashing", "amount": "5000"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/variations/{variation['id']}/approve", headers=headers)

    res = client.post(f"/api/v1/variations/{variation['id']}/reject", headers=headers)
    assert res.status_code == 409
    assert "negative variation" in res.json()["error"]["detail"]


# --- Back-charges ------------------------------------------------------------


def test_a_back_charge_reduces_what_they_are_owed(client, db):
    headers, contract, _ = _live_package(client, db)
    _certify_first(client, headers, contract)

    before = client.get(
        f"/api/v1/subcontracts/{contract['id']}/certificate", headers=headers
    ).json()
    client.post(
        f"/api/v1/subcontracts/{contract['id']}/back-charges",
        json={"reason": "Scaffold left on site, removed by others", "amount": "1200"},
        headers=headers,
    )
    after = client.get(
        f"/api/v1/subcontracts/{contract['id']}/certificate", headers=headers
    ).json()

    assert Decimal(after["back_charges"]) == Decimal("1200.00")
    assert Decimal(after["net_payable"]) == Decimal(before["net_payable"]) - Decimal("1200.00")


def test_a_back_charge_gives_the_job_its_money_back_rather_than_earning_it(client, db):
    """The remedial work is already a cost on the job. Recovering it takes
    that cost off; it does not create income."""
    headers, contract, project = _live_package(client, db)
    _certify_first(client, headers, contract)

    before = client.get(f"/api/v1/projects/{project.id}/summary", headers=headers).json()
    client.post(
        f"/api/v1/subcontracts/{contract['id']}/back-charges",
        json={"reason": "Making good", "amount": "1500"},
        headers=headers,
    )
    after = client.get(f"/api/v1/projects/{project.id}/summary", headers=headers).json()

    assert Decimal(after["actual_total"]) == Decimal(before["actual_total"]) - Decimal("1500.00")


def test_a_back_charge_has_to_be_worth_something(client, db):
    headers, contract, _ = _live_package(client, db)
    res = client.post(
        f"/api/v1/subcontracts/{contract['id']}/back-charges",
        json={"reason": "Nothing", "amount": "0"},
        headers=headers,
    )
    assert res.status_code == 422


# --- Withholding tax ---------------------------------------------------------


def test_withholding_moves_money_to_the_revenue_authority_not_to_us(client, db):
    """It is not a saving. What we stop owing the subcontractor we start owing
    the taxman, and it stays owed until it is remitted."""
    headers, contract, _ = _live_package(client, db, withholding="10")
    _certify_first(client, headers, contract)

    res = client.post(
        f"/api/v1/subcontracts/{contract['id']}/withholding", json={}, headers=headers
    )
    assert res.status_code == 200, res.text
    body = res.json()
    # 40,000 certified less 4,000 retention, withheld at 10%.
    assert Decimal(body["base"]) == Decimal("36000.00")
    assert Decimal(body["withheld"]) == Decimal("3600.00")

    trial = client.get("/api/v1/accounting/trial-balance", headers=headers).json()
    wht = next(row for row in trial["rows"] if row["code"] == "2350")
    assert Decimal(wht["credit"]) == Decimal("3600.00")


def test_a_package_with_no_rate_is_not_silently_withheld_at_zero(client, db):
    """A subcontractor with a valid tax clearance is withheld at nothing, but
    that is a decision to record rather than one to assume."""
    headers, contract, _ = _live_package(client, db, withholding="0")
    _certify_first(client, headers, contract)

    res = client.post(
        f"/api/v1/subcontracts/{contract['id']}/withholding", json={}, headers=headers
    )
    assert res.status_code == 409
    assert "tax clearance" in res.json()["error"]["detail"]


def test_nothing_owed_means_nothing_to_withhold(client, db):
    headers, contract, _ = _live_package(client, db, withholding="10")
    res = client.post(
        f"/api/v1/subcontracts/{contract['id']}/withholding", json={}, headers=headers
    )
    assert res.status_code == 409


# --- The certificate ---------------------------------------------------------


def test_the_certificate_accounts_for_every_deduction(client, db):
    headers, contract, _ = _live_package(client, db, retention="10", withholding="10")
    _certify_first(client, headers, contract)

    variation = client.post(
        f"/api/v1/subcontracts/{contract['id']}/variations",
        json={"title": "Extra flashing", "amount": "6000"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/variations/{variation['id']}/approve", headers=headers)
    client.post(
        f"/api/v1/subcontracts/{contract['id']}/back-charges",
        json={"reason": "Making good", "amount": "1000"},
        headers=headers,
    )

    cert = client.get(
        f"/api/v1/subcontracts/{contract['id']}/certificate", headers=headers
    ).json()

    assert Decimal(cert["original_value"]) == Decimal("100000.00")
    assert Decimal(cert["variations"]) == Decimal("6000.00")
    assert Decimal(cert["contract_value"]) == Decimal("106000.00")
    assert Decimal(cert["certified"]) == Decimal("40000.00")
    assert Decimal(cert["retention_held"]) == Decimal("4000.00")
    assert Decimal(cert["back_charges"]) == Decimal("1000.00")
    assert Decimal(cert["withholding_tax"]) == Decimal("3600.00")
    # 40,000 − 4,000 retention − 1,000 back-charge − 3,600 tax.
    assert Decimal(cert["net_payable"]) == Decimal("31400.00")


def test_the_certificate_adds_up(client, db):
    """Whatever the numbers, the deductions have to reconcile the claim to the
    payment. A subcontractor paid a figure they cannot rebuild will ring."""
    headers, contract, _ = _live_package(client, db, retention="5", withholding="10")
    _certify_first(client, headers, contract)
    client.post(
        f"/api/v1/subcontracts/{contract['id']}/back-charges",
        json={"reason": "Damage to blockwork", "amount": "750"},
        headers=headers,
    )

    cert = client.get(
        f"/api/v1/subcontracts/{contract['id']}/certificate", headers=headers
    ).json()
    rebuilt = (
        Decimal(cert["certified"])
        - Decimal(cert["retention_held"])
        - Decimal(cert["back_charges"])
        - Decimal(cert["withholding_tax"])
    )
    assert rebuilt == Decimal(cert["net_payable"])
