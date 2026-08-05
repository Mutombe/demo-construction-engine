"""Who is carrying too much."""

from datetime import date, timedelta
from decimal import Decimal

from app.common.enums import UserRole, WorkStatus
from tests.factories import auth_headers, make_project, make_task, make_user

MONDAY = date(2026, 9, 7)


def _workload(client, headers, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    res = client.get(f"/api/v1/workload?{query}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _person(body, name):
    return next(p for p in body["people"] if p["full_name"] == name)


def test_overlapping_tasks_show_as_concurrency(client, db):
    """Two tasks live on the same day is the thing a PM is actually asking
    about — being in two places at once."""
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    foreman = make_user(db, role=UserRole.site_manager, full_name="Busy Foreman")
    project = make_project(db)
    make_task(
        db, project, name="Slab", assignee_id=foreman.id,
        planned_start=MONDAY, planned_end=MONDAY + timedelta(days=4),
    )
    make_task(
        db, project, name="Blockwork", assignee_id=foreman.id,
        planned_start=MONDAY + timedelta(days=2), planned_end=MONDAY + timedelta(days=6),
    )

    body = _workload(client, headers, start=MONDAY, end=MONDAY + timedelta(days=13))
    person = _person(body, "Busy Foreman")
    assert person["open_tasks"] == 2
    assert person["peak_concurrency"] == 2
    # Seven distinct days are covered by at least one of the two tasks
    assert person["busy_days"] == 7


def test_overload_is_flagged_only_past_the_limit(client, db):
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    foreman = make_user(db, role=UserRole.site_manager, full_name="Stretched")
    project = make_project(db)
    for name in ("A", "B", "C"):
        make_task(
            db, project, name=name, assignee_id=foreman.id,
            planned_start=MONDAY, planned_end=MONDAY + timedelta(days=1),
        )

    # Default limit of 2: three concurrent tasks is over it
    body = _workload(client, headers, start=MONDAY, end=MONDAY + timedelta(days=6))
    person = _person(body, "Stretched")
    assert person["peak_concurrency"] == 3
    assert person["overloaded_days"] == 2

    # Raise the limit and the same data is no longer an alarm
    relaxed = _workload(client, headers, start=MONDAY, end=MONDAY + timedelta(days=6), limit=3)
    assert _person(relaxed, "Stretched")["overloaded_days"] == 0


def test_undated_tasks_are_counted_but_never_invented_onto_days(client, db):
    """Guessing a window for an undated task would manufacture overload that
    does not exist."""
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    person = make_user(db, role=UserRole.site_manager, full_name="Vague Work")
    project = make_project(db)
    make_task(db, project, name="Someday", assignee_id=person.id,
              planned_start=None, planned_end=None)

    body = _workload(client, headers, start=MONDAY, end=MONDAY + timedelta(days=6))
    loaded = _person(body, "Vague Work")
    assert loaded["open_tasks"] == 1
    assert loaded["peak_concurrency"] == 0
    assert loaded["busy_days"] == 0
    assert loaded["tasks"][0]["is_scheduled"] is False


def test_finished_work_stops_counting_against_anyone(client, db):
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    person = make_user(db, role=UserRole.site_manager, full_name="Finished Up")
    project = make_project(db)
    make_task(
        db, project, name="Done", assignee_id=person.id, status=WorkStatus.done,
        planned_start=MONDAY, planned_end=MONDAY + timedelta(days=3),
    )

    body = _workload(client, headers, start=MONDAY, end=MONDAY + timedelta(days=6))
    assert all(p["full_name"] != "Finished Up" for p in body["people"])


def test_unassigned_work_is_surfaced_and_sinks_to_the_bottom(client, db):
    """Nobody owning a task is its own problem, so it is shown rather than
    quietly dropped — but it never outranks a real person."""
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    person = make_user(db, role=UserRole.site_manager, full_name="Real Person")
    project = make_project(db)
    make_task(db, project, name="Orphan", assignee_id=None,
              planned_start=MONDAY, planned_end=MONDAY + timedelta(days=2))
    make_task(db, project, name="Owned", assignee_id=person.id,
              planned_start=MONDAY, planned_end=MONDAY + timedelta(days=2))

    body = _workload(client, headers, start=MONDAY, end=MONDAY + timedelta(days=6))
    names = [p["full_name"] for p in body["people"]]
    assert "Unassigned" in names
    assert names[-1] == "Unassigned"
    assert _person(body, "Unassigned")["user_id"] is None


def test_the_next_free_day_is_reported(client, db):
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    person = make_user(db, role=UserRole.site_manager, full_name="Free Soon")
    project = make_project(db)
    make_task(db, project, name="Until Wednesday", assignee_id=person.id,
              planned_start=MONDAY, planned_end=MONDAY + timedelta(days=2))

    body = _workload(client, headers, start=MONDAY, end=MONDAY + timedelta(days=6))
    assert _person(body, "Free Soon")["next_free_day"] == str(MONDAY + timedelta(days=3))


def test_hours_booked_follow_the_task_to_its_assignee(client, db):
    """Timesheets belong to workers, who are not users, so hours are credited
    through the task they name."""
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    person = make_user(db, role=UserRole.site_manager, full_name="Hours Owner")
    project = make_project(db)
    task = make_task(db, project, name="Tracked", assignee_id=person.id,
                     planned_start=MONDAY, planned_end=MONDAY + timedelta(days=4))

    worker = client.post(
        "/api/v1/workers",
        json={"full_name": "Site Hand", "trade": "General", "pay_basis": "hourly",
              "rate": "5.00"},
        headers=headers,
    ).json()
    res = client.post(
        "/api/v1/timesheets",
        json={"worker_id": worker["id"], "project_id": str(project.id),
              "task_id": str(task.id), "work_date": str(MONDAY), "quantity": "8",
              "overtime_quantity": "2"},
        headers=headers,
    )
    assert res.status_code == 201
    assert res.json()["task_id"] == str(task.id)

    body = _workload(client, headers, start=MONDAY, end=MONDAY + timedelta(days=6))
    assert _person(body, "Hours Owner")["hours_booked"] == 10.0


def test_time_cannot_be_booked_to_another_projects_task(client, db):
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    project = make_project(db)
    elsewhere = make_task(db, make_project(db), name="Different job")
    worker = client.post(
        "/api/v1/workers",
        json={"full_name": "Hand", "trade": "General", "pay_basis": "hourly",
              "rate": "5.00"},
        headers=headers,
    ).json()

    res = client.post(
        "/api/v1/timesheets",
        json={"worker_id": worker["id"], "project_id": str(project.id),
              "task_id": str(elsewhere.id), "work_date": str(MONDAY), "quantity": "8"},
        headers=headers,
    )
    assert res.status_code == 422
    assert "different project" in res.json()["error"]["detail"]


def test_the_window_can_be_narrowed_to_one_project(client, db):
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    person = make_user(db, role=UserRole.site_manager, full_name="Split Across Jobs")
    here = make_project(db)
    there = make_project(db)
    make_task(db, here, name="This job", assignee_id=person.id,
              planned_start=MONDAY, planned_end=MONDAY + timedelta(days=2))
    make_task(db, there, name="That job", assignee_id=person.id,
              planned_start=MONDAY, planned_end=MONDAY + timedelta(days=2))

    everything = _workload(client, headers, start=MONDAY, end=MONDAY + timedelta(days=6))
    assert _person(everything, "Split Across Jobs")["open_tasks"] == 2

    one = _workload(client, headers, start=MONDAY, end=MONDAY + timedelta(days=6),
                    project_id=here.id)
    assert _person(one, "Split Across Jobs")["open_tasks"] == 1


def test_a_backwards_window_is_refused(client, db):
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    res = client.get(
        f"/api/v1/workload?start={MONDAY}&end={MONDAY - timedelta(days=5)}", headers=headers
    )
    assert res.status_code == 422


# --- Site labour -------------------------------------------------------------


def _worker(client, headers, name, basis="daily", rate="40.00"):
    return client.post(
        "/api/v1/workers",
        json={"full_name": name, "trade": "General", "pay_basis": basis, "rate": rate},
        headers=headers,
    ).json()


def _book(client, headers, worker, project, day, quantity="1", overtime="0"):
    return client.post(
        "/api/v1/timesheets",
        json={
            "worker_id": worker["id"],
            "project_id": str(project.id),
            "work_date": str(day),
            "quantity": quantity,
            "overtime_quantity": overtime,
        },
        headers=headers,
    )


def _worker_row(body, name):
    return next(w for w in body["workers"] if w["full_name"] == name)


def test_site_labour_is_measured_by_time_booked_not_tasks(client, db):
    """A worker is not a system user and can never be an assignee, so the only
    honest measure of their load is the time actually booked against them."""
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    project = make_project(db)
    worker = _worker(client, headers, "Tendai Moyo")
    for offset in range(3):
        _book(client, headers, worker, project, MONDAY + timedelta(days=offset))

    body = _workload(client, headers, start=MONDAY, end=MONDAY + timedelta(days=6))
    row = _worker_row(body, "Tendai Moyo")
    assert row["days_booked"] == 3
    assert Decimal(row["total_booked"]) == Decimal("3.00")
    assert row["projects"] == 1
    assert row["over_days"] == 0


def test_a_worker_on_two_sites_in_one_day_shows_as_split(client, db):
    """The unique constraint allows it on purpose — people genuinely move
    between sites — but a planner should be able to see it."""
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    here, there = make_project(db), make_project(db)
    worker = _worker(client, headers, "Split Worker")
    _book(client, headers, worker, here, MONDAY, quantity="0.5")
    _book(client, headers, worker, there, MONDAY, quantity="0.5")

    row = _worker_row(
        _workload(client, headers, start=MONDAY, end=MONDAY + timedelta(days=6)), "Split Worker"
    )
    assert row["split_days"] == 1
    assert row["projects"] == 2
    assert row["over_days"] == 0  # half a day each still adds to one day


def test_booking_more_than_a_full_day_is_flagged(client, db):
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    here, there = make_project(db), make_project(db)
    worker = _worker(client, headers, "Overbooked")
    _book(client, headers, worker, here, MONDAY)
    _book(client, headers, worker, there, MONDAY)

    row = _worker_row(
        _workload(client, headers, start=MONDAY, end=MONDAY + timedelta(days=6)), "Overbooked"
    )
    assert row["over_days"] == 1
    assert Decimal(row["total_booked"]) == Decimal("2.00")


def test_a_full_day_means_eight_hours_for_an_hourly_worker(client, db):
    """One is a full day on a daily rate and nonsense on an hourly one, so the
    threshold follows how the worker is actually paid."""
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    project = make_project(db)
    worker = _worker(client, headers, "Hourly Hand", basis="hourly", rate="5.00")
    _book(client, headers, worker, project, MONDAY, quantity="8", overtime="2")

    row = _worker_row(
        _workload(client, headers, start=MONDAY, end=MONDAY + timedelta(days=6)), "Hourly Hand"
    )
    assert row["over_days"] == 0
    assert Decimal(row["total_overtime"]) == Decimal("2.00")


def test_worker_load_can_be_narrowed_to_one_project(client, db):
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    here, there = make_project(db), make_project(db)
    worker = _worker(client, headers, "Across Jobs")
    _book(client, headers, worker, here, MONDAY, quantity="0.5")
    _book(client, headers, worker, there, MONDAY, quantity="0.5")

    scoped = _workload(
        client, headers, start=MONDAY, end=MONDAY + timedelta(days=6), project_id=here.id
    )
    assert _worker_row(scoped, "Across Jobs")["projects"] == 1
