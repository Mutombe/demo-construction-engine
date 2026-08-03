from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.common.enums import CostSource, PayBasis, UserRole
from app.modules.costs.models import CostEntry
from tests.factories import auth_headers, make_project, make_timesheet, make_user, make_worker

TODAY = date.today()


def _pm(db):
    return auth_headers(make_user(db, role=UserRole.project_manager))


def _site(db):
    return auth_headers(make_user(db, role=UserRole.site_manager))


def _run(client, headers, start=None, end=None):
    return client.post(
        "/api/v1/pay-runs",
        json={
            "period_start": (start or TODAY - timedelta(days=6)).isoformat(),
            "period_end": (end or TODAY).isoformat(),
        },
        headers=headers,
    )


# --- Workers ----------------------------------------------------------------


def test_worker_crud_and_rbac(client, db):
    pm = _pm(db)
    res = client.post(
        "/api/v1/workers",
        json={"full_name": "T. Banda", "trade": "Bricklayer", "pay_basis": "daily", "rate": "35"},
        headers=pm,
    )
    assert res.status_code == 201
    worker = res.json()

    item = client.post(
        f"/api/v1/workers/{worker['id']}/pay-items",
        json={"kind": "allowance", "label": "Transport", "amount": "10"},
        headers=pm,
    )
    assert item.status_code == 201

    patched = client.patch(
        f"/api/v1/workers/{worker['id']}", json={"rate": "38"}, headers=pm
    ).json()
    assert Decimal(patched["rate"]) == Decimal("38")
    assert len(patched["pay_items"]) == 1

    viewer = auth_headers(make_user(db, role=UserRole.viewer))
    assert client.get("/api/v1/workers", headers=viewer).status_code == 403
    assert client.get("/api/v1/pay-runs", headers=viewer).status_code == 403
    # site managers can read workers (needed for day entry) but not create them
    site = _site(db)
    assert client.get("/api/v1/workers", headers=site).status_code == 200
    assert (
        client.post(
            "/api/v1/workers",
            json={"full_name": "X", "trade": "Y", "rate": "5"},
            headers=site,
        ).status_code
        == 403
    )


# --- Timesheets -------------------------------------------------------------


def test_timesheet_unique_and_bulk(client, db):
    site = _site(db)
    project = make_project(db)
    w1 = make_worker(db)
    w2 = make_worker(db)

    res = client.post(
        "/api/v1/timesheets",
        json={
            "worker_id": str(w1.id),
            "project_id": str(project.id),
            "work_date": TODAY.isoformat(),
            "quantity": "1",
        },
        headers=site,
    )
    assert res.status_code == 201
    dup = client.post(
        "/api/v1/timesheets",
        json={
            "worker_id": str(w1.id),
            "project_id": str(project.id),
            "work_date": TODAY.isoformat(),
            "quantity": "1",
        },
        headers=site,
    )
    assert dup.status_code == 409

    # bulk upserts w1 and creates w2; zero clears nothing for w2 later
    bulk = client.post(
        "/api/v1/timesheets/bulk",
        json={
            "project_id": str(project.id),
            "work_date": TODAY.isoformat(),
            "entries": [
                {"worker_id": str(w1.id), "quantity": "0.5", "overtime_quantity": "0.5"},
                {"worker_id": str(w2.id), "quantity": "1"},
            ],
        },
        headers=site,
    )
    assert bulk.status_code == 201
    listed = client.get(
        f"/api/v1/timesheets?project_id={project.id}", headers=site
    ).json()
    assert listed["total"] == 2
    q_by_worker = {row["worker_id"]: row["quantity"] for row in listed["items"]}
    assert Decimal(q_by_worker[str(w1.id)]) == Decimal("0.5")

    # zero-quantity bulk entry deletes the unpaid row
    client.post(
        "/api/v1/timesheets/bulk",
        json={
            "project_id": str(project.id),
            "work_date": TODAY.isoformat(),
            "entries": [{"worker_id": str(w2.id), "quantity": "0"}],
        },
        headers=site,
    )
    listed = client.get(f"/api/v1/timesheets?project_id={project.id}", headers=site).json()
    assert listed["total"] == 1


# --- Pay run math -----------------------------------------------------------


def test_pay_run_math_hourly_daily_and_items(client, db):
    pm = _pm(db)
    project = make_project(db)

    hourly = make_worker(db, pay_basis=PayBasis.hourly, rate=Decimal("5"))
    daily = make_worker(db, pay_basis=PayBasis.daily, rate=Decimal("40"))
    client.post(
        f"/api/v1/workers/{daily.id}/pay-items",
        json={"kind": "allowance", "label": "Transport", "amount": "15"},
        headers=pm,
    )
    client.post(
        f"/api/v1/workers/{daily.id}/pay-items",
        json={"kind": "deduction", "label": "Advance", "amount": "20"},
        headers=pm,
    )

    # hourly: 8h + 2h OT @5 => 40 + 15 = 55
    make_timesheet(db, hourly, project, quantity=Decimal("8"), overtime_quantity=Decimal("2"))
    # daily: 5 days @40 = 200 + 15 allowance = 215 gross, net 195
    for offset in range(5):
        make_timesheet(db, daily, project, work_date=TODAY - timedelta(days=offset))

    run = _run(client, pm)
    assert run.status_code == 201
    body = run.json()
    lines = {line["worker_id"]: line for line in body["lines"]}
    h = lines[str(hourly.id)]
    assert Decimal(h["base_pay"]) == Decimal("40")
    assert Decimal(h["overtime_pay"]) == Decimal("15")
    assert Decimal(h["gross_pay"]) == Decimal("55")
    assert Decimal(h["net_pay"]) == Decimal("55")
    d = lines[str(daily.id)]
    assert Decimal(d["base_pay"]) == Decimal("200")
    assert Decimal(d["allowance_total"]) == Decimal("15")
    assert Decimal(d["deduction_total"]) == Decimal("20")
    assert Decimal(d["gross_pay"]) == Decimal("215")
    assert Decimal(d["net_pay"]) == Decimal("195")
    assert Decimal(body["gross_total"]) == Decimal("270")
    assert Decimal(body["net_total"]) == Decimal("250")


def test_multi_project_allocation_sums_to_gross(client, db):
    pm = _pm(db)
    p1 = make_project(db)
    p2 = make_project(db)
    worker = make_worker(db, pay_basis=PayBasis.daily, rate=Decimal("33.33"))
    client.post(
        f"/api/v1/workers/{worker.id}/pay-items",
        json={"kind": "allowance", "label": "Phone", "amount": "7.77"},
        headers=pm,
    )
    make_timesheet(db, worker, p1, work_date=TODAY - timedelta(days=1))
    make_timesheet(db, worker, p1, work_date=TODAY - timedelta(days=2))
    make_timesheet(db, worker, p2, work_date=TODAY)

    body = _run(client, pm).json()
    line = body["lines"][0]
    alloc_total = sum(Decimal(a["amount"]) for a in line["project_allocation"])
    assert alloc_total == Decimal(line["gross_pay"])
    assert {a["project_id"] for a in line["project_allocation"]} == {str(p1.id), str(p2.id)}


# --- Approval ---------------------------------------------------------------


def test_approve_posts_costs_and_locks_timesheets(client, db):
    pm = _pm(db)
    p1 = make_project(db)
    p2 = make_project(db)
    worker = make_worker(db, rate=Decimal("50"))
    s1 = make_timesheet(db, worker, p1, work_date=TODAY - timedelta(days=1))
    s2 = make_timesheet(db, worker, p2, work_date=TODAY)

    run = _run(client, pm).json()
    res = client.post(f"/api/v1/pay-runs/{run['id']}/approve", headers=pm)
    assert res.status_code == 200
    assert res.json()["status"] == "approved"

    entries = list(
        db.scalars(select(CostEntry).where(CostEntry.reference == run["doc_number"]))
    )
    assert len(entries) == 2
    assert all(e.source == CostSource.payroll for e in entries)
    assert sum(e.amount for e in entries) == Decimal("100")
    assert {e.project_id for e in entries} == {p1.id, p2.id}

    db.refresh(s1)
    db.refresh(s2)
    assert str(s1.pay_run_id) == run["id"]
    assert str(s2.pay_run_id) == run["id"]

    # locked timesheet can't change; re-approve 409; approved run can't be deleted
    assert (
        client.patch(
            f"/api/v1/timesheets/{s1.id}", json={"quantity": "2"}, headers=pm
        ).status_code
        == 409
    )
    assert client.post(f"/api/v1/pay-runs/{run['id']}/approve", headers=pm).status_code == 409
    assert client.delete(f"/api/v1/pay-runs/{run['id']}", headers=pm).status_code == 409

    # a second run over the same period finds nothing to pay
    empty = _run(client, pm)
    assert empty.status_code == 409  # overlapping approved period


def test_pay_run_guards(client, db):
    pm = _pm(db)
    project = make_project(db)
    worker = make_worker(db)
    make_timesheet(db, worker, project)

    first = _run(client, pm)
    assert first.status_code == 201
    # only one draft at a time
    assert _run(client, pm).status_code == 409
    # regenerate picks up new timesheets
    other = make_worker(db)
    make_timesheet(db, other, project)
    regen = client.post(f"/api/v1/pay-runs/{first.json()['id']}/regenerate", headers=pm)
    assert len(regen.json()["lines"]) == 2
    # delete the draft, then approve on an empty period fails validation
    assert client.delete(f"/api/v1/pay-runs/{first.json()['id']}", headers=pm).status_code == 204
    far_future = _run(
        client, pm, start=TODAY + timedelta(days=200), end=TODAY + timedelta(days=206)
    )
    assert far_future.status_code == 201
    approve = client.post(f"/api/v1/pay-runs/{far_future.json()['id']}/approve", headers=pm)
    assert approve.status_code == 422
