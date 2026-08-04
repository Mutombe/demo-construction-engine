"""Global search behind the command palette, and sidebar work counts."""

from datetime import date, timedelta
from decimal import Decimal

from app.common.enums import UserRole
from tests.factories import (
    auth_headers,
    make_boq_item,
    make_boq_section,
    make_client_record,
    make_project,
    make_supplier,
    make_user,
    make_worker,
)


def _pm(db):
    return auth_headers(make_user(db, role=UserRole.project_manager))


def _search(client, headers, q):
    res = client.get(f"/api/v1/search?q={q}", headers=headers)
    assert res.status_code == 200
    return res.json()


def test_finds_projects_clients_and_suppliers(client, db):
    headers = _pm(db)
    customer = make_client_record(db, name="Riverside Property Group")
    make_project(db, client=customer, code="PRJ-2026-001", name="Riverside Apartments")
    make_supplier(db, name="Riverside Aggregates")

    body = _search(client, headers, "riverside")
    types = {hit["type"] for hit in body["hits"]}
    assert {"project", "client", "supplier"} <= types
    project = next(h for h in body["hits"] if h["type"] == "project")
    assert project["code"] == "PRJ-2026-001"
    assert project["url"] == f"/projects/{project['id']}"
    assert project["sublabel"] == "Riverside Property Group"


def test_exact_document_number_ranks_first(client, db):
    headers = _pm(db)
    project = make_project(db, name="Depot")
    supplier = make_supplier(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section)
    po = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "items": [
                {
                    "boq_item_id": str(item.id),
                    "description": "Cement",
                    "unit": "bag",
                    "quantity": "10",
                    "unit_price": "10.00",
                }
            ],
        },
        headers=headers,
    ).json()

    body = _search(client, headers, po["doc_number"].lower())
    # Someone typing a doc number wants that document at the top
    assert body["hits"][0]["code"] == po["doc_number"]
    assert body["hits"][0]["type"] == "purchase_order"
    assert body["hits"][0]["url"] == f"/procurement/pos/{po['id']}"


def test_stock_items_are_findable_by_barcode(client, db):
    headers = auth_headers(make_user(db, role=UserRole.procurement_officer))
    item = client.post(
        "/api/v1/stock-items",
        json={
            "code": "CEM-425",
            "name": "Cement 42.5N",
            "unit": "bag",
            "barcode": "6001234500018",
        },
        headers=headers,
    ).json()

    body = _search(client, headers, "6001234500018")
    assert body["hits"][0]["id"] == item["id"]
    assert body["hits"][0]["url"] == f"/inventory/{item['id']}"


def test_short_queries_return_nothing(client, db):
    headers = _pm(db)
    make_project(db, name="Alpha")
    assert _search(client, headers, "a")["hits"] == []
    assert _search(client, headers, "")["hits"] == []


def test_workers_are_hidden_from_roles_without_payroll_access(client, db):
    make_worker(db, full_name="Tapiwa Moyo", trade="Bricklayer")

    pm_hits = _search(client, _pm(db), "tapiwa")["hits"]
    assert any(h["type"] == "worker" for h in pm_hits)

    for role in (UserRole.site_manager, UserRole.procurement_officer, UserRole.viewer):
        hits = _search(client, auth_headers(make_user(db, role=role)), "tapiwa")["hits"]
        assert not any(h["type"] == "worker" for h in hits), role


def test_search_requires_authentication(client, db):
    assert client.get("/api/v1/search?q=riverside").status_code == 401


# --- Nav counts --------------------------------------------------------------


def _counts(client, headers):
    res = client.get("/api/v1/dashboard/nav-counts", headers=headers)
    assert res.status_code == 200
    return {item["path"]: item for item in res.json()["items"]}


def test_open_requisitions_badge_procurement_queue(client, db):
    project = make_project(db)
    site = auth_headers(make_user(db, role=UserRole.site_manager))
    client.post(
        f"/api/v1/projects/{project.id}/requisitions",
        json={"items": [{"description": "Cement", "unit": "bag", "quantity": "10"}]},
        headers=site,
    )

    procurement = auth_headers(make_user(db, role=UserRole.procurement_officer))
    counts = _counts(client, procurement)
    assert counts["/procurement/requisitions"]["count"] == 1
    assert counts["/procurement/requisitions"]["tone"] == "warning"


def test_actioned_requests_stop_being_counted(client, db):
    project = make_project(db)
    site = auth_headers(make_user(db, role=UserRole.site_manager))
    requisition = client.post(
        f"/api/v1/projects/{project.id}/requisitions",
        json={"items": [{"description": "Sand", "unit": "m3", "quantity": "5"}]},
        headers=site,
    ).json()
    procurement = auth_headers(make_user(db, role=UserRole.procurement_officer))
    assert _counts(client, procurement)["/procurement/requisitions"]["count"] == 1

    client.post(
        f"/api/v1/requisitions/{requisition['id']}/convert-to-rfq", headers=procurement
    )
    # A badge that stays lit after the work is done teaches people to ignore it
    assert "/procurement/requisitions" not in _counts(client, procurement)


def test_overdue_deliveries_badge(client, db):
    headers = _pm(db)
    project = make_project(db)
    po = client.post(
        f"/api/v1/projects/{project.id}/purchase-orders",
        json={
            "supplier_id": str(make_supplier(db).id),
            "expected_delivery": str(date.today() - timedelta(days=3)),
            "items": [
                {"description": "Steel", "unit": "t", "quantity": "1", "unit_price": "10"}
            ],
        },
        headers=headers,
    ).json()
    assert "/procurement" not in _counts(client, headers)  # draft is not late

    client.post(f"/api/v1/purchase-orders/{po['id']}/issue", headers=headers)
    counts = _counts(client, headers)
    assert counts["/procurement"]["count"] == 1
    assert counts["/procurement"]["tone"] == "danger"


def test_expense_approvals_only_reach_approvers(client, db):
    project = make_project(db)
    site_user = make_user(db, role=UserRole.site_manager)
    site = auth_headers(site_user)
    res = client.post(
        f"/api/v1/projects/{project.id}/expenses",
        json={
            "category": "materials",
            "expense_date": str(date.today()),
            "amount": "50.00",
            "description": "Fuel for the mixer",
        },
        headers=site,
    )
    assert res.status_code == 201, res.text

    assert _counts(client, _pm(db))["/expenses"]["count"] == 1
    # The person who submitted it has nothing to approve
    assert "/expenses" not in _counts(client, site)


def test_viewer_sees_no_badges(client, db):
    project = make_project(db)
    site = auth_headers(make_user(db, role=UserRole.site_manager))
    client.post(
        f"/api/v1/projects/{project.id}/requisitions",
        json={"items": [{"description": "Cement", "unit": "bag", "quantity": "1"}]},
        headers=site,
    )
    viewer = auth_headers(make_user(db, role=UserRole.viewer))
    assert _counts(client, viewer) == {}


def test_low_stock_badge(client, db):
    headers = auth_headers(make_user(db, role=UserRole.procurement_officer))
    item = client.post(
        "/api/v1/stock-items",
        json={"code": "LOW-1", "name": "Low item", "unit": "ea", "reorder_level": "100"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "10", "unit_cost": "1.00"},
        headers=headers,
    )
    counts = _counts(client, headers)
    assert counts["/inventory"]["count"] == 1

    # Restocking clears it
    client.post(
        f"/api/v1/stock-items/{item['id']}/goods-in",
        json={"quantity": "500", "unit_cost": "1.00"},
        headers=headers,
    )
    assert "/inventory" not in _counts(client, headers)


def test_site_manager_sees_only_their_own_open_requests(client, db):
    project = make_project(db)
    mine = make_user(db, role=UserRole.site_manager)
    theirs = make_user(db, role=UserRole.site_manager)
    for headers in (auth_headers(mine), auth_headers(theirs)):
        client.post(
            f"/api/v1/projects/{project.id}/requisitions",
            json={"items": [{"description": "Cement", "unit": "bag", "quantity": "1"}]},
            headers=headers,
        )

    counts = _counts(client, auth_headers(mine))
    assert counts["/procurement/requisitions"]["count"] == 1  # not 2
    assert counts["/procurement/requisitions"]["tone"] == "default"
    # Procurement, who must action both, sees both
    procurement = auth_headers(make_user(db, role=UserRole.procurement_officer))
    assert _counts(client, procurement)["/procurement/requisitions"]["count"] == 2


def test_nav_counts_expose_only_actionable_paths(client, db):
    """Guard: a badge must map to a real sidebar destination."""
    known = {
        "/procurement",
        "/procurement/requisitions",
        "/inventory",
        "/expenses",
        "/inbox",
    }
    project = make_project(db)
    site = auth_headers(make_user(db, role=UserRole.site_manager))
    client.post(
        f"/api/v1/projects/{project.id}/requisitions",
        json={"items": [{"description": "Cement", "unit": "bag", "quantity": "1"}]},
        headers=site,
    )
    for role in UserRole:
        counts = _counts(client, auth_headers(make_user(db, role=role)))
        assert set(counts) <= known, role
        assert all(item["count"] > 0 for item in counts.values()), role
