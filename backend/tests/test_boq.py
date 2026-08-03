from decimal import Decimal

from app.common.enums import UserRole
from tests.factories import (
    auth_headers,
    make_boq_item,
    make_boq_section,
    make_cost_entry,
    make_project,
    make_user,
)


def test_amount_is_generated_by_db(client, db):
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section, quantity=Decimal("420"), rate=Decimal("8.50"))
    assert item.amount == Decimal("3570.00")


def test_item_crud_via_api(client, db):
    pm = make_user(db, role=UserRole.project_manager)
    headers = auth_headers(pm)
    project = make_project(db)
    section = make_boq_section(db, project, code="A", title="Substructure")

    res = client.post(
        f"/api/v1/boq/sections/{section.id}/items",
        json={
            "item_code": "A.1.1",
            "description": "Excavate foundation trenches n.e. 1.5m deep",
            "unit": "m3",
            "quantity": "420",
            "rate": "8.50",
            "cost_category": "labour",
        },
        headers=headers,
    )
    assert res.status_code == 201
    body = res.json()
    assert body["amount"] == "3570.00"

    # Rate change recomputes amount server-side
    res = client.patch(f"/api/v1/boq/items/{body['id']}", json={"rate": "10.00"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["amount"] == "4200.00"


def test_duplicate_item_code_in_section_conflict(client, db):
    pm = make_user(db, role=UserRole.project_manager)
    headers = auth_headers(pm)
    project = make_project(db)
    section = make_boq_section(db, project)
    payload = {"item_code": "X.1", "description": "d", "unit": "m", "quantity": "1", "rate": "1"}
    assert (
        client.post(
            f"/api/v1/boq/sections/{section.id}/items", json=payload, headers=headers
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/v1/boq/sections/{section.id}/items", json=payload, headers=headers
        ).status_code
        == 409
    )


def test_boq_tree_totals_exclude_omissions(client, db):
    viewer = make_user(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    make_boq_item(db, section, quantity=Decimal("10"), rate=Decimal("100"))  # 1000
    make_boq_item(
        db, section, quantity=Decimal("5"), rate=Decimal("100"), item_type="variation"
    )  # 500
    make_boq_item(
        db, section, quantity=Decimal("2"), rate=Decimal("100"), item_type="omission"
    )  # excluded

    res = client.get(f"/api/v1/projects/{project.id}/boq", headers=auth_headers(viewer))
    assert res.status_code == 200
    tree = res.json()
    assert Decimal(tree["grand_total"]) == Decimal("1500.00")
    assert Decimal(tree["sections"][0]["subtotal"]) == Decimal("1500.00")


def test_boq_summary_budget_vs_actual(client, db):
    viewer = make_user(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section, quantity=Decimal("10"), rate=Decimal("100"))  # 1000
    make_cost_entry(db, project, boq_item_id=item.id, amount=Decimal("400"))
    make_cost_entry(db, project, amount=Decimal("150"))  # unallocated

    res = client.get(f"/api/v1/projects/{project.id}/boq/summary", headers=auth_headers(viewer))
    assert res.status_code == 200
    summary = res.json()
    assert Decimal(summary["budget_total"]) == Decimal("1000.00")
    assert Decimal(summary["actual_total"]) == Decimal("550.00")
    assert Decimal(summary["unallocated_actual"]) == Decimal("150.00")
    assert len(summary["by_section"]) == 1
    assert Decimal(summary["by_section"][0]["actual"]) == Decimal("400.00")
