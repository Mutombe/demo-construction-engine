import pytest

from app.common.enums import UserRole
from tests.factories import auth_headers, make_client_record, make_project, make_user

ROLES = list(UserRole)


def _expect(role: UserRole, allowed: set[UserRole]) -> int:
    return 200 if role in allowed or role == UserRole.admin else 403


@pytest.mark.parametrize("role", ROLES)
def test_all_roles_can_read_projects(client, db, role):
    user = make_user(db, role=role)
    res = client.get("/api/v1/projects", headers=auth_headers(user))
    assert res.status_code == 200


@pytest.mark.parametrize("role", ROLES)
def test_project_create_matrix(client, db, role):
    user = make_user(db, role=role)
    c = make_client_record(db)
    res = client.post(
        "/api/v1/projects",
        json={"name": "RBAC Project", "client_id": str(c.id)},
        headers=auth_headers(user),
    )
    allowed = {UserRole.project_manager}
    expected = 201 if role in allowed or role == UserRole.admin else 403
    assert res.status_code == expected


@pytest.mark.parametrize("role", ROLES)
def test_task_update_matrix(client, db, role):
    from tests.factories import make_task

    project = make_project(db)
    task = make_task(db, project)
    user = make_user(db, role=role)
    res = client.patch(
        f"/api/v1/tasks/{task.id}",
        json={"progress_pct": 50},
        headers=auth_headers(user),
    )
    allowed = {UserRole.project_manager, UserRole.site_manager}
    assert res.status_code == _expect(role, allowed)


@pytest.mark.parametrize("role", ROLES)
def test_users_admin_only(client, db, role):
    user = make_user(db, role=role)
    res = client.get("/api/v1/users", headers=auth_headers(user))
    assert res.status_code == _expect(role, set())


@pytest.mark.parametrize("role", ROLES)
def test_boq_write_matrix(client, db, role):
    project = make_project(db)
    user = make_user(db, role=role)
    res = client.post(
        f"/api/v1/projects/{project.id}/boq/sections",
        json={"code": "A", "title": "Preliminaries"},
        headers=auth_headers(user),
    )
    allowed = {UserRole.project_manager}
    expected = 201 if role in allowed or role == UserRole.admin else 403
    assert res.status_code == expected


@pytest.mark.parametrize("role", ROLES)
def test_dashboard_read_all_roles(client, db, role):
    user = make_user(db, role=role)
    res = client.get("/api/v1/dashboard/overview", headers=auth_headers(user))
    assert res.status_code == 200


def test_inactive_user_rejected_even_with_valid_token(client, db):
    user = make_user(db, role=UserRole.admin)
    headers = auth_headers(user)
    user.is_active = False
    db.flush()
    res = client.get("/api/v1/projects", headers=headers)
    assert res.status_code == 401
