from decimal import Decimal

from app.common.enums import UserRole
from tests.factories import auth_headers, make_project, make_user


def _claim(client, headers, project):
    return client.post(
        f"/api/v1/projects/{project.id}/expenses",
        json={
            "category": "fuel",
            "expense_date": "2026-08-01",
            "amount": "50",
            "description": "Diesel",
        },
        headers=headers,
    ).json()


def test_expense_flow_emits_and_suppresses_self(client, db):
    pm_user = make_user(db, role=UserRole.project_manager)
    pm = auth_headers(pm_user)
    site_user = make_user(db, role=UserRole.site_manager)
    site = auth_headers(site_user)
    project = make_project(db)

    claim = _claim(client, site, project)

    # PM was notified of the submission; the claimant was not
    pm_list = client.get("/api/v1/notifications", headers=pm).json()
    assert any(n["type"] == "expense_submitted" for n in pm_list["items"])
    site_list = client.get("/api/v1/notifications", headers=site).json()
    assert not any(n["type"] == "expense_submitted" for n in site_list["items"])

    # approval notifies the claimant, not the approver
    client.post(f"/api/v1/expenses/{claim['id']}/approve", headers=pm)
    site_list = client.get("/api/v1/notifications", headers=site).json()
    assert any(n["type"] == "expense_approved" for n in site_list["items"])
    pm_list = client.get("/api/v1/notifications", headers=pm).json()
    assert not any(n["type"] == "expense_approved" for n in pm_list["items"])


def test_unread_count_read_and_read_all(client, db):
    pm_user = make_user(db, role=UserRole.project_manager)
    pm = auth_headers(pm_user)
    site = auth_headers(make_user(db, role=UserRole.site_manager))
    project = make_project(db)
    _claim(client, site, project)
    _claim(client, site, project)

    count = client.get("/api/v1/notifications/unread-count", headers=pm).json()["count"]
    assert count == 2

    first = client.get("/api/v1/notifications", headers=pm).json()["items"][0]
    marked = client.post(f"/api/v1/notifications/{first['id']}/read", headers=pm).json()
    assert marked["is_read"] is True
    assert client.get("/api/v1/notifications/unread-count", headers=pm).json()["count"] == 1

    client.post("/api/v1/notifications/read-all", headers=pm)
    assert client.get("/api/v1/notifications/unread-count", headers=pm).json()["count"] == 0

    unread_only = client.get("/api/v1/notifications?unread_only=true", headers=pm).json()
    assert unread_only["total"] == 0


def test_notifications_are_user_scoped(client, db):
    pm = auth_headers(make_user(db, role=UserRole.project_manager))
    other_pm = auth_headers(make_user(db, role=UserRole.project_manager))
    site = auth_headers(make_user(db, role=UserRole.site_manager))
    project = make_project(db)
    _claim(client, site, project)

    mine = client.get("/api/v1/notifications", headers=pm).json()["items"][0]
    # another user cannot mark my notification read
    res = client.post(f"/api/v1/notifications/{mine['id']}/read", headers=other_pm)
    assert res.status_code == 404


def test_valuation_and_payroll_notifications(client, db):
    from datetime import date, timedelta

    from tests.factories import make_timesheet, make_worker

    admin = auth_headers(make_user(db, role=UserRole.admin))
    pm_user = make_user(db, role=UserRole.project_manager)
    pm = auth_headers(pm_user)
    project = make_project(
        db,
        contract_value=Decimal("100000"),
        project_manager_id=pm_user.id,
    )

    # valuation issued by admin -> PM notified
    val = client.post(
        f"/api/v1/projects/{project.id}/valuations",
        json={"period_end": "2026-07-31", "gross_valuation": "10000"},
        headers=admin,
    ).json()
    client.post(f"/api/v1/valuations/{val['id']}/issue", json={}, headers=admin)
    pm_list = client.get("/api/v1/notifications", headers=pm).json()
    assert any(n["type"] == "valuation_issued" for n in pm_list["items"])

    # pay run approved by PM -> admin notified
    worker = make_worker(db)
    make_timesheet(db, worker, project, work_date=date.today())
    run = client.post(
        "/api/v1/pay-runs",
        json={
            "period_start": (date.today() - timedelta(days=6)).isoformat(),
            "period_end": date.today().isoformat(),
        },
        headers=pm,
    ).json()
    client.post(f"/api/v1/pay-runs/{run['id']}/approve", headers=pm)
    admin_list = client.get("/api/v1/notifications", headers=admin).json()
    assert any(n["type"] == "pay_run_approved" for n in admin_list["items"])
