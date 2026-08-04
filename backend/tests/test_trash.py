"""Deleting keeps a copy, and the copy can be put back."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.common.enums import UserRole
from app.modules.boq.models import BoqItem, BoqSection
from app.modules.clients.models import Client
from app.modules.tasks.models import Task
from tests.factories import (
    auth_headers,
    make_boq_item,
    make_boq_section,
    make_client_record,
    make_project,
    make_supplier,
    make_task,
    make_user,
)


def _admin(db):
    return auth_headers(make_user(db, role=UserRole.admin))


def _trash(client, headers, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    res = client.get(f"/api/v1/admin/trash?{query}", headers=headers)
    assert res.status_code == 200
    return res.json()


def test_a_deleted_client_lands_in_the_trash(client, db):
    admin = _admin(db)
    victim = make_client_record(db, name="Harare Holdings")

    assert client.delete(f"/api/v1/clients/{victim.id}", headers=admin).status_code == 204
    assert db.get(Client, victim.id) is None

    entries = _trash(client, admin)["items"]
    entry = next(e for e in entries if e["entity_id"] == str(victim.id))
    assert entry["entity_type"] == "client"
    assert entry["label"] == "Harare Holdings"
    assert entry["restorable"] is True


def test_restoring_brings_the_record_back_with_its_values(client, db):
    """Not just the row: the same id, and every field it had."""
    admin = _admin(db)
    victim = make_client_record(
        db, name="Restored Ltd", email="hello@restored.example", phone="+263 77 000 0000"
    )
    original_id = victim.id

    client.delete(f"/api/v1/clients/{original_id}", headers=admin)
    entry = next(e for e in _trash(client, admin)["items"] if e["entity_id"] == str(original_id))

    res = client.post(f"/api/v1/admin/trash/{entry['id']}/restore", headers=admin)
    assert res.status_code == 200

    db.expire_all()
    back = db.get(Client, original_id)
    assert back is not None
    assert back.name == "Restored Ltd"
    assert back.email == "hello@restored.example"
    assert back.phone == "+263 77 000 0000"

    # And it leaves the trash listing, rather than offering a second restore
    assert all(e["entity_id"] != str(original_id) for e in _trash(client, admin)["items"])


def test_money_survives_the_round_trip(client, db):
    """Decimals through JSON is exactly where a cent goes missing, so this
    asserts the value is identical rather than merely close."""
    admin = _admin(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section, quantity=Decimal("13.750"), rate=Decimal("1234.56"))
    item_id, amount = item.id, item.amount

    client.delete(f"/api/v1/boq/items/{item_id}", headers=admin)
    entry = next(e for e in _trash(client, admin)["items"] if e["entity_id"] == str(item_id))
    client.post(f"/api/v1/admin/trash/{entry['id']}/restore", headers=admin)

    db.expire_all()
    back = db.get(BoqItem, item_id)
    assert back.quantity == Decimal("13.750")
    assert back.rate == Decimal("1234.56")
    assert back.amount == amount


def test_children_that_cascade_come_back_too(client, db):
    """A BOQ section takes its items with it, so restoring the section that
    gave back an empty shell would be worse than not offering restore at all."""
    admin = _admin(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    first = make_boq_item(db, section, item_code="A1")
    second = make_boq_item(db, section, item_code="A2")
    section_id, item_ids = section.id, {first.id, second.id}

    assert client.delete(f"/api/v1/boq/sections/{section_id}", headers=admin).status_code == 204
    db.expire_all()
    assert db.scalars(select(BoqItem.id).where(BoqItem.id.in_(item_ids))).all() == []

    entry = next(e for e in _trash(client, admin)["items"] if e["entity_id"] == str(section_id))
    assert entry["row_count"] == 3  # the section and both items
    client.post(f"/api/v1/admin/trash/{entry['id']}/restore", headers=admin)

    db.expire_all()
    assert db.get(BoqSection, section_id) is not None
    assert set(db.scalars(select(BoqItem.id).where(BoqItem.id.in_(item_ids)))) == item_ids


def test_restore_refuses_when_the_parent_is_gone(client, db):
    """The task's project was deleted afterwards: putting the task back would
    fail on the foreign key, so it is refused with a reason instead."""
    admin = _admin(db)
    project = make_project(db)
    task = make_task(db, project, name="Pour slab")
    task_id = task.id

    client.delete(f"/api/v1/tasks/{task_id}", headers=admin)
    entry = next(e for e in _trash(client, admin)["items"] if e["entity_id"] == str(task_id))
    assert client.delete(f"/api/v1/projects/{project.id}", headers=admin).status_code == 204

    res = client.post(f"/api/v1/admin/trash/{entry['id']}/restore", headers=admin)
    assert res.status_code == 422
    assert "something it depended on is gone" in res.json()["error"]["detail"]
    db.expire_all()
    assert db.get(Task, task_id) is None


def test_the_same_entry_cannot_be_restored_twice(client, db):
    admin = _admin(db)
    victim = make_client_record(db, name="Once Only")
    client.delete(f"/api/v1/clients/{victim.id}", headers=admin)
    entry = next(e for e in _trash(client, admin)["items"] if e["entity_id"] == str(victim.id))

    assert client.post(
        f"/api/v1/admin/trash/{entry['id']}/restore", headers=admin
    ).status_code == 200
    second = client.post(f"/api/v1/admin/trash/{entry['id']}/restore", headers=admin)
    assert second.status_code == 409


def test_purging_is_final(client, db):
    admin = _admin(db)
    victim = make_client_record(db, name="Gone For Good")
    client.delete(f"/api/v1/clients/{victim.id}", headers=admin)
    entry = next(e for e in _trash(client, admin)["items"] if e["entity_id"] == str(victim.id))

    assert client.delete(f"/api/v1/admin/trash/{entry['id']}", headers=admin).status_code == 204
    assert all(e["id"] != entry["id"] for e in _trash(client, admin)["items"])
    assert client.post(
        f"/api/v1/admin/trash/{entry['id']}/restore", headers=admin
    ).status_code == 404
    db.expire_all()
    assert db.get(Client, victim.id) is None


def test_who_deleted_it_is_recorded(client, db):
    admin = _admin(db)
    pm = make_user(db, role=UserRole.project_manager, full_name="Chipo Nyoni")
    victim = make_client_record(db, name="Traced")

    client.delete(f"/api/v1/clients/{victim.id}", headers=auth_headers(pm))
    entry = next(e for e in _trash(client, admin)["items"] if e["entity_id"] == str(victim.id))
    assert entry["deleted_by_name"] == "Chipo Nyoni"


def test_trash_can_be_filtered_by_type(client, db):
    admin = _admin(db)
    project = make_project(db)
    make_supplier(db)
    victim = make_client_record(db, name="Typed")
    task = make_task(db, project, name="Filtered task")

    client.delete(f"/api/v1/clients/{victim.id}", headers=admin)
    client.delete(f"/api/v1/tasks/{task.id}", headers=admin)

    only_tasks = _trash(client, admin, entity_type="task")
    assert only_tasks["total"] >= 1
    assert all(e["entity_type"] == "task" for e in only_tasks["items"])

    types = client.get("/api/v1/admin/trash/types", headers=admin).json()
    assert {"client", "task"} <= set(types)


def test_a_restore_is_written_to_the_activity_log(client, db):
    admin = _admin(db)
    victim = make_client_record(db, name="Audited")
    client.delete(f"/api/v1/clients/{victim.id}", headers=admin)
    entry = next(e for e in _trash(client, admin)["items"] if e["entity_id"] == str(victim.id))
    client.post(f"/api/v1/admin/trash/{entry['id']}/restore", headers=admin)

    entries = client.get("/api/v1/admin/activity", headers=admin).json()["items"]
    assert any(e["action"] == "record_restored" and "Audited" in e["summary"] for e in entries)


def test_trash_is_admin_only(client, db):
    victim_headers = auth_headers(make_user(db, role=UserRole.project_manager))
    assert client.get("/api/v1/admin/trash", headers=victim_headers).status_code == 403
    assert (
        client.get("/api/v1/admin/trash/types", headers=victim_headers).status_code == 403
    )


def test_a_diary_entry_keeps_its_date_through_the_trash(client, db):
    """Dates go through JSON as strings; this is the guard that they come back
    as dates and not as text the rest of the app cannot compare."""
    admin = _admin(db)
    project = make_project(db)
    entry_date = date(2026, 3, 14)
    created = client.post(
        f"/api/v1/projects/{project.id}/diary",
        json={"entry_date": str(entry_date), "work_done": "Formwork to grid B"},
        headers=admin,
    ).json()

    client.delete(f"/api/v1/diary/{created['id']}", headers=admin)
    trashed = next(
        e for e in _trash(client, admin)["items"] if e["entity_id"] == created["id"]
    )
    assert client.post(
        f"/api/v1/admin/trash/{trashed['id']}/restore", headers=admin
    ).status_code == 200

    back = client.get(f"/api/v1/diary/{created['id']}", headers=admin).json()
    assert back["entry_date"] == str(entry_date)
    assert back["work_done"] == "Formwork to grid B"
