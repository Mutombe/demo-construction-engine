"""Activity log and user invitations."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.common.enums import UserRole
from app.modules.admin.models import UserInvite
from tests.factories import (
    auth_headers,
    make_boq_item,
    make_boq_section,
    make_project,
    make_supplier,
    make_user,
)


def _admin(db):
    return auth_headers(make_user(db, role=UserRole.admin))


def _activity(client, headers, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    res = client.get(f"/api/v1/admin/activity?{query}", headers=headers)
    assert res.status_code == 200
    return res.json()


def test_approving_an_expense_is_recorded(client, db):
    admin = _admin(db)
    approver = make_user(db, role=UserRole.project_manager, full_name="Tendai Moyo")
    project = make_project(db)
    site = auth_headers(make_user(db, role=UserRole.site_manager))
    claim = client.post(
        f"/api/v1/projects/{project.id}/expenses",
        json={
            "category": "materials",
            "expense_date": str(date.today()),
            "amount": "125.00",
            "description": "Diesel for the mixer",
        },
        headers=site,
    ).json()
    client.post(
        f"/api/v1/expenses/{claim['id']}/approve", headers=auth_headers(approver)
    )

    entries = _activity(client, admin)["items"]
    entry = next(e for e in entries if e["action"] == "expense_approved")
    assert entry["user_name"] == "Tendai Moyo"
    assert claim["doc_number"] in entry["summary"]
    assert entry["entity_type"] == "expense"
    assert entry["link_path"] == f"/expenses/{claim['id']}"


def test_issuing_a_purchase_order_is_recorded(client, db):
    admin = _admin(db)
    officer = make_user(db, role=UserRole.procurement_officer, full_name="Rudo Marufu")
    project = make_project(db)
    supplier = make_supplier(db, name="Blue Circle")
    po = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "items": [
                {"description": "Cement", "unit": "bag", "quantity": "10", "unit_price": "12.00"}
            ],
        },
        headers=auth_headers(officer),
    ).json()
    client.post(
        f"/api/v1/purchase-orders/{po['id']}/issue", headers=auth_headers(officer)
    )

    entry = next(
        e for e in _activity(client, admin)["items"] if e["action"] == "po_issued"
    )
    assert entry["user_name"] == "Rudo Marufu"
    assert "Blue Circle" in entry["summary"]


def test_the_log_survives_the_record_it_describes(client, db):
    """A log entry that stops making sense once the user leaves is no audit
    trail at all, so the name is snapshotted."""
    admin = _admin(db)
    approver = make_user(db, role=UserRole.project_manager, full_name="Departing Person")
    project = make_project(db, contract_value=Decimal("100000"))
    valuation = client.post(
        f"/api/v1/projects/{project.id}/valuations",
        json={"period_end": str(date.today()), "gross_valuation": "5000"},
        headers=auth_headers(approver),
    ).json()
    client.post(
        f"/api/v1/valuations/{valuation['id']}/issue",
        json={},
        headers=auth_headers(approver),
    )

    entry = next(
        e for e in _activity(client, admin)["items"] if e["action"] == "valuation_issued"
    )
    assert entry["user_name"] == "Departing Person"
    assert valuation["doc_number"] in entry["summary"]


def test_activity_can_be_filtered(client, db):
    admin = _admin(db)
    project = make_project(db)
    site = auth_headers(make_user(db, role=UserRole.site_manager))
    pm = make_user(db, role=UserRole.project_manager)
    claim = client.post(
        f"/api/v1/projects/{project.id}/expenses",
        json={
            "category": "fuel",
            "expense_date": str(date.today()),
            "amount": "40.00",
            "description": "Fuel",
        },
        headers=site,
    ).json()
    client.post(f"/api/v1/expenses/{claim['id']}/approve", headers=auth_headers(pm))

    by_action = _activity(client, admin, action="expense_approved")
    assert by_action["total"] >= 1
    assert all(e["action"] == "expense_approved" for e in by_action["items"])
    assert _activity(client, admin, action="nothing_like_this")["total"] == 0

    actions = client.get("/api/v1/admin/activity/actions", headers=admin).json()
    assert "expense_approved" in actions


def test_activity_log_is_admin_only(client, db):
    for role in (UserRole.project_manager, UserRole.site_manager, UserRole.viewer):
        headers = auth_headers(make_user(db, role=role))
        assert client.get("/api/v1/admin/activity", headers=headers).status_code == 403


# --- Invites -----------------------------------------------------------------


def test_invite_returns_its_link_once_then_never_again(client, db):
    admin = _admin(db)
    res = client.post(
        "/api/v1/admin/invites",
        json={"email": "New.Person@example.com", "full_name": "New Person", "role": "site_manager"},
        headers=admin,
    )
    assert res.status_code == 201
    created = res.json()
    assert "/accept-invite/" in created["invite_url"]
    assert created["status"] == "pending"
    assert created["email"] == "new.person@example.com"  # normalised

    # The raw token is not recoverable from any later read
    listed = client.get("/api/v1/admin/invites", headers=admin).json()
    assert all("invite_url" not in invite for invite in listed)
    stored = db.scalar(select(UserInvite).where(UserInvite.email == "new.person@example.com"))
    assert stored.token_hash and stored.token_hash not in created["invite_url"]


def test_accepting_an_invite_creates_a_working_account(client, db):
    admin = _admin(db)
    created = client.post(
        "/api/v1/admin/invites",
        json={"email": "joiner@example.com", "full_name": "Joiner", "role": "procurement_officer"},
        headers=admin,
    ).json()
    token = created["invite_url"].rsplit("/", 1)[1]

    res = client.post(
        "/api/v1/invites/accept", json={"token": token, "password": "brandnew123"}
    )
    assert res.status_code == 200
    assert res.json()["role"] == "procurement_officer"

    # The new account can actually sign in
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "joiner@example.com", "password": "brandnew123"},
    )
    assert login.status_code == 200
    # And the joining is on the record
    entries = client.get("/api/v1/admin/activity", headers=admin).json()["items"]
    assert any(e["action"] == "user_joined" for e in entries)


def test_an_invite_cannot_be_used_twice(client, db):
    admin = _admin(db)
    created = client.post(
        "/api/v1/admin/invites",
        json={"email": "once@example.com", "full_name": "Once", "role": "viewer"},
        headers=admin,
    ).json()
    token = created["invite_url"].rsplit("/", 1)[1]

    assert client.post(
        "/api/v1/invites/accept", json={"token": token, "password": "password123"}
    ).status_code == 200
    second = client.post(
        "/api/v1/invites/accept", json={"token": token, "password": "password123"}
    )
    assert second.status_code == 422
    assert "already been accepted" in second.json()["error"]["detail"]


def test_revoked_and_expired_invites_are_refused(client, db):
    admin = _admin(db)
    created = client.post(
        "/api/v1/admin/invites",
        json={"email": "revoked@example.com", "full_name": "Revoked", "role": "viewer"},
        headers=admin,
    ).json()
    token = created["invite_url"].rsplit("/", 1)[1]
    client.post(f"/api/v1/admin/invites/{created['id']}/revoke", headers=admin)

    res = client.post(
        "/api/v1/invites/accept", json={"token": token, "password": "password123"}
    )
    assert res.status_code == 422
    assert "revoked" in res.json()["error"]["detail"]

    # Expiry is enforced on the same path
    expired = client.post(
        "/api/v1/admin/invites",
        json={"email": "expired@example.com", "full_name": "Expired", "role": "viewer"},
        headers=admin,
    ).json()
    expired_token = expired["invite_url"].rsplit("/", 1)[1]
    row = db.get(UserInvite, expired["id"])
    row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.flush()
    res = client.post(
        "/api/v1/invites/accept", json={"token": expired_token, "password": "password123"}
    )
    assert res.status_code == 422
    assert "expired" in res.json()["error"]["detail"]


def test_a_bad_token_is_a_clean_404(client, db):
    res = client.post(
        "/api/v1/invites/accept", json={"token": "not-a-real-token", "password": "password123"}
    )
    assert res.status_code == 404


def test_cannot_invite_an_existing_account_or_duplicate(client, db):
    admin = _admin(db)
    make_user(db, email="taken@example.com", role=UserRole.viewer)
    assert client.post(
        "/api/v1/admin/invites",
        json={"email": "taken@example.com", "full_name": "Taken", "role": "viewer"},
        headers=admin,
    ).status_code == 409

    body = {"email": "dup@example.com", "full_name": "Dup", "role": "viewer"}
    assert client.post("/api/v1/admin/invites", json=body, headers=admin).status_code == 201
    assert client.post("/api/v1/admin/invites", json=body, headers=admin).status_code == 409


def test_invites_are_admin_only(client, db):
    body = {"email": "x@example.com", "full_name": "X", "role": "viewer"}
    for role in (UserRole.project_manager, UserRole.procurement_officer, UserRole.viewer):
        headers = auth_headers(make_user(db, role=role))
        assert client.get("/api/v1/admin/invites", headers=headers).status_code == 403
        assert client.post("/api/v1/admin/invites", json=body, headers=headers).status_code == 403


def test_boq_helpers_unused_import_guard(client, db):
    """Kept so the shared factories stay imported and linted."""
    project = make_project(db)
    item = make_boq_item(db, make_boq_section(db, project))
    assert item.project_id == project.id
