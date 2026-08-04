"""Stock held across multiple locations, and transfers between them."""

from decimal import Decimal

from sqlalchemy import func, select

from app.common.enums import StockMovementType, UserRole
from app.modules.inventory.models import StockLevel, StockLocation, StockMovement
from tests.factories import auth_headers, make_project, make_user


def _proc(db):
    return auth_headers(make_user(db, role=UserRole.procurement_officer))


def _default_location(db):
    """Ask the service, which is what guarantees exactly one default exists."""
    from app.modules.inventory.service import default_location

    return default_location(db)


def _make_location(client, headers, code, name, **kw):
    res = client.post(
        "/api/v1/stock-locations",
        json={"code": code, "name": name, **kw},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


def _make_item(client, headers, code="CEM-425"):
    res = client.post(
        "/api/v1/stock-items",
        json={"code": code, "name": f"Item {code}", "unit": "bag"},
        headers=headers,
    )
    assert res.status_code == 201
    return res.json()


def test_a_default_location_always_exists(client, db):
    """Single-store users never chose a location, so one must be there."""
    location = _default_location(db)
    assert location is not None and location.is_default
    # Asking twice must not produce a second default
    assert _default_location(db).id == location.id
    assert (
        db.scalar(
            select(func.count())
            .select_from(StockLocation)
            .where(StockLocation.is_default.is_(True))
        )
        == 1
    )
    listed = client.get("/api/v1/stock-locations", headers=_proc(db)).json()
    assert any(loc["is_default"] for loc in listed)


def test_receiving_without_a_location_uses_the_default(client, db):
    headers = _proc(db)
    item = _make_item(client, headers)
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "100", "unit_cost": "10.00"},
        headers=headers,
    )

    levels = client.get(f"/api/v1/stock-items/{item['id']}/levels", headers=headers).json()
    assert len(levels) == 1
    assert Decimal(levels[0]["quantity"]) == Decimal("100.000")
    assert levels[0]["location_id"] == str(_default_location(db).id)


def test_stock_is_tracked_per_location(client, db):
    headers = _proc(db)
    item = _make_item(client, headers)
    yard = _make_location(client, headers, "YARD", "Plant Yard", kind="yard")

    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "60", "unit_cost": "10.00"},
        headers=headers,
    )
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"location_id": yard["id"], "quantity": "40", "unit_cost": "10.00"},
        headers=headers,
    )

    # The company total still reads as one number
    assert Decimal(
        client.get(f"/api/v1/stock-items/{item['id']}", headers=headers).json()["qty_on_hand"]
    ) == Decimal("100.000")
    levels = {
        row["location_code"]: Decimal(row["quantity"])
        for row in client.get(
            f"/api/v1/stock-items/{item['id']}/levels", headers=headers
        ).json()
    }
    assert levels == {"MAIN": Decimal("60.000"), "YARD": Decimal("40.000")}


def test_cannot_issue_stock_the_location_does_not_hold(client, db):
    """A healthy company total must not let you issue from an empty shelf."""
    headers = _proc(db)
    project = make_project(db)
    item = _make_item(client, headers)
    yard = _make_location(client, headers, "YARD", "Plant Yard")

    # All 100 sit in the main store; the yard has none
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "100", "unit_cost": "10.00"},
        headers=headers,
    )
    res = client.post(
        f"/api/v1/stock-items/{item['id']}/issue",
        json={
            "location_id": yard["id"],
            "project_id": str(project.id),
            "quantity": "5",
        },
        headers=headers,
    )
    assert res.status_code == 409
    assert "Plant Yard" in res.json()["error"]["detail"]
    # And nothing moved
    assert Decimal(
        client.get(f"/api/v1/stock-items/{item['id']}", headers=headers).json()["qty_on_hand"]
    ) == Decimal("100.000")


def test_transfer_moves_quantity_without_changing_the_total(client, db):
    headers = _proc(db)
    item = _make_item(client, headers)
    yard = _make_location(client, headers, "YARD", "Plant Yard")
    main = _default_location(db)
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "100", "unit_cost": "12.50"},
        headers=headers,
    )

    res = client.post(
        "/api/v1/stock-transfers",
        json={
            "stock_item_id": item["id"],
            "from_location_id": str(main.id),
            "to_location_id": yard["id"],
            "quantity": "30",
        },
        headers=headers,
    )
    assert res.status_code == 201
    transfer = res.json()
    assert transfer["doc_number"].startswith("TRF-")
    assert Decimal(transfer["value"]) == Decimal("375.00")  # 30 x 12.50

    after = client.get(f"/api/v1/stock-items/{item['id']}", headers=headers).json()
    assert Decimal(after["qty_on_hand"]) == Decimal("100.000")  # nothing created or lost
    assert Decimal(after["unit_cost"]) == Decimal("12.50")  # moving stock is not a repricing

    levels = {
        row["location_code"]: Decimal(row["quantity"])
        for row in client.get(
            f"/api/v1/stock-items/{item['id']}/levels", headers=headers
        ).json()
    }
    assert levels == {"MAIN": Decimal("70.000"), "YARD": Decimal("30.000")}


def test_transfer_posts_a_matched_pair_and_no_cost(client, db):
    from app.modules.costs.models import CostEntry

    headers = _proc(db)
    item = _make_item(client, headers)
    yard = _make_location(client, headers, "YARD", "Plant Yard")
    main = _default_location(db)
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "50", "unit_cost": "10.00"},
        headers=headers,
    )
    doc = client.post(
        "/api/v1/stock-transfers",
        json={
            "stock_item_id": item["id"],
            "from_location_id": str(main.id),
            "to_location_id": yard["id"],
            "quantity": "20",
        },
        headers=headers,
    ).json()["doc_number"]

    moves = db.scalars(
        select(StockMovement).where(
            StockMovement.movement_type == StockMovementType.transfer
        )
    ).all()
    assert len(moves) == 2
    assert {m.doc_number for m in moves} == {f"{doc}-O", f"{doc}-I"}
    # The ledger invariant holds: the pair nets to zero
    assert sum(m.quantity for m in moves) == Decimal("0")
    # Moving our own stock between our own stores spends nothing
    assert db.scalars(select(CostEntry).where(CostEntry.reference == doc)).all() == []


def test_transfer_guards(client, db):
    headers = _proc(db)
    item = _make_item(client, headers)
    yard = _make_location(client, headers, "YARD", "Plant Yard")
    main = _default_location(db)
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "10", "unit_cost": "5.00"},
        headers=headers,
    )

    def transfer(from_id, to_id, qty):
        return client.post(
            "/api/v1/stock-transfers",
            json={
                "stock_item_id": item["id"],
                "from_location_id": str(from_id),
                "to_location_id": str(to_id),
                "quantity": qty,
            },
            headers=headers,
        )

    assert transfer(main.id, main.id, "1").status_code == 422  # nowhere to nowhere
    assert transfer(main.id, yard["id"], "999").status_code == 409  # more than held
    # Nothing leaked from the failed attempts
    assert Decimal(
        client.get(f"/api/v1/stock-items/{item['id']}", headers=headers).json()["qty_on_hand"]
    ) == Decimal("10.000")


def test_adjustment_is_bounded_by_the_location_not_the_company(client, db):
    headers = _proc(db)
    item = _make_item(client, headers)
    yard = _make_location(client, headers, "YARD", "Plant Yard")
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "100", "unit_cost": "10.00"},
        headers=headers,
    )
    # The yard holds nothing, so it cannot go down by 5 even though the
    # company holds 100
    res = client.post(
        f"/api/v1/stock-items/{item['id']}/adjust",
        json={"location_id": yard["id"], "quantity": "-5", "notes": "breakage"},
        headers=headers,
    )
    assert res.status_code == 409
    assert "Plant Yard" in res.json()["error"]["detail"]


def test_stocktake_counts_one_location(client, db):
    headers = _proc(db)
    item = _make_item(client, headers)
    yard = _make_location(client, headers, "YARD", "Plant Yard")
    main = _default_location(db)
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "80", "unit_cost": "10.00"},
        headers=headers,
    )
    client.post(
        "/api/v1/stock-transfers",
        json={
            "stock_item_id": item["id"],
            "from_location_id": str(main.id),
            "to_location_id": yard["id"],
            "quantity": "30",
        },
        headers=headers,
    )

    stocktake = client.post(
        "/api/v1/stocktakes", json={"location_id": yard["id"]}, headers=headers
    ).json()
    assert stocktake["location_name"] == "Plant Yard"
    line = next(l for l in stocktake["lines"] if l["stock_item_id"] == item["id"])
    # Expected is what is on THAT shelf, not the company total
    assert Decimal(line["expected_quantity"]) == Decimal("30.000")

    client.put(
        f"/api/v1/stocktakes/{stocktake['id']}/counts",
        json={"lines": [{"stock_item_id": item["id"], "counted_quantity": "28"}]},
        headers=headers,
    )
    client.post(f"/api/v1/stocktakes/{stocktake['id']}/approve", headers=headers)

    levels = {
        row["location_code"]: Decimal(row["quantity"])
        for row in client.get(
            f"/api/v1/stock-items/{item['id']}/levels", headers=headers
        ).json()
    }
    # The shortage came off the yard only; the main store is untouched
    assert levels == {"MAIN": Decimal("50.000"), "YARD": Decimal("28.000")}
    assert Decimal(
        client.get(f"/api/v1/stock-items/{item['id']}", headers=headers).json()["qty_on_hand"]
    ) == Decimal("78.000")


def test_location_management_rules(client, db):
    headers = _proc(db)
    item = _make_item(client, headers)
    yard = _make_location(client, headers, "YARD", "Plant Yard")

    # Duplicate code
    assert (
        client.post(
            "/api/v1/stock-locations",
            json={"code": "YARD", "name": "Another"},
            headers=headers,
        ).status_code
        == 409
    )

    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"location_id": yard["id"], "quantity": "5", "unit_cost": "1.00"},
        headers=headers,
    )
    # Stock would be stranded, so deactivating is refused
    res = client.patch(
        f"/api/v1/stock-locations/{yard['id']}", json={"is_active": False}, headers=headers
    )
    assert res.status_code == 409
    assert "transfer them out" in res.json()["error"]["detail"]

    # The default location can never be switched off
    main = _default_location(db)
    assert (
        client.patch(
            f"/api/v1/stock-locations/{main.id}", json={"is_active": False}, headers=headers
        ).status_code
        == 409
    )


def test_site_store_can_belong_to_a_project(client, db):
    headers = _proc(db)
    project = make_project(db, name="Riverside Block A")
    location = _make_location(
        client, headers, "SITE-A", "Riverside Site Store",
        kind="site", project_id=str(project.id),
    )
    assert location["project_name"] == "Riverside Block A"
    assert location["kind"] == "site"


def test_location_summary_counts_and_values_its_stock(client, db):
    headers = _proc(db)
    yard = _make_location(client, headers, "YARD", "Plant Yard")
    for code, qty, cost in (("A-1", "10", "5.00"), ("A-2", "4", "20.00")):
        item = _make_item(client, headers, code)
        client.post(
            f"/api/v1/stock-items/{item['id']}/goods-in",
            json={"location_id": yard["id"], "quantity": qty, "unit_cost": cost},
            headers=headers,
        )

    summary = next(
        loc
        for loc in client.get("/api/v1/stock-locations", headers=headers).json()
        if loc["code"] == "YARD"
    )
    assert summary["item_count"] == 2
    assert Decimal(summary["stock_value"]) == Decimal("130.00")  # 10x5 + 4x20


def test_levels_always_reconcile_with_the_item_total(client, db):
    """The invariant that makes the company total trustworthy."""
    headers = _proc(db)
    project = make_project(db)
    item = _make_item(client, headers)
    yard = _make_location(client, headers, "YARD", "Plant Yard")
    main = _default_location(db)

    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "100", "unit_cost": "10.00"},
        headers=headers,
    )
    client.post(
        "/api/v1/stock-transfers",
        json={
            "stock_item_id": item["id"],
            "from_location_id": str(main.id),
            "to_location_id": yard["id"],
            "quantity": "40",
        },
        headers=headers,
    )
    client.post(
        f"/api/v1/stock-items/{item['id']}/issue",
        json={
            "location_id": yard["id"],
            "project_id": str(project.id),
            "quantity": "15",
        },
        headers=headers,
    )
    client.post(
        f"/api/v1/stock-items/{item['id']}/adjust",
        json={"quantity": "-3", "notes": "damaged"},
        headers=headers,
    )

    total = Decimal(
        client.get(f"/api/v1/stock-items/{item['id']}", headers=headers).json()["qty_on_hand"]
    )
    level_sum = db.scalar(
        select(StockLevel.quantity).where(StockLevel.stock_item_id == item["id"])
    )
    all_levels = sum(
        row.quantity
        for row in db.scalars(
            select(StockLevel).where(StockLevel.stock_item_id == item["id"])
        )
    )
    assert total == all_levels == Decimal("82.000")
    assert level_sum is not None
