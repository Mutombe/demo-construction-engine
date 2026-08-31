"""Plant: what it did, what it burned, and what it cost."""

from datetime import date, timedelta
from decimal import Decimal

from app.common.enums import UserRole
from tests.factories import auth_headers, make_project, make_user

TODAY = date(2026, 10, 5)


def _pm(db):
    return auth_headers(make_user(db, role=UserRole.project_manager))


def _machine(client, headers, code="PLT-001", **kw):
    body = {
        "code": code,
        "name": kw.pop("name", "Excavator 20t"),
        "category": kw.pop("category", "excavator"),
        "meter_type": kw.pop("meter_type", "hours"),
        "current_meter": kw.pop("current_meter", "1000"),
        **kw,
    }
    res = client.post("/api/v1/equipment", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _reading(client, headers, machine, meter, when, **kw):
    return client.post(
        f"/api/v1/equipment/{machine['id']}/readings",
        json={"meter": str(meter), "reading_date": str(when), **kw},
        headers=headers,
    )


def _fuel(client, headers, machine, litres, meter, when, **kw):
    return client.post(
        f"/api/v1/equipment/{machine['id']}/fuel",
        json={"litres": str(litres), "meter": str(meter), "log_date": str(when), **kw},
        headers=headers,
    )


# --- The register ------------------------------------------------------------


def test_a_machine_is_registered_once(client, db):
    headers = _pm(db)
    _machine(client, headers, "PLT-001")
    duplicate = client.post(
        "/api/v1/equipment",
        json={"code": "PLT-001", "name": "Another", "category": "loader"},
        headers=headers,
    )
    assert duplicate.status_code == 409


def test_the_fleet_can_be_searched_by_plate(client, db):
    headers = _pm(db)
    _machine(client, headers, "PLT-002", name="Tipper", registration="ABC1234")
    found = client.get("/api/v1/equipment?search=abc123", headers=headers).json()
    assert found["total"] == 1
    assert found["items"][0]["registration"] == "ABC1234"


# --- Meter -------------------------------------------------------------------


def test_a_reading_moves_the_machines_meter_forward(client, db):
    headers = _pm(db)
    machine = _machine(client, headers, current_meter="1000")
    assert _reading(client, headers, machine, 1042, TODAY).status_code == 201

    again = client.get(f"/api/v1/equipment/{machine['id']}", headers=headers).json()
    assert Decimal(again["current_meter"]) == Decimal("1042.0")


def test_a_meter_cannot_go_backwards(client, db):
    """A reading below the last is a mis-key or a replaced meter. Accepting it
    would make the gap negative, and every figure here is built on the gaps."""
    headers = _pm(db)
    machine = _machine(client, headers, current_meter="1000")
    _reading(client, headers, machine, 1100, TODAY)

    res = _reading(client, headers, machine, 900, TODAY + timedelta(days=1))
    assert res.status_code == 422
    assert "cannot go backwards" in res.json()["error"]["detail"]


# --- Fuel --------------------------------------------------------------------


def test_fuel_is_measured_against_the_hours_it_ran(client, db):
    """Litres alone say nothing: a big machine burns a lot. Litres per hour
    run since the last fill is the comparable number."""
    headers = _pm(db)
    machine = _machine(client, headers, expected_burn_rate="20")
    # 100 hours at a normal 20 L/h
    _fuel(client, headers, machine, 200, 1000, TODAY)
    _fuel(client, headers, machine, 2000, 1100, TODAY + timedelta(days=5))

    flagged = client.get("/api/v1/fleet/fuel-exceptions", headers=headers).json()
    assert flagged == []


def test_a_draw_well_above_the_baseline_is_flagged(client, db):
    headers = _pm(db)
    machine = _machine(client, headers, expected_burn_rate="20")
    _fuel(client, headers, machine, 200, 1000, TODAY)
    # 100 hours run, but 4000 litres drawn: 40 L/h against a 20 L/h machine
    _fuel(client, headers, machine, 4000, 1100, TODAY + timedelta(days=5),
          operator="Night shift")

    flagged = client.get("/api/v1/fleet/fuel-exceptions", headers=headers).json()
    assert len(flagged) == 1
    assert flagged[0]["code"] == "PLT-001"
    assert Decimal(flagged[0]["rate"]) == Decimal("40.00")
    assert Decimal(flagged[0]["excess_pct"]) == Decimal("100.0")
    assert flagged[0]["operator"] == "Night shift"


def test_a_single_fill_is_never_flagged(client, db):
    """One fill gives no interval to measure against, and inventing one would
    manufacture the very number this is meant to test."""
    headers = _pm(db)
    machine = _machine(client, headers, expected_burn_rate="20")
    _fuel(client, headers, machine, 5000, 1000, TODAY)

    assert client.get("/api/v1/fleet/fuel-exceptions", headers=headers).json() == []


def test_without_a_stated_baseline_the_machines_own_median_is_used(client, db):
    """Median, so the outlier being hunted does not raise the bar it is
    measured against."""
    headers = _pm(db)
    machine = _machine(client, headers)  # no expected_burn_rate
    for index, (litres, meter) in enumerate(
        [(200, 1000), (200, 1010), (200, 1020), (2000, 1030)]
    ):
        _fuel(client, headers, machine, litres, meter, TODAY + timedelta(days=index))

    flagged = client.get("/api/v1/fleet/fuel-exceptions", headers=headers).json()
    assert len(flagged) == 1
    assert Decimal(flagged[0]["rate"]) == Decimal("200.00")


def test_fuel_with_a_cost_reaches_the_job(client, db):
    """Plant fuel is a real project cost, so it goes through the same ledger as
    everything else rather than sitting in a separate silo."""
    headers = _pm(db)
    project = make_project(db)
    machine = _machine(client, headers)
    _fuel(
        client, headers, machine, 500, 1050, TODAY,
        unit_cost="1.50", project_id=str(project.id),
    )

    entries = client.get(
        f"/api/v1/projects/{project.id}/cost-entries", headers=headers
    ).json()
    assert any(Decimal(e["amount"]) == Decimal("750.00") for e in entries["items"])


# --- Utilisation -------------------------------------------------------------


def test_utilisation_is_measured_between_readings(client, db):
    headers = _pm(db)
    machine = _machine(client, headers, current_meter="1000")
    start = TODAY
    end = TODAY + timedelta(days=9)  # 10 days, 80 available hours
    _reading(client, headers, machine, 1000, start)
    _reading(client, headers, machine, 1040, end)

    rows = client.get(
        f"/api/v1/fleet/utilisation?start={start}&end={end}", headers=headers
    ).json()
    row = next(r for r in rows if r["code"] == "PLT-001")
    assert Decimal(row["worked"]) == Decimal("40.0")
    assert Decimal(row["utilisation_pct"]) == Decimal("50.0")


def test_a_machine_nobody_read_reports_unknown_not_zero(client, db):
    """"We did not measure it" and "it did nothing" are different answers, and
    confusing them sends someone hunting an idle machine that was working."""
    headers = _pm(db)
    _machine(client, headers, "PLT-009", name="Unread")

    rows = client.get("/api/v1/fleet/utilisation", headers=headers).json()
    row = next(r for r in rows if r["code"] == "PLT-009")
    assert row["worked"] is None
    assert row["utilisation_pct"] is None
    assert row["measured"] is False


# --- Maintenance -------------------------------------------------------------


def test_a_service_falls_due_on_hours(client, db):
    headers = _pm(db)
    machine = _machine(client, headers, current_meter="900")
    client.post(
        f"/api/v1/equipment/{machine['id']}/schedules",
        json={"name": "250h service", "interval_meter": "250", "last_done_meter": "800"},
        headers=headers,
    )
    # Due at 1050 and the machine is on 900: 150 hours off, so not yet raised
    assert client.get("/api/v1/fleet/maintenance-due", headers=headers).json() == []

    _reading(client, headers, machine, 1060, TODAY)
    due = client.get("/api/v1/fleet/maintenance-due", headers=headers).json()
    assert len(due) == 1
    assert due[0]["status"] == "overdue"
    assert due[0]["service"] == "250h service"


def test_a_service_is_raised_before_it_is_missed(client, db):
    """Due soon rather than due today: a service that first appears on the day
    it is needed is a service nobody planned for."""
    headers = _pm(db)
    machine = _machine(client, headers, current_meter="1020")
    client.post(
        f"/api/v1/equipment/{machine['id']}/schedules",
        json={"name": "250h service", "interval_meter": "250", "last_done_meter": "800"},
        headers=headers,
    )
    due = client.get("/api/v1/fleet/maintenance-due", headers=headers).json()
    assert len(due) == 1
    assert due[0]["status"] == "due_soon"
    assert Decimal(due[0]["meter_remaining"]) == Decimal("30.0")


def test_a_service_also_falls_due_on_time(client, db):
    """Whichever comes first governs: a machine that has not done the hours is
    still due if the months have passed."""
    headers = _pm(db)
    machine = _machine(client, headers)
    client.post(
        f"/api/v1/equipment/{machine['id']}/schedules",
        json={
            "name": "Annual inspection",
            "interval_days": 365,
            "last_done_date": str(date.today() - timedelta(days=400)),
        },
        headers=headers,
    )
    due = client.get("/api/v1/fleet/maintenance-due", headers=headers).json()
    assert len(due) == 1
    assert due[0]["status"] == "overdue"


def test_a_schedule_needs_an_interval(client, db):
    headers = _pm(db)
    machine = _machine(client, headers)
    res = client.post(
        f"/api/v1/equipment/{machine['id']}/schedules",
        json={"name": "Vague"},
        headers=headers,
    )
    assert res.status_code == 422


def test_doing_the_service_resets_the_clock(client, db):
    headers = _pm(db)
    machine = _machine(client, headers, current_meter="1000")
    schedule = client.post(
        f"/api/v1/equipment/{machine['id']}/schedules",
        json={"name": "250h service", "interval_meter": "250", "last_done_meter": "800"},
        headers=headers,
    ).json()
    _reading(client, headers, machine, 1060, TODAY)
    assert client.get("/api/v1/fleet/maintenance-due", headers=headers).json()

    client.post(
        f"/api/v1/equipment/{machine['id']}/maintenance",
        json={
            "schedule_id": schedule["id"],
            "description": "Oil and filters",
            "meter": "1060",
            "cost": "450",
        },
        headers=headers,
    )
    assert client.get("/api/v1/fleet/maintenance-due", headers=headers).json() == []


# --- Deployment --------------------------------------------------------------


def test_moving_a_machine_closes_where_it_was(client, db):
    """A machine is in one place at a time; two open assignments would
    double-count the plant cost of every hour it ran."""
    headers = _pm(db)
    first, second = make_project(db), make_project(db)
    machine = _machine(client, headers)

    client.post(
        f"/api/v1/equipment/{machine['id']}/assign",
        json={"project_id": str(first.id), "started_on": str(TODAY)},
        headers=headers,
    )
    client.post(
        f"/api/v1/equipment/{machine['id']}/assign",
        json={"project_id": str(second.id), "started_on": str(TODAY + timedelta(days=7))},
        headers=headers,
    )

    history = client.get(
        f"/api/v1/equipment/{machine['id']}/assignments", headers=headers
    ).json()
    assert len(history) == 2
    closed = next(a for a in history if a["project_id"] == str(first.id))
    assert closed["ended_on"] == str(TODAY + timedelta(days=7))

    now = client.get(f"/api/v1/equipment/{machine['id']}", headers=headers).json()
    assert now["current_project_id"] == str(second.id)
    assert now["status"] == "on_site"


def test_a_machine_cannot_be_sent_where_it_already_is(client, db):
    headers = _pm(db)
    project = make_project(db)
    machine = _machine(client, headers)
    client.post(
        f"/api/v1/equipment/{machine['id']}/assign",
        json={"project_id": str(project.id)},
        headers=headers,
    )
    again = client.post(
        f"/api/v1/equipment/{machine['id']}/assign",
        json={"project_id": str(project.id)},
        headers=headers,
    )
    assert again.status_code == 409


def test_releasing_brings_it_back_to_the_yard(client, db):
    headers = _pm(db)
    project = make_project(db)
    machine = _machine(client, headers)
    client.post(
        f"/api/v1/equipment/{machine['id']}/assign",
        json={"project_id": str(project.id)},
        headers=headers,
    )
    released = client.post(
        f"/api/v1/equipment/{machine['id']}/release", headers=headers
    ).json()
    assert released["status"] == "available"
    assert released["current_project_id"] is None


def test_the_yard_summary_counts_what_needs_attention(client, db):
    headers = _pm(db)
    project = make_project(db)
    machine = _machine(client, headers)
    client.post(
        f"/api/v1/equipment/{machine['id']}/assign",
        json={"project_id": str(project.id)},
        headers=headers,
    )
    summary = client.get("/api/v1/fleet/summary", headers=headers).json()
    assert summary["total"] == 1
    assert summary["on_site"] == 1


def test_a_viewer_cannot_change_the_fleet(client, db):
    headers = _pm(db)
    machine = _machine(client, headers)
    viewer = auth_headers(make_user(db, role=UserRole.viewer))

    assert client.post(
        "/api/v1/equipment",
        json={"code": "PLT-999", "name": "Nope", "category": "loader"},
        headers=viewer,
    ).status_code == 403
    assert _reading(client, viewer, machine, 2000, TODAY).status_code == 403
    # Reading the fleet is fine
    assert client.get("/api/v1/equipment", headers=viewer).status_code == 200


# --- What a machine costs ----------------------------------------------------


def test_a_machine_reports_what_it_cost_and_what_that_is_per_hour(client, db):
    headers = _pm(db)
    machine = _machine(client, headers, "PLT-500", current_meter="1000")

    _reading(client, headers, machine, 1100, TODAY - timedelta(days=30))
    _fuel(client, headers, machine, 200, 1100, TODAY - timedelta(days=30), unit_cost="2")
    _reading(client, headers, machine, 1300, TODAY - timedelta(days=10))
    _fuel(client, headers, machine, 300, 1300, TODAY - timedelta(days=10), unit_cost="2")

    client.post(
        f"/api/v1/equipment/{machine['id']}/maintenance",
        json={"description": "500hr service", "cost": "600", "downtime_hours": "8",
              "service_date": str(TODAY - timedelta(days=5))},
        headers=headers,
    )

    costs = client.get(f"/api/v1/equipment/{machine['id']}/costs", headers=headers).json()
    assert Decimal(costs["fuel_cost"]) == Decimal("1000.00")
    assert Decimal(costs["workshop_cost"]) == Decimal("600.00")
    assert Decimal(costs["total_cost"]) == Decimal("1600.00")
    # 200 hours between the first and last reading in the window.
    assert Decimal(costs["metered"]) == Decimal("200")
    assert Decimal(costs["cost_per_unit"]) == Decimal("8.00")


def test_a_machine_that_never_moved_has_no_cost_per_hour(client, db):
    """Not zero. A machine that did no work has no cost per hour, and 0.00
    would read as free."""
    headers = _pm(db)
    machine = _machine(client, headers, "PLT-501", current_meter="1000")
    client.post(
        f"/api/v1/equipment/{machine['id']}/maintenance",
        json={"description": "Standing inspection", "cost": "300"},
        headers=headers,
    )

    costs = client.get(f"/api/v1/equipment/{machine['id']}/costs", headers=headers).json()
    assert Decimal(costs["workshop_cost"]) == Decimal("300.00")
    assert costs["cost_per_unit"] is None
    assert costs["metered"] is None


# --- Telematics imports ------------------------------------------------------


def _import(client, headers, rows):
    res = client.post("/api/v1/fleet/telematics/import", json={"rows": rows}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_an_export_lands_readings_and_fills_together(client, db):
    headers = _pm(db)
    machine = _machine(client, headers, "PLT-600", current_meter="2000")

    result = _import(client, headers, [
        {"code": "PLT-600", "reading_date": str(TODAY - timedelta(days=7)),
         "meter": "2050", "litres": "800", "unit_cost": "1.6"},
        {"code": "PLT-600", "reading_date": str(TODAY), "meter": "2110", "litres": "950"},
    ])
    assert result["applied"] == 2
    assert result["rejected"] == 0

    after = client.get(f"/api/v1/equipment/{machine['id']}", headers=headers).json()
    assert Decimal(after["current_meter"]) == Decimal("2110")

    fuel = client.get(f"/api/v1/equipment/{machine['id']}/fuel", headers=headers).json()
    assert len(fuel) == 2


def test_a_bad_row_is_reported_by_line_and_the_good_ones_still_land(client, db):
    """A file that stops dead on line 2 of 900 is worse than no import."""
    headers = _pm(db)
    _machine(client, headers, "PLT-601", current_meter="500")

    result = _import(client, headers, [
        {"code": "PLT-601", "reading_date": str(TODAY), "meter": "560"},
        {"code": "NOT-A-MACHINE", "reading_date": str(TODAY), "meter": "100"},
        {"code": "PLT-601", "reading_date": str(TODAY), "meter": "590"},
    ])
    assert result["applied"] == 2
    assert result["rejected"] == 1

    bad = next(r for r in result["results"] if r["status"] == "rejected")
    assert bad["line"] == 2
    assert "NOT-A-MACHINE" in bad["detail"]


def test_an_imported_meter_that_goes_backwards_is_refused_like_any_other(client, db):
    headers = _pm(db)
    _machine(client, headers, "PLT-602", current_meter="900")

    result = _import(client, headers, [
        {"code": "PLT-602", "reading_date": str(TODAY), "meter": "400"},
    ])
    assert result["rejected"] == 1
    assert "backwards" in result["results"][0]["detail"]


def test_an_import_is_marked_as_telematics_not_as_someone_typing(client, db):
    headers = _pm(db)
    machine = _machine(client, headers, "PLT-603", current_meter="100")
    _import(client, headers, [
        {"code": "PLT-603", "reading_date": str(TODAY), "meter": "160"},
    ])

    readings = client.get(
        f"/api/v1/equipment/{machine['id']}/readings", headers=headers
    ).json()
    assert readings[0]["source"] == "telematics"
