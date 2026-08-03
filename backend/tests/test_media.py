import io

from app.common.enums import UserRole
from app.modules.media import service as media_service
from tests.factories import auth_headers, fake_uuid, make_project, make_user


def _pm(db):
    return auth_headers(make_user(db, role=UserRole.project_manager))


def _png_bytes() -> bytes:
    """A real 4x4 PNG so Pillow can thumbnail it."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 30, 30)).save(buf, "PNG")
    return buf.getvalue()


def _upload(client, headers, entity_type, entity_id, *, content=b"hello",
            filename="note.txt", ctype="text/plain", folder=None, caption=None):
    data = {"entity_type": entity_type, "entity_id": str(entity_id)}
    if folder:
        data["folder"] = folder
    if caption:
        data["caption"] = caption
    return client.post(
        "/api/v1/media",
        files={"file": (filename, content, ctype)},
        data=data,
        headers=headers,
    )


def test_upload_list_download_roundtrip(client, db):
    headers = _pm(db)
    project = make_project(db)
    res = _upload(
        client, headers, "project", project.id,
        folder="contracts", caption="Signed main contract",
    )
    assert res.status_code == 201
    body = res.json()
    assert body["folder"] == "contracts"
    assert body["has_thumbnail"] is False
    assert body["file_size"] == 5

    listed = client.get(
        f"/api/v1/media?entity_type=project&entity_id={project.id}", headers=headers
    ).json()
    assert listed["total"] == 1
    assert listed["items"][0]["original_filename"] == "note.txt"

    download = client.get(f"/api/v1/media/{body['id']}/file", headers=headers)
    assert download.status_code == 200
    assert download.content == b"hello"
    # No thumbnail for non-images
    assert client.get(f"/api/v1/media/{body['id']}/thumbnail", headers=headers).status_code == 404


def test_image_upload_gets_thumbnail(client, db):
    headers = _pm(db)
    project = make_project(db)
    res = _upload(
        client, headers, "project", project.id,
        content=_png_bytes(), filename="site.png", ctype="image/png", folder="photos",
    )
    assert res.status_code == 201
    body = res.json()
    assert body["has_thumbnail"] is True
    thumb = client.get(f"/api/v1/media/{body['id']}/thumbnail", headers=headers)
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/jpeg"


def test_entity_registry_gatekeeps(client, db):
    headers = _pm(db)
    project = make_project(db)
    # Unknown entity type
    assert _upload(client, headers, "user", project.id).status_code == 422
    # Known type, missing record
    assert _upload(client, headers, "project", fake_uuid()).status_code == 404


def test_upload_validation(client, db, monkeypatch):
    headers = _pm(db)
    project = make_project(db)
    # Unsupported content type
    res = _upload(client, headers, "project", project.id,
                  filename="app.exe", ctype="application/x-msdownload")
    assert res.status_code == 422
    # Empty file
    assert _upload(client, headers, "project", project.id, content=b"").status_code == 422
    # Oversize
    monkeypatch.setattr(media_service, "MAX_FILE_SIZE", 3)
    assert _upload(client, headers, "project", project.id, content=b"1234").status_code == 422


def test_folder_counts(client, db):
    headers = _pm(db)
    project = make_project(db)
    _upload(client, headers, "project", project.id, folder="contracts")
    _upload(client, headers, "project", project.id, folder="photos",
            content=_png_bytes(), filename="a.png", ctype="image/png")
    _upload(client, headers, "project", project.id, folder="photos",
            content=_png_bytes(), filename="b.png", ctype="image/png")
    res = client.get(
        f"/api/v1/media/folders?entity_type=project&entity_id={project.id}", headers=headers
    )
    body = res.json()
    assert body["total"] == 3
    assert body["counts"] == {"contracts": 1, "photos": 2}


def test_update_caption_and_folder(client, db):
    headers = _pm(db)
    project = make_project(db)
    media_id = _upload(client, headers, "project", project.id).json()["id"]
    res = client.patch(
        f"/api/v1/media/{media_id}",
        json={"caption": "Renamed", "folder": "reports"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["caption"] == "Renamed"
    assert res.json()["folder"] == "reports"


def test_media_rbac(client, db):
    viewer = auth_headers(make_user(db, role=UserRole.viewer))
    pm = _pm(db)
    project = make_project(db)
    media_id = _upload(client, pm, "project", project.id).json()["id"]
    # Viewer reads but cannot write
    assert client.get("/api/v1/media", headers=viewer).status_code == 200
    assert client.get(f"/api/v1/media/{media_id}/file", headers=viewer).status_code == 200
    assert _upload(client, viewer, "project", project.id).status_code == 403
    assert (
        client.patch(f"/api/v1/media/{media_id}", json={"caption": "x"}, headers=viewer).status_code
        == 403
    )


def test_delete_rules_and_disk_cleanup(client, db, media_root):
    site_a = make_user(db, role=UserRole.site_manager)
    site_b = make_user(db, role=UserRole.site_manager)
    pm = _pm(db)
    project = make_project(db)
    uploaded = _upload(client, auth_headers(site_a), "project", project.id).json()

    # Another non-manager cannot delete someone else's file
    res = client.delete(f"/api/v1/media/{uploaded['id']}", headers=auth_headers(site_b))
    assert res.status_code == 403

    # The uploader can; the file disappears from disk too
    stored = list((media_root / "library").rglob("*.txt"))
    assert len(stored) == 1
    res = client.delete(f"/api/v1/media/{uploaded['id']}", headers=auth_headers(site_a))
    assert res.status_code == 204
    assert not stored[0].exists()
    assert client.get(f"/api/v1/media/{uploaded['id']}/file", headers=pm).status_code == 404


def test_search_by_filename_and_caption(client, db):
    headers = _pm(db)
    project = make_project(db)
    _upload(client, headers, "project", project.id, filename="foundation-drawing.txt")
    _upload(client, headers, "project", project.id, caption="Roof warranty certificate")
    assert client.get("/api/v1/media?search=foundation", headers=headers).json()["total"] == 1
    assert client.get("/api/v1/media?search=warranty", headers=headers).json()["total"] == 1
    assert client.get("/api/v1/media?search=nothing-matches", headers=headers).json()["total"] == 0
