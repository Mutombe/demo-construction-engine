from app.common.enums import UserRole
from tests.factories import auth_headers, make_project, make_task, make_user


def _link(client, headers, successor, predecessor, **kw):
    return client.post(
        f"/api/v1/tasks/{successor.id}/dependencies",
        json={"predecessor_id": str(predecessor.id), **kw},
        headers=headers,
    )


def test_add_and_remove_dependency(client, db):
    pm = make_user(db, role=UserRole.project_manager)
    headers = auth_headers(pm)
    project = make_project(db)
    a, b = make_task(db, project), make_task(db, project)

    res = _link(client, headers, b, a, dep_type="FS", lag_days=2)
    assert res.status_code == 201
    assert res.json()["lag_days"] == 2

    res = client.delete(f"/api/v1/tasks/{b.id}/dependencies/{a.id}", headers=headers)
    assert res.status_code == 204


def test_duplicate_dependency_conflict(client, db):
    pm = make_user(db, role=UserRole.project_manager)
    headers = auth_headers(pm)
    project = make_project(db)
    a, b = make_task(db, project), make_task(db, project)
    assert _link(client, headers, b, a).status_code == 201
    assert _link(client, headers, b, a).status_code == 409


def test_self_dependency_rejected(client, db):
    pm = make_user(db, role=UserRole.project_manager)
    project = make_project(db)
    a = make_task(db, project)
    res = _link(client, auth_headers(pm), a, a)
    assert res.status_code == 422


def test_direct_cycle_rejected(client, db):
    pm = make_user(db, role=UserRole.project_manager)
    headers = auth_headers(pm)
    project = make_project(db)
    a, b = make_task(db, project), make_task(db, project)
    assert _link(client, headers, b, a).status_code == 201  # a -> b
    res = _link(client, headers, a, b)  # b -> a closes the loop
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "dependency_cycle"


def test_transitive_cycle_rejected(client, db):
    pm = make_user(db, role=UserRole.project_manager)
    headers = auth_headers(pm)
    project = make_project(db)
    a, b, c = make_task(db, project), make_task(db, project), make_task(db, project)
    assert _link(client, headers, b, a).status_code == 201  # a -> b
    assert _link(client, headers, c, b).status_code == 201  # b -> c
    res = _link(client, headers, a, c)  # c -> a closes a 3-node loop
    assert res.status_code == 409


def test_cross_project_dependency_rejected(client, db):
    pm = make_user(db, role=UserRole.project_manager)
    headers = auth_headers(pm)
    p1, p2 = make_project(db), make_project(db)
    a, b = make_task(db, p1), make_task(db, p2)
    res = _link(client, headers, b, a)
    assert res.status_code == 422


def test_gantt_payload_shape(client, db):
    from tests.factories import make_phase

    pm = make_user(db, role=UserRole.project_manager)
    headers = auth_headers(pm)
    project = make_project(db)
    phase = make_phase(db, project)
    a = make_task(db, project, phase_id=phase.id)
    b = make_task(db, project, phase_id=phase.id)
    _link(client, headers, b, a)

    res = client.get(f"/api/v1/projects/{project.id}/gantt", headers=headers)
    assert res.status_code == 200
    payload = res.json()
    assert len(payload["phases"]) == 1
    assert len(payload["tasks"]) == 2
    assert len(payload["dependencies"]) == 1
    assert payload["dependencies"][0]["predecessor_id"] == str(a.id)


def test_status_done_syncs_progress(client, db):
    pm = make_user(db, role=UserRole.project_manager)
    project = make_project(db)
    task = make_task(db, project)
    res = client.patch(
        f"/api/v1/tasks/{task.id}", json={"status": "done"}, headers=auth_headers(pm)
    )
    assert res.status_code == 200
    assert res.json()["progress_pct"] == 100
