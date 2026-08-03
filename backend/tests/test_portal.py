import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.common.enums import UserRole
from app.modules.portal.models import ClientAccessToken
from tests.factories import auth_headers, make_client_record, make_project, make_user


def _pm(db):
    return auth_headers(make_user(db, role=UserRole.project_manager))


def _link(client, db, headers, client_record, **body):
    return client.post(
        f"/api/v1/clients/{client_record.id}/portal-links",
        json={"label": "Sent to demo contact", **body},
        headers=headers,
    )


def _portal(token):
    return {"X-Portal-Token": token}


def _issued_valuation(client, db, headers, project):
    val = client.post(
        f"/api/v1/projects/{project.id}/valuations",
        json={"period_end": "2026-07-31", "gross_valuation": "100000"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/valuations/{val['id']}/issue", json={}, headers=headers)
    return val


def test_link_lifecycle_and_rbac(client, db):
    pm = _pm(db)
    client_record = make_client_record(db)

    created = _link(client, db, pm, client_record)
    assert created.status_code == 201
    body = created.json()
    assert body["token"]  # raw shown exactly once
    assert body["url"].endswith(body["token"])

    listed = client.get(
        f"/api/v1/clients/{client_record.id}/portal-links", headers=pm
    ).json()
    assert len(listed) == 1
    assert "token" not in listed[0]  # raw never listed

    viewer = auth_headers(make_user(db, role=UserRole.viewer))
    assert _link(client, db, viewer, client_record).status_code == 403

    revoked = client.post(
        f"/api/v1/portal-links/{body['id']}/revoke", headers=pm
    ).json()
    assert revoked["revoked_at"] is not None
    res = client.get("/api/v1/portal/summary", headers=_portal(body["token"]))
    assert res.status_code == 401


def test_portal_scoped_to_own_client(client, db):
    pm = _pm(db)
    mine = make_client_record(db, name="Portal Client A")
    other = make_client_record(db, name="Portal Client B")
    my_project = make_project(db, client=mine, contract_value=Decimal("500000"))
    other_project = make_project(db, client=other)

    token = _link(client, db, pm, mine).json()["token"]
    summary = client.get("/api/v1/portal/summary", headers=_portal(token))
    assert summary.status_code == 200
    body = summary.json()
    assert body["client_name"] == "Portal Client A"
    codes = [p["code"] for p in body["projects"]]
    assert my_project.code in codes
    assert other_project.code not in codes

    # own project detail works; foreign project is invisible (404)
    detail = client.get(f"/api/v1/portal/projects/{my_project.id}", headers=_portal(token))
    assert detail.status_code == 200
    assert (
        client.get(
            f"/api/v1/portal/projects/{other_project.id}", headers=_portal(token)
        ).status_code
        == 404
    )


def test_portal_auth_failures(client, db):
    pm = _pm(db)
    client_record = make_client_record(db)
    assert client.get("/api/v1/portal/summary").status_code == 401
    assert client.get("/api/v1/portal/summary", headers=_portal("bogus")).status_code == 401

    expired = _link(client, db, pm, client_record).json()
    row = db.scalar(
        select(ClientAccessToken).where(
            ClientAccessToken.token_hash
            == hashlib.sha256(expired["token"].encode()).hexdigest()
        )
    )
    row.expires_at = datetime.now(UTC) - timedelta(days=1)
    db.flush()
    res = client.get("/api/v1/portal/summary", headers=_portal(expired["token"]))
    assert res.status_code == 401
    assert "expired" in res.json()["error"]["detail"].lower()

    # a portal token is not a staff credential
    assert client.get("/api/v1/projects", headers=_portal(expired["token"])).status_code == 401


def test_portal_valuations_hide_drafts_and_serve_certificate(client, db):
    pm = _pm(db)
    client_record = make_client_record(db)
    project = make_project(
        db, client=client_record, contract_value=Decimal("900000"), retention_pct=Decimal("10")
    )
    issued = _issued_valuation(client, db, pm, project)
    # a draft the client must never see
    client.post(
        f"/api/v1/projects/{project.id}/valuations",
        json={"period_end": "2026-08-31", "gross_valuation": "150000"},
        headers=pm,
    )

    token = _link(client, db, pm, client_record).json()["token"]
    vals = client.get(
        f"/api/v1/portal/projects/{project.id}/valuations", headers=_portal(token)
    ).json()
    assert len(vals) == 1
    assert vals[0]["status"] == "issued"

    cert = client.get(
        f"/api/v1/portal/valuations/{issued['id']}/certificate", headers=_portal(token)
    )
    assert cert.status_code == 200
    assert cert.headers["content-type"] == "application/pdf"
    assert cert.content.startswith(b"%PDF")

    # the other client's link can't fetch it
    stranger = make_client_record(db, name="Stranger Ltd")
    stranger_token = _link(client, db, pm, stranger).json()["token"]
    assert (
        client.get(
            f"/api/v1/portal/valuations/{issued['id']}/certificate",
            headers=_portal(stranger_token),
        ).status_code
        == 404
    )
