from tests.factories import auth_headers, make_project, make_user


def test_project_map_pins(client, db):
    from decimal import Decimal

    user = auth_headers(make_user(db))
    pinned = make_project(
        db, latitude=Decimal("-17.8"), longitude=Decimal("31.05"), name="Pinned Site"
    )
    make_project(db, name="No pin")

    res = client.get("/api/v1/projects/map", headers=user)
    assert res.status_code == 200
    pins = res.json()
    ids = [p["id"] for p in pins]
    assert str(pinned.id) in ids
    pin = next(p for p in pins if p["id"] == str(pinned.id))
    assert pin["name"] == "Pinned Site"
    assert "progress_pct" in pin
    # unpinned project excluded
    assert all(p["name"] != "No pin" for p in pins)
