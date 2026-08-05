"""Sending an RFQ to suppliers, and the quote coming back."""

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


def _proc(db):
    return auth_headers(make_user(db, role=UserRole.procurement_officer))


def _issued_rfq(client, db, headers, project):
    section = make_boq_section(db, project)
    item = make_boq_item(db, section, description="Cement, 42.5N")
    rfq = client.post(
        f"/api/v1/projects/{project.id}/rfqs",
        json={
            "title": "Cement supply",
            "due_date": str(date.today() + timedelta(days=7)),
            "items": [
                {"boq_item_id": str(item.id), "description": "Cement, 42.5N",
                 "unit": "bag", "quantity": "500"}
            ],
        },
        headers=headers,
    ).json()
    client.post(f"/api/v1/rfqs/{rfq['id']}/issue", headers=headers)
    return rfq


def _send(client, headers, rfq, suppliers, **body):
    return client.post(
        f"/api/v1/rfqs/{rfq['id']}/send",
        json={"supplier_ids": [str(s.id) for s in suppliers], **body},
        headers=headers,
    )


def _token(url):
    return {"X-Rfq-Token": url.rsplit("/", 1)[1]}


def test_sending_gives_one_link_per_supplier_shown_once(client, db):
    headers = _proc(db)
    project = make_project(db)
    rfq = _issued_rfq(client, db, headers, project)
    first, second = make_supplier(db, name="Blue Circle"), make_supplier(db, name="PPC")

    res = _send(client, headers, rfq, [first, second])
    assert res.status_code == 201
    links = res.json()
    assert len(links) == 2
    assert all("/rfq/" in row["url"] for row in links)

    # The raw link never appears again
    listed = client.get(f"/api/v1/rfqs/{rfq['id']}/invites", headers=headers).json()
    assert all("url" not in invite for invite in listed)
    assert {i["status"] for i in listed} == {"sent"}


def test_a_draft_cannot_be_sent(client, db):
    """Pricing something still being edited wastes the supplier's time."""
    headers = _proc(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section)
    rfq = client.post(
        f"/api/v1/projects/{project.id}/rfqs",
        json={"title": "Draft", "items": [
            {"boq_item_id": str(item.id), "description": "X", "unit": "ea", "quantity": "1"}
        ]},
        headers=headers,
    ).json()

    res = _send(client, headers, rfq, [make_supplier(db)])
    assert res.status_code == 409
    assert "Issue the RFQ" in res.json()["error"]["detail"]


def test_a_supplier_sees_the_scope_but_never_a_price(client, db):
    """The BOQ rate is the buyer's own number. Showing it would be handing
    over the budget before asking for a quote."""
    headers = _proc(db)
    project = make_project(db)
    rfq = _issued_rfq(client, db, headers, project)
    supplier = make_supplier(db, name="Blue Circle")
    url = _send(client, headers, rfq, [supplier]).json()[0]["url"]

    view = client.get("/api/v1/rfq-portal/rfq", headers=_token(url)).json()
    assert view["doc_number"] == rfq["doc_number"]
    assert view["supplier_name"] == "Blue Circle"
    # Compared numerically: the scale depends on whether the row came fresh
    # from the database or was still in the session, and 500 is 500 either way.
    assert Decimal(view["items"][0]["quantity"]) == Decimal("500")

    # Asserted on the shape rather than by scanning the text: free fields like
    # the buyer's own name legitimately contain arbitrary words, so a substring
    # search here fails for reasons that have nothing to do with pricing.
    assert set(view) == {
        "rfq_id", "doc_number", "title", "body", "due_date",
        "buyer_name", "supplier_name", "already_responded", "items",
    }
    assert set(view["items"][0]) == {"id", "description", "unit", "quantity"}


def test_a_supplier_quote_lands_in_the_normal_comparison(client, db):
    headers = _proc(db)
    project = make_project(db)
    rfq = _issued_rfq(client, db, headers, project)
    supplier = make_supplier(db, name="Blue Circle")
    url = _send(client, headers, rfq, [supplier]).json()[0]["url"]

    view = client.get("/api/v1/rfq-portal/rfq", headers=_token(url)).json()
    res = client.post(
        "/api/v1/rfq-portal/quote",
        json={
            "items": [{"rfq_item_id": view["items"][0]["id"], "unit_price": "12.50"}],
            "payment_terms": "30 days",
            "valid_until": str(date.today() + timedelta(days=30)),
        },
        headers=_token(url),
    )
    assert res.status_code == 201
    assert res.json()["total_amount"] == "6250.00"

    # And procurement sees it exactly like a keyed-in quote
    quotes = client.get(f"/api/v1/rfqs/{rfq['id']}/quotes", headers=headers).json()
    assert len(quotes) == 1
    assert quotes[0]["status"] == "received"
    assert quotes[0]["total_amount"] == "6250.00"


def test_one_supplier_cannot_see_anothers_quote_or_rfq(client, db):
    headers = _proc(db)
    project = make_project(db)
    mine = _issued_rfq(client, db, headers, project)
    theirs = _issued_rfq(client, db, headers, make_project(db))
    a, b = make_supplier(db, name="A"), make_supplier(db, name="B")

    a_url = _send(client, headers, mine, [a]).json()[0]["url"]
    b_url = _send(client, headers, theirs, [b]).json()[0]["url"]

    # Each link reaches exactly one RFQ
    assert client.get("/api/v1/rfq-portal/rfq", headers=_token(a_url)).json()[
        "doc_number"
    ] == mine["doc_number"]
    assert client.get("/api/v1/rfq-portal/rfq", headers=_token(b_url)).json()[
        "doc_number"
    ] == theirs["doc_number"]

    # A priced quote from one is invisible to the other
    view = client.get("/api/v1/rfq-portal/rfq", headers=_token(a_url)).json()
    client.post(
        "/api/v1/rfq-portal/quote",
        json={"items": [{"rfq_item_id": view["items"][0]["id"], "unit_price": "9.99"}]},
        headers=_token(a_url),
    )
    other = client.get("/api/v1/rfq-portal/rfq", headers=_token(b_url)).json()
    assert "9.99" not in str(other)


def test_a_link_cannot_be_used_twice(client, db):
    headers = _proc(db)
    project = make_project(db)
    rfq = _issued_rfq(client, db, headers, project)
    url = _send(client, headers, rfq, [make_supplier(db)]).json()[0]["url"]
    view = client.get("/api/v1/rfq-portal/rfq", headers=_token(url)).json()
    payload = {"items": [{"rfq_item_id": view["items"][0]["id"], "unit_price": "10"}]}

    assert client.post("/api/v1/rfq-portal/quote", json=payload, headers=_token(url)).status_code == 201
    second = client.post("/api/v1/rfq-portal/quote", json=payload, headers=_token(url))
    assert second.status_code == 409


def test_resending_reissues_the_link_and_kills_the_old_one(client, db):
    headers = _proc(db)
    project = make_project(db)
    rfq = _issued_rfq(client, db, headers, project)
    supplier = make_supplier(db)

    first = _send(client, headers, rfq, [supplier]).json()[0]["url"]
    second = _send(client, headers, rfq, [supplier]).json()[0]["url"]
    assert first != second
    assert client.get("/api/v1/rfq-portal/rfq", headers=_token(first)).status_code == 401
    assert client.get("/api/v1/rfq-portal/rfq", headers=_token(second)).status_code == 200


def test_a_supplier_who_answered_cannot_be_sent_a_fresh_link(client, db):
    """Reissuing after a reply would let them quietly replace a quote that has
    already been compared against others."""
    headers = _proc(db)
    project = make_project(db)
    rfq = _issued_rfq(client, db, headers, project)
    supplier = make_supplier(db)
    url = _send(client, headers, rfq, [supplier]).json()[0]["url"]
    view = client.get("/api/v1/rfq-portal/rfq", headers=_token(url)).json()
    client.post(
        "/api/v1/rfq-portal/quote",
        json={"items": [{"rfq_item_id": view["items"][0]["id"], "unit_price": "10"}]},
        headers=_token(url),
    )

    res = _send(client, headers, rfq, [supplier])
    assert res.status_code == 409
    assert "already responded" in res.json()["error"]["detail"]


def test_a_revoked_or_expired_link_stops_working(client, db):
    from datetime import UTC, datetime

    from app.modules.procurement.models import RfqInvite

    headers = _proc(db)
    project = make_project(db)
    rfq = _issued_rfq(client, db, headers, project)
    url = _send(client, headers, rfq, [make_supplier(db)]).json()[0]["url"]
    invite_id = client.get(f"/api/v1/rfqs/{rfq['id']}/invites", headers=headers).json()[0]["id"]

    client.post(f"/api/v1/rfq-invites/{invite_id}/revoke", headers=headers)
    assert client.get("/api/v1/rfq-portal/rfq", headers=_token(url)).status_code == 401

    # Expiry is enforced on the same path
    other = _issued_rfq(client, db, headers, project)
    fresh = _send(client, headers, other, [make_supplier(db)]).json()[0]["url"]
    row = db.get(RfqInvite, client.get(
        f"/api/v1/rfqs/{other['id']}/invites", headers=headers
    ).json()[0]["id"])
    row.expires_at = datetime.now(UTC) - timedelta(days=1)
    db.flush()
    assert client.get("/api/v1/rfq-portal/rfq", headers=_token(fresh)).status_code == 401


def test_no_token_is_refused(client, db):
    assert client.get("/api/v1/rfq-portal/rfq").status_code == 401
    assert client.post("/api/v1/rfq-portal/quote", json={"items": []}).status_code in (401, 422)


def test_the_status_of_each_invite_is_visible_to_procurement(client, db):
    """Chasing quotes is the job; who has opened it and who has not is the
    whole point of sending links rather than emails."""
    headers = _proc(db)
    project = make_project(db)
    rfq = _issued_rfq(client, db, headers, project)
    quiet, keen = make_supplier(db, name="Quiet"), make_supplier(db, name="Keen")
    links = _send(client, headers, rfq, [quiet, keen]).json()
    keen_url = next(row["url"] for row in links if row["supplier_name"] == "Keen")

    view = client.get("/api/v1/rfq-portal/rfq", headers=_token(keen_url)).json()
    client.post(
        "/api/v1/rfq-portal/quote",
        json={"items": [{"rfq_item_id": view["items"][0]["id"], "unit_price": "11"}]},
        headers=_token(keen_url),
    )

    listed = client.get(f"/api/v1/rfqs/{rfq['id']}/invites", headers=headers).json()
    by_name = {row["supplier_name"]: row["status"] for row in listed}
    assert by_name == {"Quiet": "sent", "Keen": "responded"}
