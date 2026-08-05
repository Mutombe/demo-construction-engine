"""Progress photos on a client portal link."""

from app.common.enums import UserRole
from tests.factories import auth_headers, make_client_record, make_project, make_user


def _pm(db):
    return auth_headers(make_user(db, role=UserRole.project_manager))


def _portal_token(client, db, headers, client_record):
    res = client.post(
        f"/api/v1/clients/{client_record.id}/portal-links",
        json={"label": "Photos"},
        headers=headers,
    )
    assert res.status_code == 201
    return {"X-Portal-Token": res.json()["token"]}


def _upload_photo(client, headers, project, *, caption=None, folder="photos"):
    data = {"entity_type": "project", "entity_id": str(project.id), "folder": folder}
    if caption:
        data["caption"] = caption
    res = client.post(
        "/api/v1/media",
        files={"file": ("shot.txt", b"pretend-image", "text/plain")},
        data=data,
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_a_client_sees_their_project_photos_oldest_first(client, db, media_root):
    """The portal is a story of the build, so it runs forwards — the opposite
    of the staff timeline, which leads with what just happened."""
    pm = _pm(db)
    client_record = make_client_record(db)
    project = make_project(db, client=client_record)
    first = _upload_photo(client, pm, project, caption="Excavation")
    second = _upload_photo(client, pm, project, caption="Foundations")
    token = _portal_token(client, db, pm, client_record)

    body = client.get(f"/api/v1/portal/projects/{project.id}/photos", headers=token).json()
    assert body["total_photos"] == 2
    ids = [p["id"] for day in body["days"] for p in day["photos"]]
    assert ids == [first["id"], second["id"]]
    assert body["days"][0]["photos"][0]["caption"] == "Excavation"


def test_only_the_photos_folder_reaches_the_client(client, db, media_root):
    """Contracts and invoices live in the same library. A client link must
    never be a way to read them."""
    pm = _pm(db)
    client_record = make_client_record(db)
    project = make_project(db, client=client_record)
    _upload_photo(client, pm, project, caption="Site", folder="photos")
    contract = _upload_photo(client, pm, project, caption="Contract", folder="contracts")
    token = _portal_token(client, db, pm, client_record)

    body = client.get(f"/api/v1/portal/projects/{project.id}/photos", headers=token).json()
    assert body["total_photos"] == 1
    assert all(p["caption"] != "Contract" for day in body["days"] for p in day["photos"])

    # And it is not reachable by asking for it directly either
    res = client.get(f"/api/v1/portal/photos/{contract['id']}/file", headers=token)
    assert res.status_code == 404


def test_a_photo_serves_through_the_token(client, db, media_root):
    pm = _pm(db)
    client_record = make_client_record(db)
    project = make_project(db, client=client_record)
    photo = _upload_photo(client, pm, project)
    token = _portal_token(client, db, pm, client_record)

    res = client.get(f"/api/v1/portal/photos/{photo['id']}/file", headers=token)
    assert res.status_code == 200
    assert res.content == b"pretend-image"

    # No token, no photo: this is not a public static mount
    assert client.get(f"/api/v1/portal/photos/{photo['id']}/file").status_code == 401


def test_one_client_cannot_read_another_clients_photos(client, db, media_root):
    """The id is a guessable handle, so ownership is checked on the file
    itself and not merely on the project route that listed it."""
    pm = _pm(db)
    theirs = make_client_record(db, name="Other Client")
    their_project = make_project(db, client=theirs)
    their_photo = _upload_photo(client, pm, their_project, caption="Not yours")

    mine = make_client_record(db, name="My Client")
    make_project(db, client=mine)
    my_token = _portal_token(client, db, pm, mine)

    assert client.get(
        f"/api/v1/portal/projects/{their_project.id}/photos", headers=my_token
    ).status_code == 404
    assert client.get(
        f"/api/v1/portal/photos/{their_photo['id']}/file", headers=my_token
    ).status_code == 404


def test_a_project_with_no_photos_is_an_empty_timeline_not_an_error(client, db):
    pm = _pm(db)
    client_record = make_client_record(db)
    project = make_project(db, client=client_record)
    token = _portal_token(client, db, pm, client_record)

    body = client.get(f"/api/v1/portal/projects/{project.id}/photos", headers=token).json()
    assert body["total_photos"] == 0
    assert body["days"] == []
    assert body["first_photo"] is None


def test_a_revoked_link_stops_serving_photos(client, db, media_root):
    pm = _pm(db)
    client_record = make_client_record(db)
    project = make_project(db, client=client_record)
    photo = _upload_photo(client, pm, project)
    created = client.post(
        f"/api/v1/clients/{client_record.id}/portal-links",
        json={"label": "Temporary"},
        headers=pm,
    ).json()
    token = {"X-Portal-Token": created["token"]}
    assert client.get(f"/api/v1/portal/photos/{photo['id']}/file", headers=token).status_code == 200

    client.post(f"/api/v1/portal-links/{created['id']}/revoke", headers=pm)
    assert client.get(f"/api/v1/portal/photos/{photo['id']}/file", headers=token).status_code == 401
