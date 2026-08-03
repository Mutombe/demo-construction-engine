from app.common.enums import UserRole
from tests.factories import DEFAULT_PASSWORD, auth_headers, make_user


def test_login_success(client, db):
    make_user(db, email="pm@test.local", role=UserRole.project_manager)
    res = client.post(
        "/api/v1/auth/login", json={"email": "pm@test.local", "password": DEFAULT_PASSWORD}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["access_token"]
    assert body["user"]["email"] == "pm@test.local"
    assert body["user"]["role"] == "project_manager"
    assert "refresh_token" in res.cookies


def test_login_wrong_password(client, db):
    make_user(db, email="x@test.local")
    res = client.post(
        "/api/v1/auth/login", json={"email": "x@test.local", "password": "wrong-password"}
    )
    assert res.status_code == 401


def test_login_inactive_user(client, db):
    make_user(db, email="off@test.local", is_active=False)
    res = client.post(
        "/api/v1/auth/login", json={"email": "off@test.local", "password": DEFAULT_PASSWORD}
    )
    assert res.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_returns_current_user(client, db):
    user = make_user(db, email="me@test.local")
    res = client.get("/api/v1/auth/me", headers=auth_headers(user))
    assert res.status_code == 200
    assert res.json()["email"] == "me@test.local"


def test_refresh_rotates_token(client, db):
    make_user(db, email="r@test.local")
    login = client.post(
        "/api/v1/auth/login", json={"email": "r@test.local", "password": DEFAULT_PASSWORD}
    )
    first_refresh_cookie = login.cookies["refresh_token"]

    res = client.post("/api/v1/auth/refresh")
    assert res.status_code == 200
    assert res.json()["access_token"]
    second_cookie = res.cookies["refresh_token"]
    assert second_cookie != first_refresh_cookie


def test_refresh_reuse_detection_revokes_chain(client, db):
    make_user(db, email="theft@test.local")
    login = client.post(
        "/api/v1/auth/login", json={"email": "theft@test.local", "password": DEFAULT_PASSWORD}
    )
    stolen = login.cookies["refresh_token"]

    # Legitimate rotation
    ok = client.post("/api/v1/auth/refresh")
    assert ok.status_code == 200
    current = ok.cookies["refresh_token"]

    # Replay of the rotated (old) token → 401 and the whole chain is revoked
    client.cookies.set("refresh_token", stolen, path="/api/v1/auth")
    replay = client.post("/api/v1/auth/refresh")
    assert replay.status_code == 401

    # The current token no longer works either
    client.cookies.set("refresh_token", current, path="/api/v1/auth")
    after = client.post("/api/v1/auth/refresh")
    assert after.status_code == 401


def test_logout_revokes_refresh(client, db):
    make_user(db, email="bye@test.local")
    client.post(
        "/api/v1/auth/login", json={"email": "bye@test.local", "password": DEFAULT_PASSWORD}
    )
    assert client.post("/api/v1/auth/logout").status_code == 204
    # Cookie was cleared client-side; even replaying the old token fails
    res = client.post("/api/v1/auth/refresh")
    assert res.status_code == 401
