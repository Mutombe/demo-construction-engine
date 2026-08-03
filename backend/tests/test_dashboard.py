from datetime import date, timedelta
from decimal import Decimal

from app.common.enums import ProjectStatus
from tests.factories import (
    auth_headers,
    make_boq_item,
    make_boq_section,
    make_cost_entry,
    make_project,
    make_task,
    make_user,
)


def test_overview_handles_empty_database(client, db):
    user = make_user(db)
    res = client.get("/api/v1/dashboard/overview", headers=auth_headers(user))
    assert res.status_code == 200
    body = res.json()
    assert body["total_projects"] == 0
    assert body["projects"] == []


def test_overview_project_with_no_boq_or_tasks(client, db):
    """Div-by-zero guard: a project with no budget must report null used pct."""
    user = make_user(db)
    make_project(db, status=ProjectStatus.active)
    res = client.get("/api/v1/dashboard/overview", headers=auth_headers(user))
    assert res.status_code == 200
    project = res.json()["projects"][0]
    assert project["budget_used_pct"] is None
    assert project["progress_pct"] == 0.0


def test_overview_budget_health(client, db):
    user = make_user(db)
    project = make_project(db, status=ProjectStatus.active)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section, quantity=Decimal("10"), rate=Decimal("100"))  # 1000
    make_cost_entry(db, project, boq_item_id=item.id, amount=Decimal("1150"))

    res = client.get("/api/v1/dashboard/overview", headers=auth_headers(user))
    p = res.json()["projects"][0]
    assert p["budget_used_pct"] == 115.0


def test_deadlines_and_overdue_flags(client, db):
    user = make_user(db)
    project = make_project(db, status=ProjectStatus.active)
    make_task(db, project, name="Late task", planned_end=date.today() - timedelta(days=3))
    make_task(db, project, name="Soon task", planned_end=date.today() + timedelta(days=5))
    make_task(db, project, name="Far task", planned_end=date.today() + timedelta(days=200))

    res = client.get("/api/v1/dashboard/deadlines?days=30", headers=auth_headers(user))
    assert res.status_code == 200
    items = res.json()
    names = [i["task_name"] for i in items]
    assert "Late task" in names and "Soon task" in names and "Far task" not in names
    late = next(i for i in items if i["task_name"] == "Late task")
    assert late["is_overdue"] is True


def test_budget_alerts(client, db):
    user = make_user(db)
    project = make_project(db, status=ProjectStatus.active, name="Overrun Project")
    section = make_boq_section(db, project)
    item = make_boq_item(db, section, quantity=Decimal("10"), rate=Decimal("100"))  # 1000
    make_cost_entry(db, project, boq_item_id=item.id, amount=Decimal("950"))

    res = client.get("/api/v1/dashboard/budget-alerts?threshold_pct=90", headers=auth_headers(user))
    assert res.status_code == 200
    alerts = res.json()
    scopes = {a["scope"] for a in alerts}
    assert "project" in scopes and "boq_item" in scopes


def test_project_summary_endpoint(client, db):
    user = make_user(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    make_boq_item(db, section, quantity=Decimal("10"), rate=Decimal("100"))
    make_task(db, project, progress_pct=50)
    make_cost_entry(db, project, amount=Decimal("200"))

    res = client.get(f"/api/v1/projects/{project.id}/summary", headers=auth_headers(user))
    assert res.status_code == 200
    body = res.json()
    assert body["progress_pct"] == 50.0
    assert Decimal(body["budget_total"]) == Decimal("1000.00")
    assert Decimal(body["actual_total"]) == Decimal("200.00")
    assert body["budget_variance_pct"] == -80.0


def test_financial_trend_buckets_and_totals(client, db):
    from app.common.enums import UserRole

    pm = auth_headers(make_user(db, role=UserRole.project_manager))
    project = make_project(db, contract_value=Decimal("500000"))
    make_cost_entry(db, project, amount=Decimal("1200"), entry_date=date.today())

    val = client.post(
        f"/api/v1/projects/{project.id}/valuations",
        json={"period_end": str(date.today()), "gross_valuation": "50000"},
        headers=pm,
    ).json()
    client.post(
        f"/api/v1/valuations/{val['id']}/issue",
        json={"issued_date": str(date.today())},
        headers=pm,
    )

    res = client.get("/api/v1/dashboard/financial-trend?months=3", headers=pm)
    assert res.status_code == 200
    body = res.json()
    assert len(body["months"]) == 3
    current = body["months"][-1]
    assert current["month"] == date.today().strftime("%Y-%m")
    assert Decimal(current["cost"]) == Decimal("1200")
    assert Decimal(current["certified_net"]) == Decimal("50000.00")
    assert Decimal(body["totals"]["portfolio_invoiced"]) == Decimal("50000.00")
    assert Decimal(body["totals"]["portfolio_outstanding"]) == Decimal("50000.00")
    assert Decimal(body["totals"]["portfolio_paid"]) == Decimal("0")

    # project filter excludes other projects' costs
    other = make_project(db)
    make_cost_entry(db, other, amount=Decimal("999"), entry_date=date.today())
    scoped = client.get(
        f"/api/v1/dashboard/financial-trend?months=3&project_id={project.id}", headers=pm
    ).json()
    assert Decimal(scoped["months"][-1]["cost"]) == Decimal("1200")
