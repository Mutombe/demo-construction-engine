"""Batch and serial tracking: lots, expiry, FEFO issuing and recall traces."""

from datetime import date, timedelta
from decimal import Decimal

from app.common.enums import UserRole
from tests.factories import auth_headers, make_project, make_user


def _proc(db):
    return auth_headers(make_user(db, role=UserRole.procurement_officer))


def _item(client, headers, code="CEM-425", mode="batch", **kw):
    res = client.post(
        "/api/v1/stock-items",
        json={
            "code": code,
            "name": f"Item {code}",
            "unit": "bag",
            "tracking_mode": mode,
            **kw,
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


def _receive(client, headers, item_id, qty, batch=None, expiry=None, cost="10.00"):
    body = {"quantity": qty, "unit_cost": cost}
    if batch:
        body["batch_number"] = batch
    if expiry:
        body["expiry_date"] = expiry
    return client.post(
        f"/api/v1/stock-items/{item_id}/goods-in", json=body, headers=headers
    )


def test_untracked_items_are_completely_unaffected(client, db):
    """The default must behave exactly as inventory did before batches."""
    headers = _proc(db)
    item = _item(client, headers, "PLAIN-1", mode="none")
    assert _receive(client, headers, item["id"], "50").status_code == 200

    assert client.get("/api/v1/stock-batches", headers=headers).json() == []
    project = make_project(db)
    res = client.post(
        f"/api/v1/stock-items/{item['id']}/issue",
        json={"project_id": str(project.id), "quantity": "10"},
        headers=headers,
    )
    assert res.status_code == 200
    assert Decimal(res.json()["qty_on_hand"]) == Decimal("40.000")


def test_tracked_receipt_requires_a_batch_number(client, db):
    headers = _proc(db)
    item = _item(client, headers)
    res = _receive(client, headers, item["id"], "50")
    assert res.status_code == 422
    assert "batch number is required" in res.json()["error"]["detail"]


def test_receiving_creates_a_lot_and_accumulates_into_it(client, db):
    headers = _proc(db)
    item = _item(client, headers)
    expiry = str(date.today() + timedelta(days=90))
    _receive(client, headers, item["id"], "100", batch="LOT-A", expiry=expiry)
    _receive(client, headers, item["id"], "50", batch="LOT-A", expiry=expiry)

    batches = client.get(
        f"/api/v1/stock-batches?item_id={item['id']}", headers=headers
    ).json()
    assert len(batches) == 1
    assert Decimal(batches[0]["quantity"]) == Decimal("150.000")
    assert batches[0]["batch_number"] == "LOT-A"
    assert batches[0]["days_to_expiry"] == 90


def test_same_lot_cannot_carry_two_expiry_dates(client, db):
    headers = _proc(db)
    item = _item(client, headers)
    _receive(
        client, headers, item["id"], "10", batch="LOT-A",
        expiry=str(date.today() + timedelta(days=30)),
    )
    res = _receive(
        client, headers, item["id"], "10", batch="LOT-A",
        expiry=str(date.today() + timedelta(days=60)),
    )
    assert res.status_code == 422
    assert "already recorded with expiry" in res.json()["error"]["detail"]


def test_issue_takes_the_earliest_expiry_first(client, db):
    """FEFO, not FIFO: what matters is what goes off soonest."""
    headers = _proc(db)
    project = make_project(db)
    item = _item(client, headers)
    # Received in this order, but LATE expires after EARLY
    _receive(
        client, headers, item["id"], "40", batch="LATE",
        expiry=str(date.today() + timedelta(days=90)),
    )
    _receive(
        client, headers, item["id"], "30", batch="EARLY",
        expiry=str(date.today() + timedelta(days=10)),
    )

    client.post(
        f"/api/v1/stock-items/{item['id']}/issue",
        json={"project_id": str(project.id), "quantity": "25"},
        headers=headers,
    )
    remaining = {
        b["batch_number"]: Decimal(b["quantity"])
        for b in client.get(
            f"/api/v1/stock-batches?item_id={item['id']}", headers=headers
        ).json()
    }
    # The soon-to-expire lot was drawn down; the later one is untouched
    assert remaining == {"EARLY": Decimal("5.000"), "LATE": Decimal("40.000")}


def test_issue_spans_lots_when_one_cannot_cover_it(client, db):
    headers = _proc(db)
    project = make_project(db)
    item = _item(client, headers)
    _receive(
        client, headers, item["id"], "20", batch="EARLY",
        expiry=str(date.today() + timedelta(days=5)),
    )
    _receive(
        client, headers, item["id"], "50", batch="LATE",
        expiry=str(date.today() + timedelta(days=50)),
    )

    client.post(
        f"/api/v1/stock-items/{item['id']}/issue",
        json={"project_id": str(project.id), "quantity": "35"},
        headers=headers,
    )
    remaining = {
        b["batch_number"]: Decimal(b["quantity"])
        for b in client.get(
            f"/api/v1/stock-batches?item_id={item['id']}&include_empty=true",
            headers=headers,
        ).json()
    }
    assert remaining == {"EARLY": Decimal("0.000"), "LATE": Decimal("35.000")}
    # One ledger row per lot, so each row's quantity is true to one batch
    movements = client.get(
        f"/api/v1/stock-items/{item['id']}/movements", headers=headers
    ).json()["items"]
    issues = [m for m in movements if m["movement_type"] == "issue"]
    assert len(issues) == 2
    assert sum(abs(Decimal(m["quantity"])) for m in issues) == Decimal("35.000")


def test_undated_lots_are_used_after_dated_ones(client, db):
    headers = _proc(db)
    project = make_project(db)
    item = _item(client, headers)
    _receive(client, headers, item["id"], "20", batch="NO-DATE")
    _receive(
        client, headers, item["id"], "20", batch="DATED",
        expiry=str(date.today() + timedelta(days=200)),
    )

    client.post(
        f"/api/v1/stock-items/{item['id']}/issue",
        json={"project_id": str(project.id), "quantity": "20"},
        headers=headers,
    )
    remaining = {
        b["batch_number"]: Decimal(b["quantity"])
        for b in client.get(
            f"/api/v1/stock-batches?item_id={item['id']}&include_empty=true",
            headers=headers,
        ).json()
    }
    # Anything with a date is more urgent than anything without one
    assert remaining == {"DATED": Decimal("0.000"), "NO-DATE": Decimal("20.000")}


def test_a_specific_lot_can_be_forced(client, db):
    headers = _proc(db)
    project = make_project(db)
    item = _item(client, headers)
    _receive(
        client, headers, item["id"], "10", batch="EARLY",
        expiry=str(date.today() + timedelta(days=5)),
    )
    _receive(
        client, headers, item["id"], "10", batch="LATE",
        expiry=str(date.today() + timedelta(days=90)),
    )
    late = next(
        b
        for b in client.get(
            f"/api/v1/stock-batches?item_id={item['id']}", headers=headers
        ).json()
        if b["batch_number"] == "LATE"
    )

    client.post(
        f"/api/v1/stock-items/{item['id']}/issue",
        json={"project_id": str(project.id), "quantity": "10", "batch_id": late["id"]},
        headers=headers,
    )
    remaining = {
        b["batch_number"]: Decimal(b["quantity"])
        for b in client.get(
            f"/api/v1/stock-batches?item_id={item['id']}&include_empty=true",
            headers=headers,
        ).json()
    }
    assert remaining == {"EARLY": Decimal("10.000"), "LATE": Decimal("0.000")}


def test_cannot_issue_more_than_the_lots_hold(client, db):
    headers = _proc(db)
    project = make_project(db)
    item = _item(client, headers)
    _receive(client, headers, item["id"], "10", batch="LOT-A")

    res = client.post(
        f"/api/v1/stock-items/{item['id']}/issue",
        json={"project_id": str(project.id), "quantity": "50"},
        headers=headers,
    )
    assert res.status_code == 409
    # Nothing partially consumed
    batches = client.get(
        f"/api/v1/stock-batches?item_id={item['id']}", headers=headers
    ).json()
    assert Decimal(batches[0]["quantity"]) == Decimal("10.000")


def test_expiry_report_separates_expired_from_expiring(client, db):
    headers = _proc(db)
    item = _item(client, headers, expiry_warning_days=30)
    _receive(
        client, headers, item["id"], "10", batch="GONE",
        expiry=str(date.today() - timedelta(days=2)),
    )
    _receive(
        client, headers, item["id"], "20", batch="SOON",
        expiry=str(date.today() + timedelta(days=10)),
    )
    _receive(
        client, headers, item["id"], "30", batch="FINE",
        expiry=str(date.today() + timedelta(days=200)),
    )

    report = client.get("/api/v1/stock-batches/expiring", headers=headers).json()
    assert [b["batch_number"] for b in report["expired"]] == ["GONE"]
    assert [b["batch_number"] for b in report["expiring_soon"]] == ["SOON"]
    assert Decimal(report["expired_value"]) == Decimal("100.00")
    assert Decimal(report["expiring_value"]) == Decimal("200.00")


def test_fully_used_expired_lots_drop_off_the_report(client, db):
    """An expired lot with nothing left is history, not an action."""
    headers = _proc(db)
    project = make_project(db)
    item = _item(client, headers)
    _receive(
        client, headers, item["id"], "10", batch="GONE",
        expiry=str(date.today() - timedelta(days=1)),
    )
    assert len(client.get("/api/v1/stock-batches/expiring", headers=headers).json()["expired"]) == 1

    client.post(
        f"/api/v1/stock-items/{item['id']}/issue",
        json={"project_id": str(project.id), "quantity": "10"},
        headers=headers,
    )
    assert client.get("/api/v1/stock-batches/expiring", headers=headers).json()["expired"] == []


def test_recall_trace_finds_every_project_a_lot_reached(client, db):
    headers = _proc(db)
    alpha = make_project(db, name="Alpha Tower")
    beta = make_project(db, name="Beta Bridge")
    item = _item(client, headers)
    _receive(client, headers, item["id"], "100", batch="SUSPECT-1")

    for project, qty in ((alpha, "30"), (beta, "20")):
        client.post(
            f"/api/v1/stock-items/{item['id']}/issue",
            json={"project_id": str(project.id), "quantity": qty},
            headers=headers,
        )

    trace = client.get(
        "/api/v1/stock-batches/recall/SUSPECT-1", headers=headers
    ).json()
    assert trace["batch_number"] == "SUSPECT-1"
    assert Decimal(trace["remaining_quantity"]) == Decimal("50.000")
    assert Decimal(trace["issued_quantity"]) == Decimal("50.000")
    assert {u["project_name"] for u in trace["usages"]} == {"Alpha Tower", "Beta Bridge"}


def test_recall_of_an_unknown_lot_is_a_clean_404(client, db):
    assert (
        client.get("/api/v1/stock-batches/recall/NOPE", headers=_proc(db)).status_code
        == 404
    )


def test_serial_items_are_received_one_at_a_time(client, db):
    headers = _proc(db)
    item = _item(client, headers, "TOOL-1", mode="serial")

    assert _receive(client, headers, item["id"], "3", batch="SN-001").status_code == 422
    assert _receive(client, headers, item["id"], "1", batch="SN-001").status_code == 200
    assert _receive(client, headers, item["id"], "1", batch="SN-002").status_code == 200

    serials = {
        b["batch_number"]
        for b in client.get(
            f"/api/v1/stock-batches?item_id={item['id']}", headers=headers
        ).json()
    }
    assert serials == {"SN-001", "SN-002"}


def test_batches_are_held_per_location(client, db):
    headers = _proc(db)
    item = _item(client, headers)
    yard = client.post(
        "/api/v1/stock-locations",
        json={"code": "YARD", "name": "Plant Yard"},
        headers=headers,
    ).json()

    _receive(client, headers, item["id"], "40", batch="LOT-A")
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={
            "location_id": yard["id"],
            "quantity": "25",
            "unit_cost": "10.00",
            "batch_number": "LOT-A",
        },
        headers=headers,
    )

    # The same lot at two places is two rows sharing a number
    batches = client.get(
        f"/api/v1/stock-batches?item_id={item['id']}", headers=headers
    ).json()
    assert len(batches) == 2
    assert {b["batch_number"] for b in batches} == {"LOT-A"}
    # A recall still gathers them together
    trace = client.get("/api/v1/stock-batches/recall/LOT-A", headers=headers).json()
    assert Decimal(trace["remaining_quantity"]) == Decimal("65.000")


def test_batch_quantities_reconcile_with_the_location_level(client, db):
    """The invariant tying batches back to the rest of inventory."""
    headers = _proc(db)
    project = make_project(db)
    item = _item(client, headers)
    _receive(client, headers, item["id"], "60", batch="A", expiry=str(date.today() + timedelta(days=20)))
    _receive(client, headers, item["id"], "40", batch="B", expiry=str(date.today() + timedelta(days=80)))
    client.post(
        f"/api/v1/stock-items/{item['id']}/issue",
        json={"project_id": str(project.id), "quantity": "70"},
        headers=headers,
    )

    batch_total = sum(
        Decimal(b["quantity"])
        for b in client.get(
            f"/api/v1/stock-batches?item_id={item['id']}&include_empty=true",
            headers=headers,
        ).json()
    )
    levels = client.get(f"/api/v1/stock-items/{item['id']}/levels", headers=headers).json()
    level_total = sum(Decimal(l["quantity"]) for l in levels)
    item_total = Decimal(
        client.get(f"/api/v1/stock-items/{item['id']}", headers=headers).json()["qty_on_hand"]
    )
    assert batch_total == level_total == item_total == Decimal("30.000")
