"""What a supplier is like to deal with, across the four things that decide it.

The tests worth having here are about honesty. A supplier with one delivery
does not have a perfect record; a price is not dear except against another
price; and a score with nothing behind it has to say so rather than read as a
verdict.
"""

from datetime import date, timedelta
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

TODAY = date.today()


def _proc(db):
    return auth_headers(make_user(db, role=UserRole.procurement_officer))


def _order(client, headers, project, supplier, total="1000", expected=None, received=None):
    res = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "expected_delivery": str(expected) if expected else None,
            "items": [
                {
                    "description": "Cement",
                    "quantity": "10",
                    "unit": "bag",
                    "unit_price": str(Decimal(total) / 10),
                }
            ],
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    po = res.json()
    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)
    if received is not None:
        client.post(
            f"/api/v1/purchase-orders/{po['id']}/receive",
            json={"received_date": str(received)},
            headers=headers,
        )
    return po


def _assess(client, headers, po, **kw):
    return client.post(
        f"/api/v1/purchase-orders/{po['id']}/assessment", json=kw, headers=headers
    )


# --- Judging a delivery ------------------------------------------------------


def test_quality_and_professionalism_are_recorded_against_the_delivery(client, db):
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)
    po = _order(client, headers, project, supplier, received=TODAY)

    res = _assess(client, headers, po, quality=4, professionalism=5, would_use_again=True)
    assert res.status_code == 201, res.text

    rating = client.get(f"/api/v1/suppliers/{supplier.id}/rating", headers=headers).json()
    assert Decimal(rating["quality"]) == Decimal("4.0")
    assert Decimal(rating["professionalism"]) == Decimal("5.0")


def test_nothing_delivered_yet_cannot_be_judged(client, db):
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)
    po = _order(client, headers, project, supplier)

    res = _assess(client, headers, po, quality=5)
    assert res.status_code == 409
    assert "nothing to judge" in res.json()["error"]["detail"].lower()


def test_a_delivery_cannot_be_judged_twice_into_the_average(client, db):
    """Revising a view is fine. Scoring the same delivery again would count it
    twice and let a supplier be padded."""
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)
    po = _order(client, headers, project, supplier, received=TODAY)

    _assess(client, headers, po, quality=5, professionalism=5)
    _assess(client, headers, po, quality=1, professionalism=1)

    assessments = client.get(
        f"/api/v1/suppliers/{supplier.id}/assessments", headers=headers
    ).json()
    assert len(assessments) == 1

    rating = client.get(f"/api/v1/suppliers/{supplier.id}/rating", headers=headers).json()
    assert Decimal(rating["quality"]) == Decimal("1.0")


def test_a_score_out_of_range_is_refused(client, db):
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)
    po = _order(client, headers, project, supplier, received=TODAY)

    assert _assess(client, headers, po, quality=9).status_code == 422


def test_no_view_is_kept_apart_from_a_middling_score(client, db):
    """Leaving quality blank is not the same as calling it average, and the
    rating must not turn one into the other."""
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)
    po = _order(client, headers, project, supplier, received=TODAY)

    _assess(client, headers, po, professionalism=4)

    rating = client.get(f"/api/v1/suppliers/{supplier.id}/rating", headers=headers).json()
    assert rating["quality"] is None
    assert Decimal(rating["professionalism"]) == Decimal("4.0")


# --- Price, measured against the other bids ---------------------------------


def _rfq_with_bids(client, headers, db, project, bids):
    """An enquiry with a price from each supplier."""
    item = make_boq_item(db, make_boq_section(db, project))
    res = client.post(
        f"/api/v1/projects/{project.id}/rfqs",
        json={"title": "Readymix", "items": [{"boq_item_id": str(item.id)}]},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    rfq = res.json()
    # Quotes cannot be recorded against an enquiry that was never sent out.
    client.post(f"/api/v1/rfqs/{rfq['id']}/issue", headers=headers)
    for supplier, total in bids:
        bid = client.post(
            f"/api/v1/rfqs/{rfq['id']}/quotes",
            json={
                "supplier_id": str(supplier.id),
                "items": [
                    {"description": "C25", "quantity": "10", "unit": "m3",
                     "unit_price": str(Decimal(total) / 10)}
                ],
            },
            headers=headers,
        )
        assert bid.status_code == 201, bid.text
    return rfq


def test_a_price_is_only_dear_against_another_price(client, db):
    """One bid on an enquiry says nothing about whether it was a good price."""
    headers = _proc(db)
    project = make_project(db)
    alone = make_supplier(db, name="Only Bidder")
    _rfq_with_bids(client, headers, db, project, [(alone, "5000")])

    rating = client.get(f"/api/v1/suppliers/{alone.id}/rating", headers=headers).json()
    assert rating["contested_enquiries"] == 0
    assert rating["price"] is None


def test_bidding_above_the_field_shows_as_a_worse_price_score(client, db):
    headers = _proc(db)
    project = make_project(db)
    cheap = make_supplier(db, name="Keen")
    dear = make_supplier(db, name="Dear")
    _rfq_with_bids(client, headers, db, project, [(cheap, "5000"), (dear, "6000")])

    keen = client.get(f"/api/v1/suppliers/{cheap.id}/rating", headers=headers).json()
    steep = client.get(f"/api/v1/suppliers/{dear.id}/rating", headers=headers).json()

    assert Decimal(keen["avg_above_lowest_pct"]) == Decimal("0.0")
    assert Decimal(steep["avg_above_lowest_pct"]) == Decimal("20.0")
    assert Decimal(keen["price"]) > Decimal(steep["price"])
    assert keen["lowest_bid_count"] == 1


# --- The overall -------------------------------------------------------------


def test_the_overall_is_withheld_until_every_part_is_known(client, db):
    """Averaging three knowns and a blank produces something that looks like a
    verdict and is not one."""
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)
    po = _order(client, headers, project, supplier, received=TODAY)
    _assess(client, headers, po, quality=5, professionalism=5)

    rating = client.get(f"/api/v1/suppliers/{supplier.id}/rating", headers=headers).json()
    # No expected date on the order and no contested enquiry, so delivery and
    # price are both unknown.
    assert rating["overall"] is None


def test_one_good_delivery_is_not_a_reputation(client, db):
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)
    po = _order(client, headers, project, supplier, received=TODAY)
    _assess(client, headers, po, quality=5, professionalism=5)

    rating = client.get(f"/api/v1/suppliers/{supplier.id}/rating", headers=headers).json()
    assert rating["provisional"] is True
    assert rating["assessments"] == 1


def test_a_supplier_never_traded_with_is_left_off_the_table(client, db):
    """Never having been used is not the same as having been used badly."""
    headers = _proc(db)
    stranger = make_supplier(db, name="Never Used")

    rows = client.get("/api/v1/supplier-ratings", headers=headers).json()
    assert all(r["supplier_id"] != str(stranger.id) for r in rows)


# --- Where it has to appear --------------------------------------------------


def test_the_bid_comparison_puts_the_record_beside_the_price(client, db):
    """The reason for keeping any of this: it is in front of somebody at the
    moment they choose, not filed to be looked up afterwards."""
    headers = _proc(db)
    project = make_project(db)
    good = make_supplier(db, name="Reliable")
    cheap = make_supplier(db, name="Cheapest")

    po = _order(client, headers, project, good, received=TODAY)
    _assess(client, headers, po, quality=5, professionalism=5)

    rfq = _rfq_with_bids(client, headers, db, project, [(cheap, "4000"), (good, "4800")])

    rows = client.get(f"/api/v1/rfqs/{rfq['id']}/bid-comparison", headers=headers).json()
    assert [r["supplier_name"] for r in rows][0] == "Cheapest"

    reliable = next(r for r in rows if r["supplier_name"] == "Reliable")
    assert Decimal(reliable["quality"]) == Decimal("5.0")
    assert Decimal(reliable["above_lowest_pct"]) == Decimal("20.0")
    assert reliable["assessments"] == 1


def test_deliveries_nobody_judged_are_listed_so_they_get_judged(client, db):
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)
    po = _order(client, headers, project, supplier, received=TODAY)

    outstanding = client.get("/api/v1/deliveries/unassessed", headers=headers).json()
    assert any(row["purchase_order_id"] == po["id"] for row in outstanding)

    _assess(client, headers, po, quality=4)
    outstanding = client.get("/api/v1/deliveries/unassessed", headers=headers).json()
    assert all(row["purchase_order_id"] != po["id"] for row in outstanding)


def test_late_delivery_shows_in_the_delivery_score(client, db):
    headers = _proc(db)
    project = make_project(db)
    supplier = make_supplier(db)
    _order(
        client,
        headers,
        project,
        supplier,
        expected=TODAY - timedelta(days=10),
        received=TODAY,
    )

    rating = client.get(f"/api/v1/suppliers/{supplier.id}/rating", headers=headers).json()
    assert Decimal(rating["on_time_pct"]) == Decimal("0.0")
    assert Decimal(rating["delivery"]) == Decimal("0.0")
