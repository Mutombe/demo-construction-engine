"""Inventory turnover, carrying cost, dead stock and demand forecasting."""

from datetime import date, timedelta
from decimal import Decimal

from app.common.enums import UserRole
from tests.factories import auth_headers, make_project, make_supplier, make_user


def _proc(db):
    return auth_headers(make_user(db, role=UserRole.procurement_officer))


def _item(client, headers, code, reorder="0"):
    res = client.post(
        "/api/v1/stock-items",
        json={"code": code, "name": f"Item {code}", "unit": "bag", "reorder_level": reorder},
        headers=headers,
    )
    assert res.status_code == 201
    return res.json()


def _receive(client, headers, item_id, qty, cost="10.00", when=None):
    return client.post(
        f"/api/v1/stock-items/{item_id}/goods-in",
        json={
            "quantity": qty,
            "unit_cost": cost,
            **({"movement_date": str(when)} if when else {}),
        },
        headers=headers,
    )


def _issue(client, headers, item_id, project, qty, when=None):
    return client.post(
        f"/api/v1/stock-items/{item_id}/issue",
        json={
            "project_id": str(project.id),
            "quantity": qty,
            **({"movement_date": str(when)} if when else {}),
        },
        headers=headers,
    )


def _row(body, code):
    return next(r for r in body["rows"] if r["code"] == code)


def test_turnover_uses_a_real_average_not_the_closing_balance(client, db):
    """Opening stock is recoverable from the net movement, so the average is
    computed rather than assumed."""
    headers = _proc(db)
    project = make_project(db)
    item = _item(client, headers, "TURN-1")
    _receive(client, headers, item["id"], "100", cost="10.00")
    _issue(client, headers, item["id"], project, "60")

    body = client.get("/api/v1/stock-analytics?days=90", headers=headers).json()
    row = _row(body, "TURN-1")
    # Opening 0, closing 40 -> average 20 units = 200; issued 60 units = 600
    assert Decimal(row["stock_value"]) == Decimal("400.00")
    assert Decimal(row["average_stock_value"]) == Decimal("200.00")
    assert Decimal(row["issued_value"]) == Decimal("600.00")
    # 600/200 = 3 over 90 days, annualised x (365/90)
    assert Decimal(row["turnover_ratio"]) == Decimal("12.17")
    # 365 / (3 x 365/90) is exactly 30
    assert row["days_on_hand"] == 30


def test_items_that_never_moved_report_null_rather_than_zero(client, db):
    """A confident-looking 0.00 turnover would imply we measured something."""
    headers = _proc(db)
    item = _item(client, headers, "IDLE-1")
    _receive(client, headers, item["id"], "10")

    row = _row(client.get("/api/v1/stock-analytics", headers=headers).json(), "IDLE-1")
    assert row["turnover_ratio"] is None
    assert row["days_on_hand"] is None
    assert row["days_since_issue"] is None


def test_dead_stock_is_value_sitting_still(client, db):
    headers = _proc(db)
    project = make_project(db)
    long_ago = date.today() - timedelta(days=200)

    dead = _item(client, headers, "DEAD-1")
    _receive(client, headers, dead["id"], "50", when=long_ago)
    _issue(client, headers, dead["id"], project, "5", when=long_ago)

    moving = _item(client, headers, "LIVE-1")
    _receive(client, headers, moving["id"], "50")
    _issue(client, headers, moving["id"], project, "5")

    body = client.get("/api/v1/stock-analytics?dead_after_days=90", headers=headers).json()
    assert _row(body, "DEAD-1")["is_dead_stock"] is True
    assert _row(body, "LIVE-1")["is_dead_stock"] is False
    assert body["dead_stock_count"] == 1
    assert Decimal(body["dead_stock_value"]) == Decimal("450.00")  # 45 x 10


def test_an_empty_bin_is_not_dead_stock(client, db):
    """Dead stock means money tied up. Nothing on the shelf ties up nothing."""
    headers = _proc(db)
    project = make_project(db)
    item = _item(client, headers, "EMPTY-1")
    long_ago = date.today() - timedelta(days=200)
    _receive(client, headers, item["id"], "10", when=long_ago)
    _issue(client, headers, item["id"], project, "10", when=long_ago)

    row = _row(client.get("/api/v1/stock-analytics", headers=headers).json(), "EMPTY-1")
    assert Decimal(row["qty_on_hand"]) == Decimal("0.000")
    assert row["is_dead_stock"] is False


def test_carrying_cost_follows_the_rate_given(client, db):
    headers = _proc(db)
    item = _item(client, headers, "CARRY-1")
    _receive(client, headers, item["id"], "100", cost="10.00")

    quarter = client.get(
        "/api/v1/stock-analytics?carrying_rate=0.25", headers=headers
    ).json()
    tenth = client.get(
        "/api/v1/stock-analytics?carrying_rate=0.1", headers=headers
    ).json()
    # Average is 500 (opening 0, closing 1000)
    assert Decimal(_row(quarter, "CARRY-1")["annual_carrying_cost"]) == Decimal("125.00")
    assert Decimal(_row(tenth, "CARRY-1")["annual_carrying_cost"]) == Decimal("50.00")


def test_forecast_refuses_to_guess_from_too_little_history(client, db):
    headers = _proc(db)
    project = make_project(db)
    item = _item(client, headers, "THIN-1")
    _receive(client, headers, item["id"], "100")
    _issue(client, headers, item["id"], project, "5")  # a single issue

    row = _row(client.get("/api/v1/stock-forecast", headers=headers).json(), "THIN-1")
    assert row["has_enough_history"] is False
    assert row["daily_usage"] is None
    assert row["projected_stockout"] is None


def test_forecast_computes_usage_cover_and_stockout(client, db):
    headers = _proc(db)
    project = make_project(db)
    item = _item(client, headers, "FLOW-1")
    _receive(client, headers, item["id"], "1000")
    # 900 issued over a 90-day window = 10 a day
    for _ in range(3):
        _issue(client, headers, item["id"], project, "300")

    body = client.get("/api/v1/stock-forecast?days=90", headers=headers).json()
    row = _row(body, "FLOW-1")
    assert row["has_enough_history"] is True
    assert Decimal(row["daily_usage"]) == Decimal("10.000")
    assert Decimal(row["monthly_usage"]) == Decimal("300.000")
    # 100 left at 10/day
    assert row["days_of_cover"] == 10
    assert row["projected_stockout"] == str(date.today() + timedelta(days=10))


def test_reorder_point_covers_the_delivery_plus_a_buffer(client, db):
    headers = _proc(db)
    project = make_project(db)
    item = _item(client, headers, "POINT-1", reorder="5")
    _receive(client, headers, item["id"], "1000")
    for _ in range(3):
        _issue(client, headers, item["id"], project, "300")

    body = client.get(
        "/api/v1/stock-forecast?days=90&safety_days=7", headers=headers
    ).json()
    row = _row(body, "POINT-1")
    lead = body["lead_time_days"]
    # 10 a day x (lead time + 7 days of buffer)
    assert Decimal(row["suggested_reorder_point"]) == Decimal(10 * (lead + 7)).quantize(
        Decimal("0.001")
    )
    # The typed-in level of 5 is nowhere near enough, and we say so
    assert row["reorder_level_is_low"] is True
    assert row["needs_ordering"] is True


def test_lead_time_comes_from_deliveries_that_actually_happened(client, db):
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)

    # With no received orders we fall back to a stated default
    assert client.get("/api/v1/stock-forecast", headers=headers).json()["lead_time_days"] == 14

    po = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "items": [
                {"description": "Cement", "unit": "bag", "quantity": "10", "unit_price": "10"}
            ],
        },
        headers=headers,
    ).json()
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)
    client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        json={
            "destination": "project",
            "received_date": str(date.today() + timedelta(days=21)),
        },
        headers=headers,
    )
    assert client.get("/api/v1/stock-forecast", headers=headers).json()["lead_time_days"] == 21


def test_consumption_trend_buckets_issues_by_month(client, db):
    headers = _proc(db)
    project = make_project(db)
    item = _item(client, headers, "TREND-1")
    _receive(client, headers, item["id"], "500")
    _issue(client, headers, item["id"], project, "40")
    _issue(client, headers, item["id"], project, "20", when=date.today() - timedelta(days=40))

    trend = client.get(
        f"/api/v1/stock-items/{item['id']}/consumption?months=6", headers=headers
    ).json()
    assert len(trend["months"]) == 6
    assert Decimal(trend["total"]) == Decimal("60.000")
    # The current month is last in the series
    assert Decimal(trend["months"][-1]["quantity"]) == Decimal("40.000")


def test_analytics_totals_agree_with_the_rows(client, db):
    headers = _proc(db)
    project = make_project(db)
    for code, qty in (("SUM-1", "40"), ("SUM-2", "60")):
        item = _item(client, headers, code)
        _receive(client, headers, item["id"], qty, cost="10.00")
        _issue(client, headers, item["id"], project, "10")

    body = client.get("/api/v1/stock-analytics", headers=headers).json()
    row_total = sum(Decimal(r["stock_value"]) for r in body["rows"])
    assert Decimal(body["total_stock_value"]) == row_total
    issued_total = sum(Decimal(r["issued_value"]) for r in body["rows"])
    assert Decimal(body["total_issued_value"]) == issued_total
