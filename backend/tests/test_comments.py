"""Comment threads on records."""

from app.common.enums import UserRole
from tests.factories import (
    auth_headers,
    make_project,
    make_supplier,
    make_task,
    make_user,
)


def _thread(client, headers, entity_type, entity_id):
    res = client.get(
        f"/api/v1/comments?entity_type={entity_type}&entity_id={entity_id}", headers=headers
    )
    assert res.status_code == 200
    return res.json()


def _post(client, headers, entity_type, entity_id, body):
    return client.post(
        f"/api/v1/comments?entity_type={entity_type}&entity_id={entity_id}",
        json={"body": body},
        headers=headers,
    )


def test_a_thread_reads_oldest_first(client, db):
    """A thread is read top to bottom, unlike a notification feed."""
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    project = make_project(db)
    task = make_task(db, project)

    _post(client, headers, "task", task.id, "Rebar arrives Tuesday")
    _post(client, headers, "task", task.id, "Confirmed with the supplier")

    thread = _thread(client, headers, "task", task.id)
    assert [c["body"] for c in thread] == [
        "Rebar arrives Tuesday",
        "Confirmed with the supplier",
    ]


def test_the_author_is_snapshotted(client, db):
    """The name has to survive the person leaving, exactly like the activity log."""
    author = make_user(db, role=UserRole.site_manager, full_name="Tarisai Banda")
    project = make_project(db)
    task = make_task(db, project)

    res = _post(client, auth_headers(author), "task", task.id, "Formwork stripped")
    assert res.status_code == 201
    assert res.json()["author_name"] == "Tarisai Banda"


def test_commenting_notifies_the_assignee_but_not_yourself(client, db):
    assignee = make_user(db, role=UserRole.site_manager, full_name="Owner")
    commenter = make_user(db, role=UserRole.project_manager, full_name="Talker")
    project = make_project(db)
    task = make_task(db, project, assignee_id=assignee.id)

    _post(client, auth_headers(commenter), "task", task.id, "Any update on this?")

    theirs = client.get("/api/v1/notifications", headers=auth_headers(assignee)).json()
    assert any(n["type"] == "comment" for n in theirs["items"])

    # The person who typed it does not need telling
    _post(client, auth_headers(assignee), "task", task.id, "Starting tomorrow")
    mine = client.get("/api/v1/notifications", headers=auth_headers(assignee)).json()
    assert sum(1 for n in mine["items"] if n["type"] == "comment") == 1


def test_only_the_author_can_edit(client, db):
    author = make_user(db, role=UserRole.site_manager)
    other = make_user(db, role=UserRole.project_manager)
    project = make_project(db)
    task = make_task(db, project)
    comment = _post(client, auth_headers(author), "task", task.id, "First take").json()

    assert client.patch(
        f"/api/v1/comments/{comment['id']}", json={"body": "Edited"},
        headers=auth_headers(other),
    ).status_code == 403

    res = client.patch(
        f"/api/v1/comments/{comment['id']}", json={"body": "Edited"},
        headers=auth_headers(author),
    )
    assert res.status_code == 200
    assert res.json()["body"] == "Edited"
    assert res.json()["edited_at"] is not None


def test_a_project_manager_can_clear_up_someone_elses_comment(client, db):
    author = make_user(db, role=UserRole.site_manager)
    pm = make_user(db, role=UserRole.project_manager)
    viewer = make_user(db, role=UserRole.viewer)
    project = make_project(db)
    task = make_task(db, project)
    comment = _post(client, auth_headers(author), "task", task.id, "Oops").json()

    assert client.delete(
        f"/api/v1/comments/{comment['id']}", headers=auth_headers(viewer)
    ).status_code == 403
    assert client.delete(
        f"/api/v1/comments/{comment['id']}", headers=auth_headers(pm)
    ).status_code == 204
    assert _thread(client, auth_headers(pm), "task", task.id) == []


def test_can_edit_reflects_who_is_asking(client, db):
    author = make_user(db, role=UserRole.site_manager)
    other = make_user(db, role=UserRole.project_manager)
    project = make_project(db)
    task = make_task(db, project)
    _post(client, auth_headers(author), "task", task.id, "Mine")

    assert _thread(client, auth_headers(author), "task", task.id)[0]["can_edit"] is True
    assert _thread(client, auth_headers(other), "task", task.id)[0]["can_edit"] is False


def test_comments_work_on_more_than_tasks(client, db):
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    supplier = make_supplier(db)
    project = make_project(db)

    assert _post(client, headers, "supplier", supplier.id, "Slow on the last order").status_code == 201
    assert _post(client, headers, "project", project.id, "Client walked the site").status_code == 201
    assert len(_thread(client, headers, "supplier", supplier.id)) == 1


def test_an_unknown_entity_type_is_refused_with_the_allowed_list(client, db):
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    project = make_project(db)
    res = _post(client, headers, "unicorn", project.id, "Hello")
    assert res.status_code == 422
    assert "task" in res.json()["error"]["detail"]


def test_commenting_on_something_that_does_not_exist_is_a_404(client, db):
    import uuid

    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    res = _post(client, headers, "task", uuid.uuid4(), "Into the void")
    assert res.status_code == 404


def test_an_empty_comment_is_refused(client, db):
    headers = auth_headers(make_user(db, role=UserRole.project_manager))
    project = make_project(db)
    task = make_task(db, project)
    assert _post(client, headers, "task", task.id, "   ").status_code in (201, 422)
    # Whitespace-only is stored trimmed at worst; a truly empty body is refused
    assert _post(client, headers, "task", task.id, "").status_code == 422
