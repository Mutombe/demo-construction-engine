"""Cash-flow forecast and the project photo timeline."""

import io
from datetime import date, timedelta
from decimal import Decimal

from app.common.enums import CostSource, UserRole
from tests.factories import (
    auth_headers,
    make_boq_item,
    make_boq_section,
    make_cost_entry,
    make_project,
    make_supplier,
    make_user,
)


def _pm(db):
    return auth_headers(make_user(db, role=UserRole.project_manager))


def _month(offset: int) -> str:
    today = date.today()
    month = today.month + offset
    year = today.year + (month - 1) // 12
    return f"{year:04d}-{((month - 1) % 12) + 1:02d}"


def test_issued_valuation_becomes_receivable_next_month(client, db):
    headers = _pm(db)
    project = make_project(db, contract_value=Decimal("100000"))
    valuation = client.post(
        f"/api/v1/projects/{project.id}/valuations",
        json={"period_end": str(date.today()), "gross_valuation": "40000"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/valuations/{valuation['id']}/issue", json={}, headers=headers)

    forecast = client.get(
        f"/api/v1/dashboard/cashflow-forecast?project_id={project.id}", headers=headers
    ).json()
    assert Decimal(forecast["opening_receivables"]) == Decimal("40000.00")
    next_month = next(m for m in forecast["months"] if m["month"] == _month(1))
    assert Decimal(next_month["inflow_receivable"]) == Decimal("40000.00")
    # Paid certificates are no longer receivable
    client.post(f"/api/v1/valuations/{valuation['id']}/pay", json={}, headers=headers)
    after = client.get(
        f"/api/v1/dashboard/cashflow-forecast?project_id={project.id}", headers=headers
    ).json()
    assert Decimal(after["opening_receivables"]) == Decimal("0")


def test_issued_pos_land_in_their_delivery_month(client, db):
    headers = _pm(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section)
    supplier = make_supplier(db)

    # Delivery expected two months out
    target = date.today() + timedelta(days=62)
    po = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "expected_delivery": str(target),
            "items": [
                {
                    "boq_item_id": str(item.id),
                    "description": "Steel",
                    "unit": "t",
                    "quantity": "10",
                    "unit_price": "500.00",
                }
            ],
        },
        headers=headers,
    ).json()

    def committed_in(month_key):
        forecast = client.get(
            f"/api/v1/dashboard/cashflow-forecast?project_id={project.id}", headers=headers
        ).json()
        row = next(m for m in forecast["months"] if m["month"] == month_key)
        return Decimal(row["outflow_committed"])

    # A draft is not a commitment
    assert committed_in(target.strftime("%Y-%m")) == Decimal("0")
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)
    assert committed_in(target.strftime("%Y-%m")) == Decimal("5000.00")


def test_overdue_po_is_pulled_into_the_current_month(client, db):
    headers = _pm(db)
    project = make_project(db)
    supplier = make_supplier(db)
    po = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "expected_delivery": str(date.today() - timedelta(days=40)),
            "items": [
                {"description": "Sand", "unit": "m3", "quantity": "10", "unit_price": "20.00"}
            ],
        },
        headers=headers,
    ).json()
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)

    forecast = client.get(
        f"/api/v1/dashboard/cashflow-forecast?project_id={project.id}", headers=headers
    ).json()
    current = forecast["months"][0]
    assert current["month"] == _month(0)
    # Money already due does not sit in the past — it is owed now
    assert Decimal(current["outflow_committed"]) == Decimal("200.00")


def test_payroll_run_rate_carries_forward(client, db):
    headers = _pm(db)
    project = make_project(db)
    # 3 months of ledger history -> a monthly run-rate
    for days_ago in (10, 40, 70):
        make_cost_entry(
            db,
            project,
            amount=Decimal("3000"),
            entry_date=date.today() - timedelta(days=days_ago),
            source=CostSource.payroll,
        )

    forecast = client.get(
        f"/api/v1/dashboard/cashflow-forecast?project_id={project.id}", headers=headers
    ).json()
    assert all(
        Decimal(m["outflow_payroll"]) == Decimal("3000.00") for m in forecast["months"]
    )


def test_forecast_totals_and_worst_month(client, db):
    headers = _pm(db)
    project = make_project(db, contract_value=Decimal("60000"))
    forecast = client.get(
        f"/api/v1/dashboard/cashflow-forecast?project_id={project.id}&months=4",
        headers=headers,
    ).json()

    assert len(forecast["months"]) == 4
    # Cumulative is a running total of net
    running = Decimal("0")
    for row in forecast["months"]:
        running += Decimal(row["net"])
        assert Decimal(row["cumulative"]) == running
    assert Decimal(forecast["closing_position"]) == running
    assert forecast["worst_month"] in [m["month"] for m in forecast["months"]]
    # Uncertified contract value shows up as forecast income
    assert Decimal(forecast["total_inflow"]) > Decimal("0")


def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 120, 40)).save(buf, "PNG")
    return buf.getvalue()


def test_photo_timeline_groups_by_day(client, db):
    headers = _pm(db)
    project = make_project(db)

    for index in range(3):
        res = client.post(
            "/api/v1/media",
            files={"file": (f"site-{index}.png", _png(), "image/png")},
            data={
                "entity_type": "project",
                "entity_id": str(project.id),
                "folder": "photos",
                "caption": f"Pour {index}",
            },
            headers=headers,
        )
        assert res.status_code == 201
    # A non-photo document must not appear in the timeline
    client.post(
        "/api/v1/media",
        files={"file": ("contract.txt", b"terms", "text/plain")},
        data={
            "entity_type": "project",
            "entity_id": str(project.id),
            "folder": "contracts",
        },
        headers=headers,
    )

    timeline = client.get(
        f"/api/v1/media/photo-timeline?entity_type=project&entity_id={project.id}",
        headers=headers,
    ).json()
    assert timeline["total_photos"] == 3
    assert len(timeline["days"]) == 1
    day = timeline["days"][0]
    assert day["day"] == str(date.today())
    assert {p["caption"] for p in day["photos"]} == {"Pour 0", "Pour 1", "Pour 2"}
    assert all(p["has_thumbnail"] for p in day["photos"])

    # Ordering is stable across calls: uploads inside one transaction share a
    # created_at, so the id tiebreak is what stops the sequence shuffling.
    again = client.get(
        f"/api/v1/media/photo-timeline?entity_type=project&entity_id={project.id}",
        headers=headers,
    ).json()
    assert [p["id"] for p in again["days"][0]["photos"]] == [
        p["id"] for p in day["photos"]
    ]


def test_photo_timeline_empty_and_unknown_entity(client, db):
    headers = _pm(db)
    project = make_project(db)
    empty = client.get(
        f"/api/v1/media/photo-timeline?entity_type=project&entity_id={project.id}",
        headers=headers,
    ).json()
    assert empty["total_photos"] == 0
    assert empty["days"] == []
    assert empty["first_photo"] is None

    bad = client.get(
        f"/api/v1/media/photo-timeline?entity_type=user&entity_id={project.id}",
        headers=headers,
    )
    assert bad.status_code == 422
