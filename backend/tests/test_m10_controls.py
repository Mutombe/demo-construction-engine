"""Variation register, stocktake workflow and the diary -> timesheet bridge."""

from datetime import date, timedelta
from decimal import Decimal

from app.common.enums import BoqItemType, StockMovementType, UserRole
from tests.factories import (
    auth_headers,
    make_boq_item,
    make_boq_section,
    make_project,
    make_user,
    make_worker,
)


def _pm(db):
    return auth_headers(make_user(db, role=UserRole.project_manager))


def _proc(db):
    return auth_headers(make_user(db, role=UserRole.procurement_officer))


def _site(db):
    return auth_headers(make_user(db, role=UserRole.site_manager))


# --- Variation register ------------------------------------------------------


def test_only_approved_variations_move_the_ceiling(client, db):
    headers = _pm(db)
    project = make_project(db, contract_value=Decimal("100000"))
    section = make_boq_section(db, project)
    variation = make_boq_item(
        db, section, description="Extra retaining wall", unit="m",
        quantity=Decimal("100"), rate=Decimal("200"),  # 20,000
        item_type=BoqItemType.variation, variation_ref="VO-001",
    )

    register = client.get(f"/api/v1/projects/{project.id}/variations", headers=headers).json()
    row = register["rows"][0]
    assert row["variation_status"] == "proposed"
    assert Decimal(register["proposed_additions"]) == Decimal("20000.00")
    assert Decimal(register["approved_additions"]) == Decimal("0")
    # Proposed work is not certifiable, so the ceiling has not moved
    assert Decimal(register["effective_contract_value"]) == Decimal("100000.00")
    assert (
        client.post(
            f"/api/v1/projects/{project.id}/valuations",
            json={"period_end": str(date.today()), "gross_valuation": "110000"},
            headers=headers,
        ).status_code
        == 422
    )

    res = client.post(
        f"/api/v1/boq-items/{variation.id}/variation-status",
        json={"status": "approved"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["variation_status"] == "approved"

    after = client.get(f"/api/v1/projects/{project.id}/variations", headers=headers).json()
    assert Decimal(after["approved_additions"]) == Decimal("20000.00")
    assert Decimal(after["effective_contract_value"]) == Decimal("120000.00")
    assert (
        client.post(
            f"/api/v1/projects/{project.id}/valuations",
            json={"period_end": str(date.today()), "gross_valuation": "110000"},
            headers=headers,
        ).status_code
        == 201
    )


def test_rejected_variation_is_excluded_from_every_total(client, db):
    headers = _pm(db)
    project = make_project(db, contract_value=Decimal("50000"))
    section = make_boq_section(db, project)
    item = make_boq_item(
        db, section, quantity=Decimal("10"), rate=Decimal("100"),
        item_type=BoqItemType.variation, variation_ref="VO-009",
    )
    client.post(
        f"/api/v1/boq-items/{item.id}/variation-status",
        json={"status": "rejected"},
        headers=headers,
    )
    register = client.get(f"/api/v1/projects/{project.id}/variations", headers=headers).json()
    assert Decimal(register["rejected_total"]) == Decimal("1000.00")
    assert Decimal(register["proposed_additions"]) == Decimal("0")
    assert Decimal(register["effective_contract_value"]) == Decimal("50000.00")


def test_approved_omission_lowers_the_ceiling(client, db):
    headers = _pm(db)
    project = make_project(db, contract_value=Decimal("80000"))
    section = make_boq_section(db, project)
    omission = make_boq_item(
        db, section, quantity=Decimal("50"), rate=Decimal("100"),  # 5,000
        item_type=BoqItemType.omission, variation_ref="VO-002",
    )
    client.post(
        f"/api/v1/boq-items/{omission.id}/variation-status",
        json={"status": "approved"},
        headers=headers,
    )
    register = client.get(f"/api/v1/projects/{project.id}/variations", headers=headers).json()
    assert Decimal(register["approved_omissions"]) == Decimal("5000.00")
    assert Decimal(register["effective_contract_value"]) == Decimal("75000.00")


def test_original_scope_has_no_approval_state(client, db):
    headers = _pm(db)
    project = make_project(db)
    item = make_boq_item(db, make_boq_section(db, project))
    res = client.post(
        f"/api/v1/boq-items/{item.id}/variation-status",
        json={"status": "approved"},
        headers=headers,
    )
    assert res.status_code == 422
    # And it never appears on the register
    register = client.get(f"/api/v1/projects/{project.id}/variations", headers=headers).json()
    assert register["rows"] == []


def test_variation_decision_requires_project_manager(client, db):
    project = make_project(db)
    item = make_boq_item(
        db, make_boq_section(db, project), item_type=BoqItemType.variation
    )
    assert (
        client.post(
            f"/api/v1/boq-items/{item.id}/variation-status",
            json={"status": "approved"},
            headers=_site(db),
        ).status_code
        == 403
    )


# --- Stocktake ---------------------------------------------------------------


def _stock_item(client, headers, code, qty="100"):
    item = client.post(
        "/api/v1/stock-items",
        json={"code": code, "name": f"Item {code}", "unit": "ea"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": qty, "unit_cost": "10.00"},
        headers=headers,
    )
    return item


def test_stocktake_counts_then_posts_variances(client, db):
    headers = _proc(db)
    short = _stock_item(client, headers, "SHORT-1", qty="100")
    over = _stock_item(client, headers, "OVER-1", qty="50")

    stocktake = client.post("/api/v1/stocktakes", json={}, headers=headers).json()
    assert stocktake["status"] == "counting"
    assert stocktake["line_count"] == 2
    assert stocktake["counted_count"] == 0
    expected = {line["stock_item_id"]: line for line in stocktake["lines"]}
    assert Decimal(expected[short["id"]]["expected_quantity"]) == Decimal("100.000")

    counted = client.put(
        f"/api/v1/stocktakes/{stocktake['id']}/counts",
        json={
            "lines": [
                {"stock_item_id": short["id"], "counted_quantity": "94", "notes": "breakage"},
                {"stock_item_id": over["id"], "counted_quantity": "52"},
            ]
        },
        headers=headers,
    ).json()
    by_item = {line["stock_item_id"]: line for line in counted["lines"]}
    assert Decimal(by_item[short["id"]]["variance_quantity"]) == Decimal("-6.000")
    assert Decimal(by_item[short["id"]]["variance_value"]) == Decimal("-60.00")
    assert Decimal(by_item[over["id"]]["variance_quantity"]) == Decimal("2.000")
    assert Decimal(counted["variance_value"]) == Decimal("-40.00")

    # Nothing has moved until it is approved
    assert Decimal(
        client.get(f"/api/v1/stock-items/{short['id']}", headers=headers).json()["qty_on_hand"]
    ) == Decimal("100.000")

    approved = client.post(
        f"/api/v1/stocktakes/{stocktake['id']}/approve", headers=headers
    ).json()
    assert approved["status"] == "approved"
    assert approved["approved_at"] is not None
    assert Decimal(
        client.get(f"/api/v1/stock-items/{short['id']}", headers=headers).json()["qty_on_hand"]
    ) == Decimal("94.000")
    assert Decimal(
        client.get(f"/api/v1/stock-items/{over['id']}", headers=headers).json()["qty_on_hand"]
    ) == Decimal("52.000")

    movements = client.get(
        f"/api/v1/stock-items/{short['id']}/movements", headers=headers
    ).json()["items"]
    adjustment = next(m for m in movements if m["movement_type"] == "adjustment")
    assert adjustment["doc_number"].startswith("ADJ-")
    assert stocktake["doc_number"] in adjustment["notes"]
    assert "breakage" in adjustment["notes"]


def test_uncounted_lines_are_left_alone(client, db):
    headers = _proc(db)
    counted_item = _stock_item(client, headers, "C-1", qty="20")
    skipped_item = _stock_item(client, headers, "S-1", qty="30")

    stocktake = client.post("/api/v1/stocktakes", json={}, headers=headers).json()
    client.put(
        f"/api/v1/stocktakes/{stocktake['id']}/counts",
        json={"lines": [{"stock_item_id": counted_item["id"], "counted_quantity": "18"}]},
        headers=headers,
    )
    client.post(f"/api/v1/stocktakes/{stocktake['id']}/approve", headers=headers)

    # A partial count must not zero the shelves it never visited
    assert Decimal(
        client.get(f"/api/v1/stock-items/{skipped_item['id']}", headers=headers).json()[
            "qty_on_hand"
        ]
    ) == Decimal("30.000")
    assert Decimal(
        client.get(f"/api/v1/stock-items/{counted_item['id']}", headers=headers).json()[
            "qty_on_hand"
        ]
    ) == Decimal("18.000")


def test_stocktake_lifecycle_guards(client, db):
    headers = _proc(db)
    _stock_item(client, headers, "G-1")
    first = client.post("/api/v1/stocktakes", json={}, headers=headers).json()

    # Only one counting session at a time
    assert client.post("/api/v1/stocktakes", json={}, headers=headers).status_code == 409
    # Nothing counted yet
    assert (
        client.post(f"/api/v1/stocktakes/{first['id']}/approve", headers=headers).status_code
        == 422
    )

    client.post(f"/api/v1/stocktakes/{first['id']}/cancel", headers=headers)
    assert (
        client.post(f"/api/v1/stocktakes/{first['id']}/approve", headers=headers).status_code
        == 409
    )
    # Cancelling frees the slot
    assert client.post("/api/v1/stocktakes", json={}, headers=headers).status_code == 201


def test_site_can_count_but_not_approve(client, db):
    proc, site = _proc(db), _site(db)
    item = _stock_item(client, proc, "R-1", qty="10")
    stocktake = client.post("/api/v1/stocktakes", json={}, headers=proc).json()

    assert (
        client.put(
            f"/api/v1/stocktakes/{stocktake['id']}/counts",
            json={"lines": [{"stock_item_id": item["id"], "counted_quantity": "9"}]},
            headers=site,
        ).status_code
        == 200
    )
    assert (
        client.post(f"/api/v1/stocktakes/{stocktake['id']}/approve", headers=site).status_code
        == 403
    )


def test_stocktake_can_target_one_category(client, db):
    headers = _proc(db)
    client.post(
        "/api/v1/stock-items",
        json={"code": "CEM-1", "name": "Cement", "unit": "bag", "category": "cement"},
        headers=headers,
    )
    client.post(
        "/api/v1/stock-items",
        json={"code": "STL-1", "name": "Steel", "unit": "t", "category": "steel"},
        headers=headers,
    )
    stocktake = client.post(
        "/api/v1/stocktakes", json={"category": "cement"}, headers=headers
    ).json()
    assert stocktake["line_count"] == 1
    assert stocktake["lines"][0]["code"] == "CEM-1"


# --- Diary -> timesheets -----------------------------------------------------


def _diary(client, headers, project, when=None):
    return client.post(
        f"/api/v1/projects/{project.id}/diary",
        json={
            "entry_date": str(when or date.today()),
            "weather": "sunny",
            "work_done": "Slab pour to grid 3",
        },
        headers=headers,
    ).json()


def test_diary_labour_pushes_to_timesheets_once(client, db):
    headers = _site(db)
    project = make_project(db)
    worker_a = make_worker(db, full_name="Tapiwa M")
    worker_b = make_worker(db, full_name="Grace N")
    entry = _diary(client, headers, project)

    with_labour = client.put(
        f"/api/v1/diary/{entry['id']}/labour",
        json={
            "lines": [
                {"worker_id": str(worker_a.id), "quantity": "1", "overtime_quantity": "2"},
                {"worker_id": str(worker_b.id), "quantity": "1"},
            ]
        },
        headers=headers,
    ).json()
    assert len(with_labour["labour"]) == 2
    assert with_labour["labour_headcount"] == 2  # headcount follows the list
    assert with_labour["timesheets_pushed"] is False
    assert {line["worker_name"] for line in with_labour["labour"]} == {"Tapiwa M", "Grace N"}

    result = client.post(
        f"/api/v1/diary/{entry['id']}/push-timesheets", headers=headers
    ).json()
    assert result["created"] == 2
    assert result["updated"] == 0
    assert result["skipped_locked"] == []

    sheets = client.get(
        f"/api/v1/timesheets?project_id={project.id}&date_from={date.today()}"
        f"&date_to={date.today()}",
        headers=headers,
    ).json()
    assert sheets["total"] == 2
    overtime = {Decimal(s["overtime_quantity"]) for s in sheets["items"]}
    assert overtime == {Decimal("2.00"), Decimal("0.00")}

    after = client.get(f"/api/v1/diary/{entry['id']}", headers=headers).json()
    assert after["timesheets_pushed"] is True

    # Pushing again updates rather than duplicating
    again = client.post(
        f"/api/v1/diary/{entry['id']}/push-timesheets", headers=headers
    ).json()
    assert again["created"] == 0
    assert again["updated"] == 2
    assert (
        client.get(
            f"/api/v1/timesheets?project_id={project.id}&date_from={date.today()}"
            f"&date_to={date.today()}",
            headers=headers,
        ).json()["total"]
        == 2
    )


def test_push_leaves_paid_time_alone(client, db):
    site, pm = _site(db), _pm(db)
    project = make_project(db)
    worker = make_worker(db, full_name="Paid Already")
    entry = _diary(client, site, project)
    client.put(
        f"/api/v1/diary/{entry['id']}/labour",
        json={"lines": [{"worker_id": str(worker.id), "quantity": "1"}]},
        headers=site,
    )
    client.post(f"/api/v1/diary/{entry['id']}/push-timesheets", headers=site)

    # Approving a pay run locks that time
    run = client.post(
        "/api/v1/pay-runs",
        json={
            "period_start": str(date.today() - timedelta(days=6)),
            "period_end": str(date.today()),
        },
        headers=pm,
    ).json()
    client.post(f"/api/v1/pay-runs/{run['id']}/approve", headers=pm)

    result = client.post(
        f"/api/v1/diary/{entry['id']}/push-timesheets", headers=site
    ).json()
    assert result["skipped_locked"] == ["Paid Already"]
    assert result["created"] == 0
    assert result["updated"] == 0


def test_diary_labour_guards(client, db):
    headers = _site(db)
    project = make_project(db)
    worker = make_worker(db)
    entry = _diary(client, headers, project)

    # The same worker twice is a data-entry mistake, not two shifts
    res = client.put(
        f"/api/v1/diary/{entry['id']}/labour",
        json={
            "lines": [
                {"worker_id": str(worker.id), "quantity": "1"},
                {"worker_id": str(worker.id), "quantity": "1"},
            ]
        },
        headers=headers,
    )
    assert res.status_code == 422

    # Nothing to push before labour is recorded
    assert (
        client.post(
            f"/api/v1/diary/{entry['id']}/push-timesheets", headers=headers
        ).status_code
        == 422
    )

    # Zero-hour lines are dropped rather than stored
    cleared = client.put(
        f"/api/v1/diary/{entry['id']}/labour",
        json={"lines": [{"worker_id": str(worker.id), "quantity": "0"}]},
        headers=headers,
    ).json()
    assert cleared["labour"] == []
    assert cleared["labour_headcount"] == 0


def test_diary_labour_replaces_the_previous_list(client, db):
    headers = _site(db)
    project = make_project(db)
    a, b = make_worker(db), make_worker(db)
    entry = _diary(client, headers, project)

    client.put(
        f"/api/v1/diary/{entry['id']}/labour",
        json={"lines": [{"worker_id": str(a.id), "quantity": "1"}]},
        headers=headers,
    )
    replaced = client.put(
        f"/api/v1/diary/{entry['id']}/labour",
        json={"lines": [{"worker_id": str(b.id), "quantity": "1"}]},
        headers=headers,
    ).json()
    assert [line["worker_id"] for line in replaced["labour"]] == [str(b.id)]


def test_stocktake_corrections_post_as_plain_adjustments(client, db):
    """A stocktake must not invent its own movement type.

    Corrections stay ordinary adjustments so the ledger reconciles the same way
    whoever made the correction. (This originally froze the whole enum, which
    was over-specified — the enum may legitimately grow, as it did for
    transfers; what must not change is how a count posts.)
    """
    headers = _proc(db)
    item = _stock_item(client, headers, "GUARD-1", qty="10")
    stocktake = client.post("/api/v1/stocktakes", json={}, headers=headers).json()
    client.put(
        f"/api/v1/stocktakes/{stocktake['id']}/counts",
        json={"lines": [{"stock_item_id": item["id"], "counted_quantity": "8"}]},
        headers=headers,
    )
    client.post(f"/api/v1/stocktakes/{stocktake['id']}/approve", headers=headers)

    movements = client.get(
        f"/api/v1/stock-items/{item['id']}/movements", headers=headers
    ).json()["items"]
    correction = next(m for m in movements if stocktake["doc_number"] in (m["notes"] or ""))
    assert correction["movement_type"] == StockMovementType.adjustment.value
    assert correction["doc_number"].startswith("ADJ-")
