"""Materials consumed vs what the measured work should have used."""

import csv
import io
from datetime import date
from decimal import Decimal

from app.common.enums import CostSource, UserRole
from tests.factories import (
    auth_headers,
    make_boq_item,
    make_boq_section,
    make_cost_entry,
    make_project,
    make_user,
)


def _pm(db):
    return auth_headers(make_user(db, role=UserRole.project_manager))


def _rows(client, headers, project_id):
    res = client.get(
        f"/api/v1/reports/material-reconciliation?project_id={project_id}&format=csv",
        headers=headers,
    )
    assert res.status_code == 200
    reader = csv.DictReader(io.StringIO(res.content.decode("utf-8-sig")))
    # Drop the TOTAL footer row the renderer appends
    return [row for row in reader if row.get("Item") and row["Item"] != "TOTAL"]


def _measure(client, headers, project, boq_item, qty):
    valuation = client.post(
        f"/api/v1/projects/{project.id}/valuations",
        json={"period_end": str(date.today()), "gross_valuation": "1"},
        headers=headers,
    ).json()
    client.put(
        f"/api/v1/valuations/{valuation['id']}/measurement",
        json={"lines": [{"boq_item_id": str(boq_item.id), "qty_to_date": str(qty)}]},
        headers=headers,
    )
    return valuation


def test_overconsumption_is_flagged(client, db):
    headers = _pm(db)
    project = make_project(db, contract_value=Decimal("1000000"))
    section = make_boq_section(db, project)
    # 100 m3 at 100 = 10,000 budget
    item = make_boq_item(
        db, section, description="Concrete C25", unit="m3",
        quantity=Decimal("100"), rate=Decimal("100"),
    )
    # Half the line is built, so 5,000 of material is justified...
    _measure(client, headers, project, item, "50")
    # ...but 8,000 of material was issued against it
    make_cost_entry(
        db, project, amount=Decimal("8000"), boq_item_id=item.id,
        source=CostSource.inventory_issue,
    )

    rows = _rows(client, headers, project.id)
    row = next(r for r in rows if r["Item"] == item.item_code)
    assert Decimal(row["Progress %"]) == Decimal("50.0")
    assert Decimal(row["Should have used"]) == Decimal("5000.00")
    assert Decimal(row["Actually used"]) == Decimal("8000.00")
    assert Decimal(row["Variance"]) == Decimal("3000.00")
    assert Decimal(row["Variance %"]) == Decimal("60.0")
    assert row["Flag"] == "OVER"


def test_consumption_in_line_with_progress_is_not_flagged(client, db):
    headers = _pm(db)
    project = make_project(db, contract_value=Decimal("1000000"))
    section = make_boq_section(db, project)
    item = make_boq_item(
        db, section, quantity=Decimal("100"), rate=Decimal("100")
    )
    _measure(client, headers, project, item, "40")
    make_cost_entry(
        db, project, amount=Decimal("4100"), boq_item_id=item.id,
        source=CostSource.purchase_order,
    )

    row = next(r for r in _rows(client, headers, project.id) if r["Item"] == item.item_code)
    assert Decimal(row["Variance"]) == Decimal("100.00")
    assert row["Flag"] == ""  # 2.5% over is normal wastage, not an alarm


def test_material_consumed_before_any_measurement_is_flagged_unmeasured(client, db):
    headers = _pm(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section, quantity=Decimal("100"), rate=Decimal("100"))
    make_cost_entry(
        db, project, amount=Decimal("2500"), boq_item_id=item.id,
        source=CostSource.inventory_issue,
    )

    row = next(r for r in _rows(client, headers, project.id) if r["Item"] == item.item_code)
    assert row["Flag"] == "UNMEASURED"
    assert Decimal(row["Actually used"]) == Decimal("2500.00")
    assert Decimal(row["Should have used"]) == Decimal("0.00")


def test_untouched_lines_are_omitted(client, db):
    headers = _pm(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    make_boq_item(db, section, item_code="IDLE-1")
    used = make_boq_item(db, section, item_code="USED-1")
    make_cost_entry(
        db, project, amount=Decimal("100"), boq_item_id=used.id,
        source=CostSource.inventory_issue,
    )

    codes = [r["Item"] for r in _rows(client, headers, project.id)]
    assert "USED-1" in codes
    assert "IDLE-1" not in codes  # not started is not a variance


def test_labour_and_expenses_are_not_material_consumption(client, db):
    headers = _pm(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section, quantity=Decimal("100"), rate=Decimal("100"))
    _measure(client, headers, project, item, "50")
    make_cost_entry(
        db, project, amount=Decimal("900"), boq_item_id=item.id,
        source=CostSource.payroll,
    )
    make_cost_entry(
        db, project, amount=Decimal("600"), boq_item_id=item.id,
        source=CostSource.inventory_issue,
    )

    row = next(r for r in _rows(client, headers, project.id) if r["Item"] == item.item_code)
    # Only the stock issue counts — payroll is not material
    assert Decimal(row["Actually used"]) == Decimal("600.00")


def test_xlsx_export_works(client, db):
    headers = _pm(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section)
    make_cost_entry(
        db, project, amount=Decimal("10"), boq_item_id=item.id,
        source=CostSource.inventory_issue,
    )
    res = client.get(
        f"/api/v1/reports/material-reconciliation?project_id={project.id}&format=xlsx",
        headers=headers,
    )
    assert res.status_code == 200
    assert res.content[:2] == b"PK"  # xlsx is a zip container
