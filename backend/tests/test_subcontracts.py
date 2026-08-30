"""Vendor compliance, and work let out in stages."""

from datetime import date, timedelta
from decimal import Decimal

from app.common.enums import UserRole
from tests.factories import auth_headers, make_project, make_supplier, make_user

TODAY = date.today()


def _pm(db):
    return auth_headers(make_user(db, role=UserRole.project_manager))


def _doc(client, headers, supplier, doc_type, expires_on):
    return client.post(
        f"/api/v1/suppliers/{supplier.id}/compliance/documents",
        json={
            "doc_type": doc_type,
            "reference": f"{doc_type}-1",
            "expires_on": str(expires_on) if expires_on else None,
        },
        headers=headers,
    )


MANDATORY = (
    "company_registration",
    "tax_clearance",
    "public_liability",
    "workmans_compensation",
)


def _make_compliant(client, headers, supplier, expires_in_days=365, skip=()):
    """Everything mandatory, in date, and the vendor approved.

    `skip` leaves a document out so a test can supply its own lapsed copy.
    """
    when = TODAY + timedelta(days=expires_in_days)
    for doc_type in MANDATORY:
        if doc_type in skip:
            continue
        _doc(client, headers, supplier, doc_type, when)
    client.post(
        f"/api/v1/suppliers/{supplier.id}/vendor-status",
        json={"vendor_status": "approved"},
        headers=headers,
    )


def _subcontract(client, headers, project, supplier, value="100000", retention="10",
                 milestones=None):
    body = {
        "supplier_id": str(supplier.id),
        "title": "Groundworks package",
        "value": value,
        "retention_pct": retention,
        "milestones": milestones
        if milestones is not None
        else [
            {"name": "Site clearance", "value": "40000"},
            {"name": "Bulk excavation", "value": "60000"},
        ],
    }
    res = client.post(
        f"/api/v1/projects/{project.id}/subcontracts", json=body, headers=headers
    )
    assert res.status_code == 201, res.text
    return res.json()


# --- Compliance --------------------------------------------------------------


def test_a_new_supplier_is_not_compliant_until_the_papers_are_in(client, db):
    headers = _pm(db)
    supplier = make_supplier(db, name="Fresh Vendor")

    status = client.get(f"/api/v1/suppliers/{supplier.id}/compliance", headers=headers).json()
    assert status["is_compliant"] is False
    assert status["vendor_status"] == "pending"
    assert "tax_clearance" in status["blocking"]


def test_missing_and_expired_are_different_answers(client, db):
    """They need different conversations: one was never supplied, the other
    lapsed on someone's watch."""
    headers = _pm(db)
    supplier = make_supplier(db)
    _doc(client, headers, supplier, "tax_clearance", TODAY - timedelta(days=10))

    status = client.get(f"/api/v1/suppliers/{supplier.id}/compliance", headers=headers).json()
    states = {d["doc_type"]: d["state"] for d in status["documents"]}
    assert states["tax_clearance"] == "expired"
    assert states["public_liability"] == "missing"


def test_a_certificate_about_to_lapse_is_flagged_before_it_does(client, db):
    headers = _pm(db)
    supplier = make_supplier(db)
    _doc(client, headers, supplier, "tax_clearance", TODAY + timedelta(days=10))

    status = client.get(f"/api/v1/suppliers/{supplier.id}/compliance", headers=headers).json()
    tax = next(d for d in status["documents"] if d["doc_type"] == "tax_clearance")
    assert tax["state"] == "expiring"
    assert tax["days_to_expiry"] == 10
    # Expiring is not yet blocking: there is still time to chase it
    assert "tax_clearance" not in status["blocking"]


def test_a_document_with_no_expiry_stays_valid(client, db):
    headers = _pm(db)
    supplier = make_supplier(db)
    _doc(client, headers, supplier, "company_registration", None)

    status = client.get(f"/api/v1/suppliers/{supplier.id}/compliance", headers=headers).json()
    registration = next(
        d for d in status["documents"] if d["doc_type"] == "company_registration"
    )
    assert registration["state"] == "valid"


def test_a_renewal_replaces_the_old_certificate(client, db):
    """Re-uploading a renewed certificate should not leave the lapsed one
    deciding the answer."""
    headers = _pm(db)
    supplier = make_supplier(db)
    _doc(client, headers, supplier, "tax_clearance", TODAY - timedelta(days=5))
    _doc(client, headers, supplier, "tax_clearance", TODAY + timedelta(days=360))

    status = client.get(f"/api/v1/suppliers/{supplier.id}/compliance", headers=headers).json()
    tax = next(d for d in status["documents"] if d["doc_type"] == "tax_clearance")
    assert tax["state"] == "valid"


def test_everything_about_to_lapse_is_listed_in_one_place(client, db):
    headers = _pm(db)
    soon = make_supplier(db, name="Lapsing Soon")
    fine = make_supplier(db, name="All Good")
    _doc(client, headers, soon, "tax_clearance", TODAY + timedelta(days=7))
    _doc(client, headers, fine, "tax_clearance", TODAY + timedelta(days=300))

    rows = client.get("/api/v1/compliance/expiring?days=30", headers=headers).json()
    names = {r["supplier_name"] for r in rows}
    assert "Lapsing Soon" in names
    assert "All Good" not in names


def test_a_requirement_can_be_made_optional(client, db):
    """What a contractor demands of a scaffolder is not what it demands of a
    stationery supplier, and the list changes when the law does."""
    headers = _pm(db)
    supplier = make_supplier(db)

    client.put(
        "/api/v1/compliance/requirements",
        json={"doc_type": "workmans_compensation", "is_mandatory": False, "warn_days": 30},
        headers=headers,
    )
    status = client.get(f"/api/v1/suppliers/{supplier.id}/compliance", headers=headers).json()
    assert "workmans_compensation" not in status["blocking"]


# --- The gate ----------------------------------------------------------------


def test_work_cannot_be_awarded_to_a_vendor_with_lapsed_papers(client, db):
    """Where "prevents audit non-compliance" stops being a claim: the system
    will not create the commitment at all."""
    headers = _pm(db)
    project = make_project(db)
    supplier = make_supplier(db, name="Lapsed Ltd")
    # Everything in order except the insurance, whose only certificate expired
    # yesterday. A vendor still holding a valid one is covered, so the lapsed
    # copy has to be the only one for this to be the real situation.
    _make_compliant(client, headers, supplier, skip=("public_liability",))
    _doc(client, headers, supplier, "public_liability", TODAY - timedelta(days=1))

    contract = _subcontract(client, headers, project, supplier)
    res = client.post(f"/api/v1/subcontracts/{contract['id']}/award", headers=headers)
    assert res.status_code == 409
    assert "public liability" in res.json()["error"]["detail"]


def test_work_cannot_be_awarded_to_an_unapproved_vendor(client, db):
    headers = _pm(db)
    project = make_project(db)
    supplier = make_supplier(db, name="Not Approved")
    when = TODAY + timedelta(days=365)
    for doc_type in MANDATORY:
        _doc(client, headers, supplier, doc_type, when)

    contract = _subcontract(client, headers, project, supplier)
    res = client.post(f"/api/v1/subcontracts/{contract['id']}/award", headers=headers)
    assert res.status_code == 409
    assert "not been approved" in res.json()["error"]["detail"]


def test_a_suspended_vendor_is_refused_even_with_good_papers(client, db):
    """Approval is a decision about the relationship, separate from the
    paperwork."""
    headers = _pm(db)
    project = make_project(db)
    supplier = make_supplier(db, name="Suspended Ltd")
    _make_compliant(client, headers, supplier)
    client.post(
        f"/api/v1/suppliers/{supplier.id}/vendor-status",
        json={"vendor_status": "suspended"},
        headers=headers,
    )

    contract = _subcontract(client, headers, project, supplier)
    res = client.post(f"/api/v1/subcontracts/{contract['id']}/award", headers=headers)
    assert res.status_code == 409
    assert "suspended" in res.json()["error"]["detail"]


def test_a_compliant_approved_vendor_can_be_awarded(client, db):
    headers = _pm(db)
    project = make_project(db)
    supplier = make_supplier(db)
    _make_compliant(client, headers, supplier)

    contract = _subcontract(client, headers, project, supplier)
    res = client.post(f"/api/v1/subcontracts/{contract['id']}/award", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "awarded"


# --- Milestones --------------------------------------------------------------


def test_milestones_cannot_exceed_the_contract(client, db):
    """Under is normal; over is always a mistake, and catching it here is
    cheaper than finding it when the last stage cannot be paid."""
    headers = _pm(db)
    project = make_project(db)
    supplier = make_supplier(db)
    res = client.post(
        f"/api/v1/projects/{project.id}/subcontracts",
        json={
            "supplier_id": str(supplier.id),
            "title": "Overstaged",
            "value": "10000",
            "milestones": [{"name": "One", "value": "8000"}, {"name": "Two", "value": "5000"}],
        },
        headers=headers,
    )
    assert res.status_code == 422
    assert "Milestones come to" in res.json()["error"]["detail"]


def test_a_package_cannot_be_awarded_with_no_stages(client, db):
    headers = _pm(db)
    project = make_project(db)
    supplier = make_supplier(db)
    _make_compliant(client, headers, supplier)
    contract = _subcontract(client, headers, project, supplier, milestones=[])

    res = client.post(f"/api/v1/subcontracts/{contract['id']}/award", headers=headers)
    assert res.status_code == 422


def test_certifying_a_stage_books_the_cost_and_holds_retention(client, db):
    """Three things in one act: the job carries the full cost, the
    subcontractor is owed the net, and what is held sits where it can be seen."""
    headers = _pm(db)
    project = make_project(db)
    supplier = make_supplier(db)
    _make_compliant(client, headers, supplier)
    contract = _subcontract(client, headers, project, supplier, retention="10")
    client.post(f"/api/v1/subcontracts/{contract['id']}/award", headers=headers)

    milestone = contract["milestones"][0]  # 40,000
    res = client.post(f"/api/v1/milestones/{milestone['id']}/certify", json={}, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert Decimal(body["certified_amount"]) == Decimal("40000.00")
    assert Decimal(body["retention_held"]) == Decimal("4000.00")

    accounts = client.get("/api/v1/accounting/accounts", headers=headers).json()
    balance = {a["code"]: Decimal(a["balance"]) for a in accounts}
    assert balance["5300"] == Decimal("40000.00")  # cost of works, subcontract
    assert balance["2000"] == Decimal("36000.00")  # owed to the subcontractor
    assert balance["2300"] == Decimal("4000.00")  # retention held back


def test_the_certified_cost_reaches_the_job(client, db):
    headers = _pm(db)
    project = make_project(db)
    supplier = make_supplier(db)
    _make_compliant(client, headers, supplier)
    contract = _subcontract(client, headers, project, supplier)
    client.post(f"/api/v1/subcontracts/{contract['id']}/award", headers=headers)
    client.post(
        f"/api/v1/milestones/{contract['milestones'][0]['id']}/certify",
        json={},
        headers=headers,
    )

    entries = client.get(
        f"/api/v1/projects/{project.id}/cost-entries", headers=headers
    ).json()
    assert any(Decimal(e["amount"]) == Decimal("40000.00") for e in entries["items"])


def test_a_stage_can_be_certified_for_less_than_it_was_priced(client, db):
    """Overwriting the price would lose what was agreed, so the certified
    amount is its own field."""
    headers = _pm(db)
    project = make_project(db)
    supplier = make_supplier(db)
    _make_compliant(client, headers, supplier)
    contract = _subcontract(client, headers, project, supplier, retention="0")
    client.post(f"/api/v1/subcontracts/{contract['id']}/award", headers=headers)

    milestone = contract["milestones"][0]
    body = client.post(
        f"/api/v1/milestones/{milestone['id']}/certify",
        json={"certified_amount": "25000"},
        headers=headers,
    ).json()
    assert Decimal(body["value"]) == Decimal("40000.00")
    assert Decimal(body["certified_amount"]) == Decimal("25000.00")


def test_a_stage_cannot_be_certified_for_more_than_it_was_priced(client, db):
    headers = _pm(db)
    project = make_project(db)
    supplier = make_supplier(db)
    _make_compliant(client, headers, supplier)
    contract = _subcontract(client, headers, project, supplier)
    client.post(f"/api/v1/subcontracts/{contract['id']}/award", headers=headers)

    res = client.post(
        f"/api/v1/milestones/{contract['milestones'][0]['id']}/certify",
        json={"certified_amount": "999999"},
        headers=headers,
    )
    assert res.status_code == 422
    assert "more than" in res.json()["error"]["detail"]


def test_a_stage_cannot_be_certified_twice(client, db):
    headers = _pm(db)
    project = make_project(db)
    supplier = make_supplier(db)
    _make_compliant(client, headers, supplier)
    contract = _subcontract(client, headers, project, supplier)
    client.post(f"/api/v1/subcontracts/{contract['id']}/award", headers=headers)
    milestone = contract["milestones"][0]

    assert client.post(
        f"/api/v1/milestones/{milestone['id']}/certify", json={}, headers=headers
    ).status_code == 200
    again = client.post(
        f"/api/v1/milestones/{milestone['id']}/certify", json={}, headers=headers
    )
    assert again.status_code == 409


def test_nothing_can_be_certified_before_the_package_is_awarded(client, db):
    headers = _pm(db)
    project = make_project(db)
    supplier = make_supplier(db)
    _make_compliant(client, headers, supplier)
    contract = _subcontract(client, headers, project, supplier)

    res = client.post(
        f"/api/v1/milestones/{contract['milestones'][0]['id']}/certify",
        json={},
        headers=headers,
    )
    assert res.status_code == 409


def test_the_package_closes_when_every_stage_is_signed_off(client, db):
    headers = _pm(db)
    project = make_project(db)
    supplier = make_supplier(db)
    _make_compliant(client, headers, supplier)
    contract = _subcontract(client, headers, project, supplier)
    client.post(f"/api/v1/subcontracts/{contract['id']}/award", headers=headers)

    for milestone in contract["milestones"]:
        client.post(f"/api/v1/milestones/{milestone['id']}/certify", json={}, headers=headers)

    detail = client.get(f"/api/v1/subcontracts/{contract['id']}", headers=headers).json()
    assert detail["status"] == "completed"
    assert Decimal(detail["certified"]) == Decimal("100000.00")
    assert Decimal(detail["retention_held"]) == Decimal("10000.00")
    assert Decimal(detail["net_payable"]) == Decimal("90000.00")
    assert Decimal(detail["remaining"]) == 0


def test_the_books_still_balance_after_certifying(client, db):
    headers = _pm(db)
    project = make_project(db)
    supplier = make_supplier(db)
    _make_compliant(client, headers, supplier)
    contract = _subcontract(client, headers, project, supplier)
    client.post(f"/api/v1/subcontracts/{contract['id']}/award", headers=headers)
    client.post(
        f"/api/v1/milestones/{contract['milestones'][0]['id']}/certify",
        json={},
        headers=headers,
    )

    trial = client.get("/api/v1/accounting/trial-balance", headers=headers).json()
    assert trial["balanced"] is True
    # And the ledger has no gap: the milestone's cost entry carries a journal
    assert client.get("/api/v1/accounting/unposted", headers=headers).json() == []


def test_only_a_project_manager_certifies(client, db):
    """Certifying releases money, so it sits with whoever carries the job's
    cost rather than whoever raised the package."""
    headers = _pm(db)
    project = make_project(db)
    supplier = make_supplier(db)
    _make_compliant(client, headers, supplier)
    contract = _subcontract(client, headers, project, supplier)
    client.post(f"/api/v1/subcontracts/{contract['id']}/award", headers=headers)

    officer = auth_headers(make_user(db, role=UserRole.procurement_officer))
    res = client.post(
        f"/api/v1/milestones/{contract['milestones'][0]['id']}/certify",
        json={},
        headers=officer,
    )
    assert res.status_code == 403
