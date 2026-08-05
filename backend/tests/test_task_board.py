"""Subtasks, priorities, tags, and the calendar that sits on top of them."""

from datetime import date, timedelta

from app.common.enums import UserRole
from tests.factories import auth_headers, make_project, make_task, make_user

MONDAY = date(2026, 10, 5)


def _pm(db):
    return auth_headers(make_user(db, role=UserRole.project_manager))


def _create(client, headers, project, **body):
    return client.post(
        f"/api/v1/projects/{project.id}/tasks",
        json={"name": "Task", **body},
        headers=headers,
    )


def _list(client, headers, project, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    res = client.get(f"/api/v1/projects/{project.id}/tasks?{query}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_a_task_can_be_broken_into_subtasks(client, db):
    headers = _pm(db)
    project = make_project(db)
    parent = _create(client, headers, project, name="Pour the slab").json()
    first = _create(client, headers, project, name="Fix formwork", parent_id=parent["id"])
    assert first.status_code == 201
    assert first.json()["parent_id"] == parent["id"]
    _create(client, headers, project, name="Tie rebar", parent_id=parent["id"])

    rows = _list(client, headers, project)
    parent_row = next(t for t in rows if t["id"] == parent["id"])
    assert parent_row["subtask_count"] == 2
    assert parent_row["subtasks_done"] == 0

    # Only the parents when asked for the top level
    top = _list(client, headers, project, top_level_only="true")
    assert [t["id"] for t in top] == [parent["id"]]


def test_finished_subtasks_roll_up(client, db):
    headers = _pm(db)
    project = make_project(db)
    parent = _create(client, headers, project, name="Parent").json()
    child = _create(client, headers, project, name="Child", parent_id=parent["id"]).json()
    _create(client, headers, project, name="Other", parent_id=parent["id"])

    client.patch(f"/api/v1/tasks/{child['id']}", json={"status": "done"}, headers=headers)

    parent_row = next(t for t in _list(client, headers, project) if t["id"] == parent["id"])
    assert (parent_row["subtask_count"], parent_row["subtasks_done"]) == (2, 1)


def test_nesting_stops_at_one_level(client, db):
    """An arbitrary tree makes the Gantt bars and the critical path meaningless."""
    headers = _pm(db)
    project = make_project(db)
    parent = _create(client, headers, project, name="Parent").json()
    child = _create(client, headers, project, name="Child", parent_id=parent["id"]).json()

    res = _create(client, headers, project, name="Grandchild", parent_id=child["id"])
    assert res.status_code == 422
    assert "more than one level" in res.json()["error"]["detail"]


def test_a_task_with_subtasks_cannot_itself_become_one(client, db):
    headers = _pm(db)
    project = make_project(db)
    parent = _create(client, headers, project, name="Parent").json()
    _create(client, headers, project, name="Child", parent_id=parent["id"])
    other = _create(client, headers, project, name="Elsewhere").json()

    res = client.patch(
        f"/api/v1/tasks/{parent['id']}", json={"parent_id": other["id"]}, headers=headers
    )
    assert res.status_code == 422
    assert "subtasks of its own" in res.json()["error"]["detail"]


def test_a_task_cannot_be_its_own_parent(client, db):
    headers = _pm(db)
    project = make_project(db)
    task = _create(client, headers, project, name="Self").json()
    res = client.patch(
        f"/api/v1/tasks/{task['id']}", json={"parent_id": task["id"]}, headers=headers
    )
    assert res.status_code == 422


def test_a_parent_from_another_project_is_refused(client, db):
    headers = _pm(db)
    project = make_project(db)
    elsewhere = make_task(db, make_project(db), name="Different job")
    res = _create(client, headers, project, name="Orphan", parent_id=str(elsewhere.id))
    assert res.status_code == 422
    assert "different project" in res.json()["error"]["detail"]


def test_deleting_a_parent_takes_its_subtasks(client, db):
    headers = _pm(db)
    project = make_project(db)
    parent = _create(client, headers, project, name="Parent").json()
    _create(client, headers, project, name="Child", parent_id=parent["id"])

    assert client.delete(f"/api/v1/tasks/{parent['id']}", headers=headers).status_code == 204
    assert _list(client, headers, project) == []


def test_priority_defaults_to_normal_and_filters(client, db):
    headers = _pm(db)
    project = make_project(db)
    plain = _create(client, headers, project, name="Ordinary").json()
    assert plain["priority"] == "normal"
    _create(client, headers, project, name="Now", priority="urgent")

    urgent = _list(client, headers, project, priority="urgent")
    assert [t["name"] for t in urgent] == ["Now"]


def test_tags_are_saved_and_filterable(client, db):
    headers = _pm(db)
    project = make_project(db)
    _create(client, headers, project, name="Wet works", tags=["concrete", "critical"])
    _create(client, headers, project, name="Dry works", tags=["fitout"])

    assert _create(client, headers, project, name="Plain").json()["tags"] == []

    tagged = _list(client, headers, project, tag="concrete")
    assert [t["name"] for t in tagged] == ["Wet works"]

    in_use = client.get(f"/api/v1/projects/{project.id}/tags", headers=headers).json()
    assert in_use == ["concrete", "critical", "fitout"]


def test_comment_counts_ride_along_with_the_list(client, db):
    """The board shows a comment count, and doing that per card would be one
    query per task."""
    headers = _pm(db)
    project = make_project(db)
    task = _create(client, headers, project, name="Discussed").json()
    client.post(
        f"/api/v1/comments?entity_type=task&entity_id={task['id']}",
        json={"body": "Started"},
        headers=headers,
    )

    row = next(t for t in _list(client, headers, project) if t["id"] == task["id"])
    assert row["comment_count"] == 1


# --- Calendar ----------------------------------------------------------------


def _calendar(client, headers, start, end, **params):
    query = "&".join(f"{k}={v}" for k, v in {"start": start, "end": end, **params}.items())
    res = client.get(f"/api/v1/calendar?{query}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_the_calendar_shows_both_ends_of_a_task(client, db):
    headers = _pm(db)
    project = make_project(db)
    make_task(db, project, name="Groundworks",
              planned_start=MONDAY, planned_end=MONDAY + timedelta(days=3))

    body = _calendar(client, headers, MONDAY, MONDAY + timedelta(days=6))
    kinds = {(e["kind"], e["day"]) for e in body["events"]}
    assert ("task_start", str(MONDAY)) in kinds
    assert ("task_end", str(MONDAY + timedelta(days=3))) in kinds


def test_a_milestone_is_one_point_not_a_bar(client, db):
    headers = _pm(db)
    project = make_project(db)
    make_task(db, project, name="Practical completion", is_milestone=True,
              planned_start=MONDAY, planned_end=MONDAY)

    body = _calendar(client, headers, MONDAY, MONDAY + timedelta(days=6))
    mine = [e for e in body["events"] if "completion" in e["title"]]
    assert len(mine) == 1
    assert mine[0]["kind"] == "milestone"


def test_the_calendar_carries_more_than_tasks(client, db):
    """A week is only busy if you can see the delivery and the valuation
    cut-off landing in it too."""
    headers = _pm(db)
    project = make_project(db)
    supplier = client.post(
        "/api/v1/suppliers", json={"name": "Blue Circle"}, headers=headers
    ).json()
    po = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": supplier["id"],
            "expected_delivery": str(MONDAY + timedelta(days=2)),
            "items": [
                {"description": "Cement", "unit": "bag", "quantity": "10", "unit_price": "12"}
            ],
        },
        headers=headers,
    ).json()
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)

    body = _calendar(client, headers, MONDAY, MONDAY + timedelta(days=6))
    deliveries = [e for e in body["events"] if e["kind"] == "delivery"]
    assert len(deliveries) == 1
    assert "Blue Circle" in deliveries[0]["title"]


def test_finished_work_leaves_the_calendar(client, db):
    headers = _pm(db)
    project = make_project(db)
    task = make_task(db, project, name="Already done",
                     planned_start=MONDAY, planned_end=MONDAY + timedelta(days=1))
    client.patch(f"/api/v1/tasks/{task.id}", json={"status": "done"}, headers=headers)

    body = _calendar(client, headers, MONDAY, MONDAY + timedelta(days=6))
    assert all("Already done" not in e["title"] for e in body["events"])


def test_the_calendar_can_be_narrowed_to_one_project(client, db):
    headers = _pm(db)
    here = make_project(db)
    there = make_project(db)
    make_task(db, here, name="Mine", planned_start=MONDAY, planned_end=MONDAY)
    make_task(db, there, name="Theirs", planned_start=MONDAY, planned_end=MONDAY)

    body = _calendar(client, headers, MONDAY, MONDAY + timedelta(days=6), project_id=here.id)
    titles = " ".join(e["title"] for e in body["events"])
    assert "Mine" in titles and "Theirs" not in titles
