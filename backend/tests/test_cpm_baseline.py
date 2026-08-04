"""Critical path analysis and schedule baselines."""

from datetime import date, timedelta

from app.common.enums import DependencyType, UserRole
from app.modules.tasks import cpm
from tests.factories import auth_headers, make_project, make_task, make_user

TODAY = date(2026, 3, 2)  # a Monday; CPM here is calendar-day based


def _pm(db):
    return auth_headers(make_user(db, role=UserRole.project_manager))


def _node(name_id, start_offset, days):
    return cpm.TaskNode(
        id=name_id,
        start=TODAY + timedelta(days=start_offset),
        end=TODAY + timedelta(days=start_offset + days - 1),
    )


def test_cpm_finds_the_longest_chain(db):
    """A(5d) -> B(3d) -> D(2d) is longer than A -> C(1d) -> D, so C has float."""
    import uuid

    a, b, c, d = (uuid.uuid4() for _ in range(4))
    tasks = [_node(a, 0, 5), _node(b, 5, 3), _node(c, 5, 1), _node(d, 8, 2)]
    edges = [
        (a, b, DependencyType.FS, 0),
        (a, c, DependencyType.FS, 0),
        (b, d, DependencyType.FS, 0),
        (c, d, DependencyType.FS, 0),
    ]
    result = cpm.compute(tasks, edges)

    assert result.total_float[a] == 0
    assert result.total_float[b] == 0
    assert result.total_float[d] == 0
    assert result.total_float[c] == 2  # can slip 2 days without moving D
    assert result.critical == {a, b, d}
    assert result.project_finish == TODAY + timedelta(days=9)


def test_cpm_honours_lag_on_finish_to_start(db):
    import uuid

    a, b = uuid.uuid4(), uuid.uuid4()
    # B is planned to start immediately after A, but a 3-day lag pushes it out
    tasks = [_node(a, 0, 2), _node(b, 2, 2)]
    result = cpm.compute(tasks, [(a, b, DependencyType.FS, 3)])
    assert result.early_start[b] == TODAY + timedelta(days=5)


def test_cpm_start_to_start_and_finish_to_finish(db):
    import uuid

    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    tasks = [_node(a, 0, 5), _node(b, 0, 3), _node(c, 0, 4)]
    result = cpm.compute(
        tasks,
        [
            (a, b, DependencyType.SS, 2),  # B starts 2 days after A starts
            (a, c, DependencyType.FF, 1),  # C finishes 1 day after A finishes
        ],
    )
    assert result.early_start[b] == TODAY + timedelta(days=2)
    assert result.early_finish[c] == TODAY + timedelta(days=5)
    # Duration is preserved when a finish constraint pushes the task
    assert (result.early_finish[c] - result.early_start[c]).days == 3


def test_cpm_degrades_safely_on_empty_and_cyclic_input(db):
    import uuid

    assert cpm.compute([], []).project_finish is None

    a, b = uuid.uuid4(), uuid.uuid4()
    cyclic = cpm.compute(
        [_node(a, 0, 1), _node(b, 1, 1)],
        [(a, b, DependencyType.FS, 0), (b, a, DependencyType.FS, 0)],
    )
    assert cyclic.critical == set()  # no hang, no partial answer


def test_gantt_exposes_float_and_critical_flags(client, db):
    headers = _pm(db)
    project = make_project(db)
    a = make_task(
        db, project, name="Excavate",
        planned_start=TODAY, planned_end=TODAY + timedelta(days=4),
    )
    b = make_task(
        db, project, name="Foundations",
        planned_start=TODAY + timedelta(days=5), planned_end=TODAY + timedelta(days=7),
    )
    slack = make_task(
        db, project, name="Site signage",
        planned_start=TODAY, planned_end=TODAY + timedelta(days=1),
    )
    client.post(
        f"/api/v1/tasks/{b.id}/dependencies",
        json={"predecessor_id": str(a.id), "dep_type": "FS", "lag_days": 0},
        headers=headers,
    )

    gantt = client.get(f"/api/v1/projects/{project.id}/gantt", headers=headers).json()
    by_name = {t["name"]: t for t in gantt["tasks"]}
    assert by_name["Excavate"]["is_critical"] is True
    assert by_name["Foundations"]["is_critical"] is True
    assert by_name["Foundations"]["total_float"] == 0
    assert by_name["Site signage"]["is_critical"] is False
    assert by_name["Site signage"]["total_float"] > 0
    assert gantt["critical_path_length"] == 2
    assert gantt["project_finish"] == str(TODAY + timedelta(days=7))
    assert slack.id is not None


def test_undated_tasks_are_excluded_from_analysis(client, db):
    headers = _pm(db)
    project = make_project(db)
    make_task(db, project, name="Someday", planned_start=None, planned_end=None)

    gantt = client.get(f"/api/v1/projects/{project.id}/gantt", headers=headers).json()
    task = gantt["tasks"][0]
    assert task["total_float"] is None
    assert task["is_critical"] is False


def test_baseline_snapshot_and_slippage(client, db):
    headers = _pm(db)
    project = make_project(db)
    task = make_task(
        db, project, name="Roof",
        planned_start=TODAY, planned_end=TODAY + timedelta(days=10),
    )

    gantt = client.get(f"/api/v1/projects/{project.id}/gantt", headers=headers).json()
    assert gantt["has_baseline"] is False
    assert gantt["tasks"][0]["slippage_days"] is None

    baselined = client.post(f"/api/v1/projects/{project.id}/baseline", headers=headers).json()
    assert baselined["has_baseline"] is True
    assert baselined["tasks"][0]["slippage_days"] == 0
    assert baselined["tasks"][0]["baseline_end"] == str(TODAY + timedelta(days=10))

    # The programme slips by a week; the baseline does not move with it
    client.patch(
        f"/api/v1/tasks/{task.id}",
        json={"planned_end": str(TODAY + timedelta(days=17))},
        headers=headers,
    )
    after = client.get(f"/api/v1/projects/{project.id}/gantt", headers=headers).json()
    assert after["tasks"][0]["baseline_end"] == str(TODAY + timedelta(days=10))
    assert after["tasks"][0]["slippage_days"] == 7
    assert after["worst_slippage_days"] == 7

    cleared = client.delete(f"/api/v1/projects/{project.id}/baseline", headers=headers).json()
    assert cleared["has_baseline"] is False


def test_baseline_requires_project_manager(client, db):
    project = make_project(db)
    site = auth_headers(make_user(db, role=UserRole.site_manager))
    assert (
        client.post(f"/api/v1/projects/{project.id}/baseline", headers=site).status_code == 403
    )
