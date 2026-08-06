"""The permission matrix, and the exceptions on top of it."""

from app.common.enums import UserRole
from app.modules.permissions import service
from app.modules.permissions.defaults import DEFAULT_MATRIX, all_permissions
from tests.factories import auth_headers, make_user


def _admin(db):
    return auth_headers(make_user(db, role=UserRole.admin))


def test_the_starting_matrix_is_exactly_what_the_app_enforced_before(client, db):
    """Switching to a stored matrix must change nobody's access on the day it
    ships. Editing is the new part; the starting point is not."""
    matrix = service.role_matrix(db)
    for role, expected in DEFAULT_MATRIX.items():
        if role is UserRole.admin:
            continue
        assert set(matrix[role.value]) == set(expected), role.value


def test_seeding_is_idempotent_and_never_resets_an_edit(client, db):
    service.ensure_seeded(db)
    service.set_role_permission(db, UserRole.viewer, "task:write", True)
    assert service.ensure_seeded(db) == 0
    assert "task:write" in service.role_matrix(db)["viewer"]


def test_granting_and_revoking_a_role_permission(client, db):
    headers = _admin(db)
    viewer = make_user(db, role=UserRole.viewer)
    assert not service.can(db, viewer, "task:write")

    res = client.put(
        "/api/v1/permissions/matrix",
        json={"role": "viewer", "permission": "task:write", "allowed": True},
        headers=headers,
    )
    assert res.status_code == 200
    assert "task:write" in res.json()["viewer"]
    assert service.can(db, viewer, "task:write")

    client.put(
        "/api/v1/permissions/matrix",
        json={"role": "viewer", "permission": "task:write", "allowed": False},
        headers=headers,
    )
    assert not service.can(db, viewer, "task:write")


def test_administrators_cannot_be_edited_down(client, db):
    """An editable matrix with no floor is one bad click away from a company
    with nobody who can fix it."""
    headers = _admin(db)
    res = client.put(
        "/api/v1/permissions/matrix",
        json={"role": "admin", "permission": "users:manage", "allowed": False},
        headers=headers,
    )
    assert res.status_code == 409

    admin = make_user(db, role=UserRole.admin)
    assert service.effective_permissions(db, admin) == set(all_permissions())


def test_one_person_can_be_granted_something_their_role_lacks(client, db):
    headers = _admin(db)
    storeman = make_user(db, role=UserRole.viewer)
    assert not service.can(db, storeman, "inventory:write")

    res = client.put(
        f"/api/v1/permissions/users/{storeman.id}",
        json={"permission": "inventory:write", "allowed": True},
        headers=headers,
    )
    assert res.status_code == 200
    assert "inventory:write" in res.json()["effective"]
    assert service.can(db, storeman, "inventory:write")

    # And the rest of that role is untouched: an exception stays an exception
    other = make_user(db, role=UserRole.viewer)
    assert not service.can(db, other, "inventory:write")


def test_one_person_can_be_denied_something_their_role_has(client, db):
    headers = _admin(db)
    pm = make_user(db, role=UserRole.project_manager)
    assert service.can(db, pm, "expense:approve")

    client.put(
        f"/api/v1/permissions/users/{pm.id}",
        json={"permission": "expense:approve", "allowed": False},
        headers=headers,
    )
    assert not service.can(db, pm, "expense:approve")


def test_clearing_an_override_puts_someone_back_on_their_role(client, db):
    headers = _admin(db)
    pm = make_user(db, role=UserRole.project_manager)
    client.put(
        f"/api/v1/permissions/users/{pm.id}",
        json={"permission": "expense:approve", "allowed": False},
        headers=headers,
    )
    assert not service.can(db, pm, "expense:approve")

    res = client.put(
        f"/api/v1/permissions/users/{pm.id}",
        json={"permission": "expense:approve", "allowed": None},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["overrides"] == {}
    assert service.can(db, pm, "expense:approve")


def test_an_unknown_permission_is_refused(client, db):
    headers = _admin(db)
    res = client.put(
        "/api/v1/permissions/matrix",
        json={"role": "viewer", "permission": "nonsense:write", "allowed": True},
        headers=headers,
    )
    assert res.status_code == 422


def test_everyone_can_read_their_own_permissions(client, db):
    """The frontend gates on this rather than on a table compiled into the
    bundle, so an edit lands on the next page load."""
    for role in (UserRole.site_manager, UserRole.viewer):
        headers = auth_headers(make_user(db, role=role))
        res = client.get("/api/v1/permissions/me", headers=headers)
        assert res.status_code == 200
        assert set(res.json()) == set(DEFAULT_MATRIX[role])


def test_only_an_administrator_edits_the_matrix(client, db):
    for role in (UserRole.project_manager, UserRole.site_manager, UserRole.viewer):
        headers = auth_headers(make_user(db, role=role))
        assert client.get("/api/v1/permissions/matrix", headers=headers).status_code == 403
        assert client.put(
            "/api/v1/permissions/matrix",
            json={"role": "viewer", "permission": "task:write", "allowed": True},
            headers=headers,
        ).status_code == 403


def test_the_catalogue_describes_every_permission_it_can_grant(client, db):
    headers = _admin(db)
    body = client.get("/api/v1/permissions/catalogue", headers=headers).json()
    listed = {
        action["permission"] for module in body["modules"] for action in module["actions"]
    }
    assert listed == set(all_permissions())
    assert set(body["roles"]) == {role.value for role in UserRole}
