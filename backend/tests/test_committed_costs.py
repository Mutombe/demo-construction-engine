"""Issued-but-unreceived purchase orders must show as commitments.

The gap this closes: a project reads "under budget" from actuals alone while
orders already placed have overrun it.
"""

from decimal import Decimal

from app.common.enums import UserRole
from tests.factories import (
    auth_headers,
    make_boq_item,
    make_boq_section,
    make_project,
    make_supplier,
    make_user,
)


def _pm(db):
    return auth_headers(make_user(db, role=UserRole.project_manager))


def _po(client, headers, project, boq_item, supplier, *, qty="10", price="100.00"):
    res = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "items": [
                {
                    "boq_item_id": str(boq_item.id),
                    "description": boq_item.description,
                    "unit": boq_item.unit,
                    "quantity": qty,
                    "unit_price": price,
                }
            ],
        },
        headers=headers,
    )
    assert res.status_code == 201
    return res.json()


def _setup(db):
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(
        db, section, quantity=Decimal("100"), rate=Decimal("50")
    )  # 5,000 budget
    return project, section, item


def test_only_issued_pos_count_as_committed(client, db):
    headers = _pm(db)
    project, section, item = _setup(db)
    supplier = make_supplier(db)
    po = _po(client, headers, project, item, supplier)

    def summary():
        return client.get(f"/api/v1/projects/{project.id}/boq/summary", headers=headers).json()

    # Draft: nothing has been sent to the supplier, so nothing is committed
    assert Decimal(summary()["committed_total"]) == Decimal("0")

    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)
    assert Decimal(summary()["committed_total"]) == Decimal("1000.00")

    # Receiving turns the commitment into an actual — it must not be counted twice
    client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        json={"destination": "project"},
        headers=headers,
    )
    after = summary()
    assert Decimal(after["committed_total"]) == Decimal("0")
    assert Decimal(after["actual_total"]) == Decimal("1000.00")


def test_cancelled_po_is_not_committed(client, db):
    headers = _pm(db)
    project, _, item = _setup(db)
    po = _po(client, headers, project, item, make_supplier(db))
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)
    client.post(f"/api/v1/purchase-orders/{po['id']}/cancel", headers=headers)

    summary = client.get(
        f"/api/v1/projects/{project.id}/boq/summary", headers=headers
    ).json()
    assert Decimal(summary["committed_total"]) == Decimal("0")


def test_committed_appears_per_boq_item_section_and_category(client, db):
    headers = _pm(db)
    project, section, item = _setup(db)
    po = _po(client, headers, project, item, make_supplier(db), qty="20", price="50.00")
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)

    tree = client.get(f"/api/v1/projects/{project.id}/boq", headers=headers).json()
    line = tree["sections"][0]["items"][0]
    assert Decimal(line["committed_total"]) == Decimal("1000.00")
    assert Decimal(line["actual_total"]) == Decimal("0")

    summary = client.get(
        f"/api/v1/projects/{project.id}/boq/summary", headers=headers
    ).json()
    by_section = {s["section_id"]: s for s in summary["by_section"]}
    assert Decimal(by_section[str(section.id)]["committed"]) == Decimal("1000.00")
    by_category = {c["cost_category"]: c for c in summary["by_category"]}
    assert Decimal(by_category["material"]["committed"]) == Decimal("1000.00")


def test_project_summary_exposure_catches_overrun_actuals_miss(client, db):
    headers = _pm(db)
    project, _, item = _setup(db)  # 5,000 budget
    # Spend 2,000 and commit another 4,000: actuals say 40%, exposure says 120%
    from tests.factories import make_cost_entry

    make_cost_entry(db, project, amount=Decimal("2000"), boq_item_id=item.id)
    po = _po(client, headers, project, item, make_supplier(db), qty="80", price="50.00")
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)

    summary = client.get(f"/api/v1/projects/{project.id}/summary", headers=headers).json()
    assert Decimal(summary["actual_total"]) == Decimal("2000.00")
    assert Decimal(summary["committed_total"]) == Decimal("4000.00")
    assert summary["budget_variance_pct"] == -60.0  # actuals alone look healthy
    assert summary["exposure_pct"] == 120.0  # commitments reveal the overrun


def test_dashboard_overview_carries_commitments(client, db):
    headers = _pm(db)
    project, _, item = _setup(db)
    po = _po(client, headers, project, item, make_supplier(db))
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)

    overview = client.get("/api/v1/dashboard/overview", headers=headers).json()
    assert Decimal(overview["portfolio_committed"]) == Decimal("1000.00")
    health = next(p for p in overview["projects"] if p["id"] == str(project.id))
    assert Decimal(health["committed_total"]) == Decimal("1000.00")
    assert health["exposure_pct"] == 20.0  # 1,000 of 5,000 budget


def test_store_bound_po_still_commits_project_budget(client, db):
    """A store receipt posts no cost entry, but the money is still committed
    while the order is outstanding."""
    headers = _pm(db)
    project, _, item = _setup(db)
    po = _po(client, headers, project, item, make_supplier(db))
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)

    summary = client.get(
        f"/api/v1/projects/{project.id}/boq/summary", headers=headers
    ).json()
    assert Decimal(summary["committed_total"]) == Decimal("1000.00")
