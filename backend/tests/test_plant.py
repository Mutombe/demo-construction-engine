"""Plant as a business: what it earns, what it wears out, what stops it.

The rule worth proving hardest is that a job is never charged twice for the
same diesel. Direct costing and internal hire are two coherent answers to
"what did the job pay for the machine", and running both at once is the
expensive mistake this module exists to make impossible.
"""

from datetime import date, timedelta
from decimal import Decimal

from app.common.enums import UserRole
from tests.factories import auth_headers, make_project, make_user

TODAY = date(2026, 10, 5)
# Compliance asks whether a certificate is in date *now*, so these are
# anchored to the real clock rather than to the fixture month.
REAL_TODAY = date.today()
PERIOD = date(2026, 10, 1)


def _pm(db):
    return auth_headers(make_user(db, role=UserRole.project_manager))


def _machine(client, headers, code="PLT-100", **kw):
    body = {
        "code": code,
        "name": kw.pop("name", "Excavator"),
        "category": kw.pop("category", "excavator"),
        "current_meter": kw.pop("current_meter", "1000"),
        "hourly_rate": kw.pop("hourly_rate", "50"),
        **kw,
    }
    res = client.post("/api/v1/equipment", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _insure(client, headers, machine, expires_in_days=365):
    return client.post(
        f"/api/v1/equipment/{machine['id']}/certificates",
        json={
            "cert_type": "insurance",
            "reference": "INS-1",
            "expires_on": str(REAL_TODAY + timedelta(days=expires_in_days)),
        },
        headers=headers,
    )


def _set_mode(client, db, mode):
    """How plant is costed is an accounts decision, so only an admin makes it."""
    admin = auth_headers(make_user(db, role=UserRole.admin))
    res = client.patch(
        "/api/v1/company-settings", json={"plant_costing_mode": mode}, headers=admin
    )
    assert res.status_code == 200, res.text
    return res.json()


def _reading(client, headers, machine, meter, when):
    res = client.post(
        f"/api/v1/equipment/{machine['id']}/readings",
        json={"meter": str(meter), "reading_date": str(when)},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


# --- The rule that stops a job being charged twice ---------------------------


def test_a_recharge_is_refused_while_costs_go_straight_to_the_job(client, db):
    headers = _pm(db)
    res = client.post(
        "/api/v1/fleet/recharge", json={"period_start": str(PERIOD)}, headers=headers
    )
    assert res.status_code == 409
    detail = res.json()["error"]["detail"].lower()
    assert "twice" in detail


def test_under_direct_costing_fuel_reaches_the_job(client, db):
    headers = _pm(db)
    project = make_project(db)
    machine = _machine(client, headers, "PLT-101")
    _insure(client, headers, machine)
    client.post(
        f"/api/v1/equipment/{machine['id']}/assign",
        json={"project_id": str(project.id)},
        headers=headers,
    )
    client.post(
        f"/api/v1/equipment/{machine['id']}/fuel",
        json={"litres": "100", "unit_cost": "2", "log_date": str(TODAY)},
        headers=headers,
    )

    summary = client.get(f"/api/v1/projects/{project.id}/summary", headers=headers).json()
    assert Decimal(summary["actual_total"]) == Decimal("200.00")


def test_under_internal_hire_fuel_goes_to_the_yard_not_the_job(client, db):
    """The job pays a rate for the hours instead, so the diesel must not also
    land on it."""
    headers = _pm(db)
    project = make_project(db)
    machine = _machine(client, headers, "PLT-102")
    _insure(client, headers, machine)
    client.post(
        f"/api/v1/equipment/{machine['id']}/assign",
        json={"project_id": str(project.id)},
        headers=headers,
    )
    _set_mode(client, db, "internal_hire")

    client.post(
        f"/api/v1/equipment/{machine['id']}/fuel",
        json={"litres": "100", "unit_cost": "2", "log_date": str(TODAY)},
        headers=headers,
    )

    summary = client.get(f"/api/v1/projects/{project.id}/summary", headers=headers).json()
    assert Decimal(summary["actual_total"]) == Decimal("0.00")


# --- The recharge itself -----------------------------------------------------


def test_hours_worked_are_charged_to_the_job_at_the_rate(client, db):
    headers = _pm(db)
    project = make_project(db)
    machine = _machine(client, headers, "PLT-103", current_meter="1000", hourly_rate="50")
    _insure(client, headers, machine)
    client.post(
        f"/api/v1/equipment/{machine['id']}/assign",
        json={"project_id": str(project.id), "started_on": str(PERIOD)},
        headers=headers,
    )
    _set_mode(client, db, "internal_hire")
    _reading(client, headers, machine, 1120, PERIOD + timedelta(days=20))

    res = client.post(
        "/api/v1/fleet/recharge", json={"period_start": str(PERIOD)}, headers=headers
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["recharged"] == 1
    # 120 hours at 50.
    assert Decimal(body["total"]) == Decimal("6000.00")

    summary = client.get(f"/api/v1/projects/{project.id}/summary", headers=headers).json()
    assert Decimal(summary["actual_total"]) == Decimal("6000.00")


def test_running_the_same_month_twice_does_not_charge_twice(client, db):
    headers = _pm(db)
    project = make_project(db)
    machine = _machine(client, headers, "PLT-104")
    _insure(client, headers, machine)
    client.post(
        f"/api/v1/equipment/{machine['id']}/assign",
        json={"project_id": str(project.id), "started_on": str(PERIOD)},
        headers=headers,
    )
    _set_mode(client, db, "internal_hire")
    _reading(client, headers, machine, 1100, PERIOD + timedelta(days=10))

    first = client.post(
        "/api/v1/fleet/recharge", json={"period_start": str(PERIOD)}, headers=headers
    ).json()
    second = client.post(
        "/api/v1/fleet/recharge", json={"period_start": str(PERIOD)}, headers=headers
    ).json()

    assert first["recharged"] == 1
    assert second["recharged"] == 0
    assert second["already_done"] == 1

    summary = client.get(f"/api/v1/projects/{project.id}/summary", headers=headers).json()
    assert Decimal(summary["actual_total"]) == Decimal(first["total"])


def test_hours_with_no_job_behind_them_are_not_charged_to_anyone(client, db):
    """Better to charge nobody than to charge a job for hours that might be
    another job's."""
    headers = _pm(db)
    machine = _machine(client, headers, "PLT-105")
    _insure(client, headers, machine)
    _set_mode(client, db, "internal_hire")
    _reading(client, headers, machine, 1090, PERIOD + timedelta(days=9))

    body = client.post(
        "/api/v1/fleet/recharge", json={"period_start": str(PERIOD)}, headers=headers
    ).json()
    assert body["recharged"] == 0


def test_the_recharge_is_a_reallocation_and_never_revenue(client, db):
    """Charging our own job for our own machine does not create turnover.
    Nothing left the business."""
    headers = _pm(db)
    project = make_project(db)
    machine = _machine(client, headers, "PLT-106")
    _insure(client, headers, machine)
    client.post(
        f"/api/v1/equipment/{machine['id']}/assign",
        json={"project_id": str(project.id), "started_on": str(PERIOD)},
        headers=headers,
    )
    _set_mode(client, db, "internal_hire")
    _reading(client, headers, machine, 1100, PERIOD + timedelta(days=10))

    before = client.get(
        "/api/v1/accounting/income-statement",
        params={"start": str(PERIOD), "end": str(PERIOD + timedelta(days=30))},
        headers=headers,
    ).json()
    client.post("/api/v1/fleet/recharge", json={"period_start": str(PERIOD)}, headers=headers)
    after = client.get(
        "/api/v1/accounting/income-statement",
        params={"start": str(PERIOD), "end": str(PERIOD + timedelta(days=30))},
        headers=headers,
    ).json()

    assert Decimal(after["revenue_total"]) == Decimal(before["revenue_total"])


def test_recovery_shows_what_the_yard_cost_against_what_it_charged(client, db):
    headers = _pm(db)
    project = make_project(db)
    machine = _machine(client, headers, "PLT-107", hourly_rate="10")
    _insure(client, headers, machine)
    client.post(
        f"/api/v1/equipment/{machine['id']}/assign",
        json={"project_id": str(project.id), "started_on": str(PERIOD)},
        headers=headers,
    )
    _set_mode(client, db, "internal_hire")

    client.post(
        f"/api/v1/equipment/{machine['id']}/fuel",
        json={"litres": "100", "unit_cost": "3", "log_date": str(PERIOD + timedelta(days=2))},
        headers=headers,
    )
    _reading(client, headers, machine, 1010, PERIOD + timedelta(days=10))
    client.post("/api/v1/fleet/recharge", json={"period_start": str(PERIOD)}, headers=headers)

    report = client.get(
        "/api/v1/fleet/recovery",
        params={"start": str(PERIOD), "end": str(PERIOD + timedelta(days=30))},
        headers=headers,
    ).json()
    assert Decimal(report["pooled"]) == Decimal("300.00")
    assert Decimal(report["recovered"]) == Decimal("100.00")
    assert Decimal(report["under_recovered"]) == Decimal("200.00")


# --- Statutory compliance ----------------------------------------------------


def test_paperwork_nobody_has_entered_yet_does_not_ground_the_yard(client, db):
    """A missing certificate is an absence of data, not evidence of an absence
    of insurance. Refusing to move any machine until every certificate has
    been typed in is a rule people work around within a week."""
    headers = _pm(db)
    project = make_project(db)
    machine = _machine(client, headers, "PLT-200")

    res = client.post(
        f"/api/v1/equipment/{machine['id']}/assign",
        json={"project_id": str(project.id)},
        headers=headers,
    )
    assert res.status_code == 201

    status = client.get(
        f"/api/v1/equipment/{machine['id']}/compliance", headers=headers
    ).json()
    assert status["incomplete"] == ["insurance"]
    assert status["is_compliant"] is False


def test_insurance_that_has_actually_lapsed_does_stop_it(client, db):
    """Expired is different from missing: somebody entered cover and it ran
    out, which is a fact rather than a gap."""
    headers = _pm(db)
    project = make_project(db)
    machine = _machine(client, headers, "PLT-201")
    _insure(client, headers, machine, expires_in_days=-1)

    res = client.post(
        f"/api/v1/equipment/{machine['id']}/assign",
        json={"project_id": str(project.id)},
        headers=headers,
    )
    assert res.status_code == 409
    assert "insurance" in res.json()["error"]["detail"].lower()


def test_lifting_gear_is_stopped_even_by_an_examination_nobody_entered(client, db):
    """The one place a missing certificate blocks. A crane may not lawfully
    lift without a current thorough examination, and the cost of being wrong
    is not a fine."""
    headers = _pm(db)
    project = make_project(db)
    crane = _machine(client, headers, "CRN-900", category="crane")
    _insure(client, headers, crane)

    res = client.post(
        f"/api/v1/equipment/{crane['id']}/assign",
        json={"project_id": str(project.id)},
        headers=headers,
    )
    assert res.status_code == 409
    assert "thorough examination" in res.json()["error"]["detail"].lower()

    client.post(
        f"/api/v1/equipment/{crane['id']}/certificates",
        json={
            "cert_type": "thorough_examination",
            "expires_on": str(REAL_TODAY + timedelta(days=180)),
        },
        headers=headers,
    )
    res = client.post(
        f"/api/v1/equipment/{crane['id']}/assign",
        json={"project_id": str(project.id)},
        headers=headers,
    )
    assert res.status_code == 201


def test_a_generator_is_not_asked_for_a_roadworthiness_test(client, db):
    headers = _pm(db)
    project = make_project(db)
    genset = _machine(client, headers, "GEN-900", category="generator")
    _insure(client, headers, genset)

    res = client.post(
        f"/api/v1/equipment/{genset['id']}/assign",
        json={"project_id": str(project.id)},
        headers=headers,
    )
    assert res.status_code == 201


def test_renewing_a_certificate_does_not_leave_the_old_one_deciding(client, db):
    headers = _pm(db)
    machine = _machine(client, headers, "PLT-202")
    _insure(client, headers, machine, expires_in_days=-5)
    _insure(client, headers, machine, expires_in_days=300)

    status = client.get(
        f"/api/v1/equipment/{machine['id']}/compliance", headers=headers
    ).json()
    assert status["is_compliant"] is True


def test_certificates_about_to_lapse_are_listed_before_they_ground_a_machine(client, db):
    headers = _pm(db)
    machine = _machine(client, headers, "PLT-203")
    _insure(client, headers, machine, expires_in_days=10)

    rows = client.get(
        "/api/v1/fleet/certificates/expiring", params={"days": 30}, headers=headers
    ).json()
    assert any(row["code"] == "PLT-203" for row in rows)


# --- Depreciation ------------------------------------------------------------


def test_a_machine_with_a_cost_and_a_life_is_written_down_monthly(client, db):
    headers = _pm(db)
    machine = _machine(
        client, headers, "PLT-300", purchase_cost="120000", purchase_date=str(PERIOD)
    )
    client.patch(
        f"/api/v1/equipment/{machine['id']}",
        json={"residual_value": "0", "useful_life_months": 60},
        headers=headers,
    )

    res = client.post(
        "/api/v1/fleet/depreciation", json={"period_start": str(PERIOD)}, headers=headers
    )
    assert res.status_code == 200, res.text
    assert Decimal(res.json()["total"]) == Decimal("2000.00")

    register = client.get("/api/v1/fleet/assets", headers=headers).json()
    row = next(r for r in register if r["code"] == "PLT-300")
    assert Decimal(row["accumulated_depreciation"]) == Decimal("2000.00")
    assert Decimal(row["net_book_value"]) == Decimal("118000.00")


def test_a_machine_with_no_life_entered_is_not_depreciated_over_a_guess(client, db):
    headers = _pm(db)
    _machine(client, headers, "PLT-301", purchase_cost="90000")

    body = client.post(
        "/api/v1/fleet/depreciation", json={"period_start": str(PERIOD)}, headers=headers
    ).json()
    assert "PLT-301" in body["not_depreciated"]
    assert Decimal(body["total"]) == Decimal("0.00")


def test_the_same_month_cannot_be_depreciated_twice(client, db):
    headers = _pm(db)
    machine = _machine(client, headers, "PLT-302", purchase_cost="60000")
    client.patch(
        f"/api/v1/equipment/{machine['id']}",
        json={"residual_value": "0", "useful_life_months": 60},
        headers=headers,
    )

    client.post("/api/v1/fleet/depreciation", json={"period_start": str(PERIOD)}, headers=headers)
    again = client.post(
        "/api/v1/fleet/depreciation", json={"period_start": str(PERIOD)}, headers=headers
    ).json()
    assert again["posted"] == 0
    assert again["already_done"] == 1

    register = client.get("/api/v1/fleet/assets", headers=headers).json()
    row = next(r for r in register if r["code"] == "PLT-302")
    assert Decimal(row["accumulated_depreciation"]) == Decimal("1000.00")


def test_depreciation_stops_at_the_residual(client, db):
    headers = _pm(db)
    machine = _machine(client, headers, "PLT-303", purchase_cost="1200")
    client.patch(
        f"/api/v1/equipment/{machine['id']}",
        json={"residual_value": "1000", "useful_life_months": 2},
        headers=headers,
    )

    total = Decimal("0")
    for month in range(1, 6):
        body = client.post(
            "/api/v1/fleet/depreciation",
            json={"period_start": str(date(2026, month, 1))},
            headers=headers,
        ).json()
        total += Decimal(body["total"])

    # 200 depreciable, never more, however many months are run.
    assert total == Decimal("200.00")
    register = client.get("/api/v1/fleet/assets", headers=headers).json()
    row = next(r for r in register if r["code"] == "PLT-303")
    assert Decimal(row["net_book_value"]) == Decimal("1000.00")


# --- Availability ------------------------------------------------------------


def test_availability_counts_time_on_a_job_not_calendar_time(client, db):
    """A machine in the yard is unused, not unavailable. Rolling the two
    together makes both numbers meaningless."""
    headers = _pm(db)
    machine = _machine(client, headers, "PLT-400")
    _insure(client, headers, machine)

    rows = client.get(
        "/api/v1/fleet/availability",
        params={"start": str(PERIOD), "end": str(PERIOD + timedelta(days=30))},
        headers=headers,
    ).json()
    row = next(r for r in rows if r["code"] == "PLT-400")
    assert row["assigned_days"] == 0
    assert row["availability_pct"] is None


def test_downtime_shows_against_the_time_it_was_meant_to_be_working(client, db):
    headers = _pm(db)
    project = make_project(db)
    machine = _machine(client, headers, "PLT-401")
    _insure(client, headers, machine)
    client.post(
        f"/api/v1/equipment/{machine['id']}/assign",
        json={"project_id": str(project.id), "started_on": str(PERIOD)},
        headers=headers,
    )
    client.post(
        f"/api/v1/equipment/{machine['id']}/maintenance",
        json={
            "description": "Hydraulic hose",
            "downtime_hours": "8",
            "service_date": str(PERIOD + timedelta(days=3)),
        },
        headers=headers,
    )

    rows = client.get(
        "/api/v1/fleet/availability",
        params={"start": str(PERIOD), "end": str(PERIOD + timedelta(days=9))},
        headers=headers,
    ).json()
    row = next(r for r in rows if r["code"] == "PLT-401")
    # Ten assigned days at eight hours, one of them lost.
    assert row["assigned_days"] == 10
    assert Decimal(row["downtime_hours"]) == Decimal("8.00")
    assert row["availability_pct"] == 90.0
