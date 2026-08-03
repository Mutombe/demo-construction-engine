from datetime import date, timedelta

from app.common.enums import UserRole
from tests.factories import auth_headers, make_project, make_user


def _site(db):
    return auth_headers(make_user(db, role=UserRole.site_manager))


def test_diary_create_and_duplicate_date(client, db):
    headers = _site(db)
    project = make_project(db)
    payload = {
        "entry_date": str(date.today()),
        "weather": "rain",
        "labour_headcount": 24,
        "work_done": "Cast first-floor slab, bays 3-4",
        "delays": "Rain stopped pour at 14:00",
    }
    res = client.post(f"/api/v1/projects/{project.id}/diary", json=payload, headers=headers)
    assert res.status_code == 201
    assert res.json()["weather"] == "rain"

    res = client.post(f"/api/v1/projects/{project.id}/diary", json=payload, headers=headers)
    assert res.status_code == 409

    # Same date on a different project is fine
    other = make_project(db)
    assert (
        client.post(f"/api/v1/projects/{other.id}/diary", json=payload, headers=headers).status_code
        == 201
    )


def test_diary_patch_to_occupied_date(client, db):
    headers = _site(db)
    project = make_project(db)
    d1 = str(date.today())
    d2 = str(date.today() - timedelta(days=1))
    e1 = client.post(
        f"/api/v1/projects/{project.id}/diary",
        json={"entry_date": d1, "work_done": "a"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/diary",
        json={"entry_date": d2, "work_done": "b"},
        headers=headers,
    )
    res = client.patch(f"/api/v1/diary/{e1['id']}", json={"entry_date": d2}, headers=headers)
    assert res.status_code == 409
    # Patching other fields on the same date is fine
    res = client.patch(f"/api/v1/diary/{e1['id']}", json={"labour_headcount": 30}, headers=headers)
    assert res.status_code == 200


def test_diary_write_requires_role(client, db):
    viewer = auth_headers(make_user(db, role=UserRole.viewer))
    project = make_project(db)
    res = client.post(
        f"/api/v1/projects/{project.id}/diary",
        json={"entry_date": str(date.today()), "work_done": "x"},
        headers=viewer,
    )
    assert res.status_code == 403


def test_issue_lifecycle(client, db):
    headers = _site(db)
    project = make_project(db)
    issue = client.post(
        f"/api/v1/projects/{project.id}/issues",
        json={"title": "Scaffold inspection overdue", "severity": "high"},
        headers=headers,
    ).json()
    assert issue["status"] == "open"

    res = client.post(
        f"/api/v1/issues/{issue['id']}/resolve",
        json={"resolution_notes": "Inspected and certified"},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "resolved"
    assert body["resolved_date"] is not None
    assert body["resolution_notes"] == "Inspected and certified"

    # Double resolve, edit-while-resolved -> 409
    assert (
        client.post(f"/api/v1/issues/{issue['id']}/resolve", json={}, headers=headers).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/v1/issues/{issue['id']}", json={"title": "X"}, headers=headers
        ).status_code
        == 409
    )

    # Reopen clears resolution
    res = client.post(f"/api/v1/issues/{issue['id']}/reopen", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "open"
    assert res.json()["resolved_date"] is None


def test_issue_status_filter(client, db):
    headers = _site(db)
    project = make_project(db)
    open_issue = client.post(
        f"/api/v1/projects/{project.id}/issues", json={"title": "Open one"}, headers=headers
    ).json()
    resolved = client.post(
        f"/api/v1/projects/{project.id}/issues", json={"title": "Fixed one"}, headers=headers
    ).json()
    client.post(f"/api/v1/issues/{resolved['id']}/resolve", json={}, headers=headers)

    res = client.get(f"/api/v1/projects/{project.id}/issues?status=open", headers=headers)
    titles = [i["title"] for i in res.json()["items"]]
    assert "Open one" in titles and "Fixed one" not in titles
    assert open_issue["id"]
