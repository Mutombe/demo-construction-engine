"""Work captured on a phone with no signal, and what happens when it lands.

The two things worth proving are that a retry does not write the day twice,
and that a device which has been out of range does not overwrite what someone
else already put on the server.
"""

import uuid
from datetime import date, timedelta

from app.common.enums import UserRole
from tests.factories import auth_headers, make_project, make_user

TODAY = date(2026, 10, 5)


def _foreman(db):
    return auth_headers(make_user(db, role=UserRole.site_manager))


def _push(client, headers, ops, device="phone-7"):
    res = client.post(
        "/api/v1/sync/push",
        json={"device_id": device, "operations": ops},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


def _diary_op(project, work="Blinding to grid A-C", **kw):
    return {
        "client_op_id": str(uuid.uuid4()),
        "op_type": "diary_entry",
        "captured_at": "2026-10-05T14:30:00Z",
        "payload": {
            "project_id": str(project.id),
            "entry_date": str(TODAY),
            "work_done": work,
            **kw,
        },
    }


# --- Nothing is written twice ------------------------------------------------


def test_a_capture_lands_once(client, db):
    headers = _foreman(db)
    project = make_project(db)
    op = _diary_op(project)

    first = _push(client, headers, [op])
    assert first["applied"] == 1
    entry_id = first["results"][0]["entity_id"]

    # The phone lost the response and sends its backlog again.
    second = _push(client, headers, [op])
    assert second["duplicate"] == 1
    assert second["applied"] == 0
    assert second["results"][0]["entity_id"] == entry_id

    listing = client.get(
        f"/api/v1/projects/{project.id}/diary", headers=headers
    ).json()
    assert len([e for e in listing["items"] if e["entry_date"] == str(TODAY)]) == 1


def test_the_same_backlog_from_two_devices_is_still_two_captures(client, db):
    """Idempotency is per capture, not per person: two foremen each writing
    their own diary are two records, and only one can own the day."""
    headers = _foreman(db)
    project = make_project(db)

    _push(client, headers, [_diary_op(project, "Blinding poured")], device="phone-a")
    result = _push(client, headers, [_diary_op(project, "Rebar fixed")], device="phone-b")

    assert result["merged"] == 1


# --- Nothing is silently lost ------------------------------------------------


def test_a_second_account_of_the_day_is_kept_not_overwritten(client, db):
    headers = _foreman(db)
    project = make_project(db)

    _push(client, headers, [_diary_op(project, "Blinding poured to grid A-C")])
    _push(client, headers, [_diary_op(project, "Rebar fixed to raft")])

    entries = client.get(f"/api/v1/projects/{project.id}/diary", headers=headers).json()
    entry = next(e for e in entries["items"] if e["entry_date"] == str(TODAY))

    assert "Blinding poured to grid A-C" in entry["work_done"]
    assert "Rebar fixed to raft" in (entry["notes"] or "")


def test_blank_fields_are_filled_but_written_ones_are_not_replaced(client, db):
    headers = _foreman(db)
    project = make_project(db)

    _push(client, headers, [_diary_op(project, "Blinding poured", delays="")])
    _push(
        client,
        headers,
        [_diary_op(project, "Blinding poured", delays="Rain from 11am")],
    )

    entries = client.get(f"/api/v1/projects/{project.id}/diary", headers=headers).json()
    entry = next(e for e in entries["items"] if e["entry_date"] == str(TODAY))
    assert entry["delays"] == "Rain from 11am"

    _push(
        client,
        headers,
        [_diary_op(project, "Blinding poured", delays="No delays")],
    )
    entries = client.get(f"/api/v1/projects/{project.id}/diary", headers=headers).json()
    entry = next(e for e in entries["items"] if e["entry_date"] == str(TODAY))
    assert entry["delays"] == "Rain from 11am"
    assert "No delays" in (entry["notes"] or "")


# --- One bad capture does not block the rest ---------------------------------


def test_a_refused_capture_does_not_stop_the_queue(client, db):
    headers = _foreman(db)
    project = make_project(db)

    bad = {
        "client_op_id": str(uuid.uuid4()),
        "op_type": "site_issue",
        "payload": {"project_id": str(project.id), "title": ""},
    }
    good = {
        "client_op_id": str(uuid.uuid4()),
        "op_type": "site_issue",
        "payload": {"project_id": str(project.id), "title": "Scaffold tie missing at level 3"},
    }

    result = _push(client, headers, [bad, good])
    assert result["rejected"] == 1
    assert result["applied"] == 1

    issues = client.get(f"/api/v1/projects/{project.id}/issues", headers=headers).json()
    assert any(i["title"].startswith("Scaffold tie") for i in issues["items"])


def test_a_refused_capture_is_kept_with_its_reason(client, db):
    headers = _foreman(db)
    project = make_project(db)

    _push(
        client,
        headers,
        [
            {
                "client_op_id": str(uuid.uuid4()),
                "op_type": "diary_labour",
                "payload": {
                    "project_id": str(project.id),
                    "entry_date": str(TODAY),
                    "lines": [{"worker_id": str(uuid.uuid4()), "quantity": "8"}],
                },
            }
        ],
    )

    rejected = client.get("/api/v1/sync/rejected", headers=headers).json()
    assert len(rejected) == 1
    assert "no diary" in rejected[0]["detail"].lower()


def test_an_unknown_capture_type_is_refused_rather_than_ignored(client, db):
    headers = _foreman(db)
    result = _push(
        client,
        headers,
        [{"client_op_id": str(uuid.uuid4()), "op_type": "moon_phase", "payload": {}}],
    )
    assert result["rejected"] == 1
    assert "moon_phase" in result["results"][0]["detail"]


# --- Labour ------------------------------------------------------------------


def test_a_recount_of_the_same_worker_corrects_the_hours(client, db):
    from tests.factories import make_worker

    headers = _foreman(db)
    project = make_project(db)
    worker = make_worker(db)
    _push(client, headers, [_diary_op(project)])

    def labour(quantity):
        return {
            "client_op_id": str(uuid.uuid4()),
            "op_type": "diary_labour",
            "payload": {
                "project_id": str(project.id),
                "entry_date": str(TODAY),
                "lines": [{"worker_id": str(worker.id), "quantity": quantity}],
            },
        }

    _push(client, headers, [labour("6")])
    _push(client, headers, [labour("8")])

    entries = client.get(f"/api/v1/projects/{project.id}/diary", headers=headers).json()
    entry_id = next(e for e in entries["items"] if e["entry_date"] == str(TODAY))["id"]
    detail = client.get(f"/api/v1/diary/{entry_id}", headers=headers).json()
    assert len(detail["labour"]) == 1
    assert float(detail["labour"][0]["quantity"]) == 8.0


# --- What the phone takes with it --------------------------------------------


def test_the_bootstrap_pack_carries_what_a_form_needs(client, db):
    from tests.factories import make_worker

    headers = _foreman(db)
    project = make_project(db)
    make_worker(db, full_name="Tendai Moyo")

    pack = client.get(f"/api/v1/sync/bootstrap/{project.id}", headers=headers).json()
    assert pack["project_code"] == project.code
    assert any(w["full_name"] == "Tendai Moyo" for w in pack["workers"])
    assert "server_time" in pack


def test_the_bootstrap_pack_refuses_a_project_that_is_not_there(client, db):
    headers = _foreman(db)
    res = client.get(f"/api/v1/sync/bootstrap/{uuid.uuid4()}", headers=headers)
    assert res.status_code == 404


# --- Plant captured in the field ---------------------------------------------


def test_a_meter_reading_captured_on_site_is_applied(client, db):
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    machine = client.post(
        "/api/v1/equipment",
        json={"code": "PLT-900", "name": "Roller", "current_meter": "500"},
        headers=headers,
    ).json()

    result = _push(
        client,
        headers,
        [
            {
                "client_op_id": str(uuid.uuid4()),
                "op_type": "meter_reading",
                "payload": {
                    "equipment_id": machine["id"],
                    "meter": "540",
                    "reading_date": str(TODAY),
                },
            }
        ],
    )
    assert result["applied"] == 1

    after = client.get(f"/api/v1/equipment/{machine['id']}", headers=headers).json()
    assert float(after["current_meter"]) == 540.0


def test_a_meter_that_went_backwards_is_refused_with_its_reason(client, db):
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    machine = client.post(
        "/api/v1/equipment",
        json={"code": "PLT-901", "name": "Roller", "current_meter": "500"},
        headers=headers,
    ).json()

    result = _push(
        client,
        headers,
        [
            {
                "client_op_id": str(uuid.uuid4()),
                "op_type": "meter_reading",
                "payload": {
                    "equipment_id": machine["id"],
                    "meter": "400",
                    "reading_date": str(TODAY + timedelta(days=1)),
                },
            }
        ],
    )
    assert result["rejected"] == 1
    assert result["results"][0]["detail"]
