from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.common.enums import CostSource, UserRole
from app.modules.costs.models import CostEntry
from tests.factories import (
    auth_headers,
    fake_uuid,
    make_boq_item,
    make_boq_section,
    make_project,
    make_user,
)


def _claim_payload(**kw):
    return {
        "category": "fuel",
        "expense_date": str(date.today()),
        "amount": "120.50",
        "description": "Diesel for generator",
        **kw,
    }


def test_submit_claim_and_numbering(client, db):
    site = auth_headers(make_user(db, role=UserRole.site_manager))
    project = make_project(db)
    year = date.today().year
    c1 = client.post(f"/api/v1/projects/{project.id}/expenses", json=_claim_payload(), headers=site)
    assert c1.status_code == 201
    assert c1.json()["doc_number"] == f"EXP-{year}-001"
    c2 = client.post(f"/api/v1/projects/{project.id}/expenses", json=_claim_payload(), headers=site)
    assert c2.json()["doc_number"] == f"EXP-{year}-002"
    assert c1.json()["status"] == "pending"


def test_claim_cross_project_boq_rejected(client, db):
    site = auth_headers(make_user(db, role=UserRole.site_manager))
    project = make_project(db)
    other = make_project(db)
    other_section = make_boq_section(db, other)
    foreign_item = make_boq_item(db, other_section)
    res = client.post(
        f"/api/v1/projects/{project.id}/expenses",
        json=_claim_payload(boq_item_id=str(foreign_item.id)),
        headers=site,
    )
    assert res.status_code == 422


def test_approve_posts_cost_entry(client, db):
    claimant = make_user(db, role=UserRole.site_manager)
    approver = make_user(db, role=UserRole.project_manager)
    project = make_project(db)
    section = make_boq_section(db, project)
    boq_item = make_boq_item(db, section)

    claim = client.post(
        f"/api/v1/projects/{project.id}/expenses",
        json=_claim_payload(boq_item_id=str(boq_item.id)),
        headers=auth_headers(claimant),
    ).json()

    res = client.post(f"/api/v1/expenses/{claim['id']}/approve", headers=auth_headers(approver))
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "approved"
    assert body["cost_entry_id"] is not None
    assert body["approver_name"] == approver.full_name

    entries = db.scalars(select(CostEntry).where(CostEntry.project_id == project.id)).all()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.source == CostSource.expense
    assert entry.amount == Decimal("120.50")
    assert entry.boq_item_id == boq_item.id
    assert entry.reference == claim["doc_number"]
    assert str(entry.entry_date) == claim["expense_date"]

    # Post-decision edits blocked
    assert (
        client.post(
            f"/api/v1/expenses/{claim['id']}/approve", headers=auth_headers(approver)
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/v1/expenses/{claim['id']}",
            json={"amount": "999"},
            headers=auth_headers(claimant),
        ).status_code
        == 409
    )


def test_self_approval_blocked(client, db):
    pm = make_user(db, role=UserRole.project_manager)
    admin = make_user(db, role=UserRole.admin)
    other_admin = make_user(db, role=UserRole.admin)
    project = make_project(db)

    pm_claim = client.post(
        f"/api/v1/projects/{project.id}/expenses", json=_claim_payload(), headers=auth_headers(pm)
    ).json()
    assert (
        client.post(
            f"/api/v1/expenses/{pm_claim['id']}/approve", headers=auth_headers(pm)
        ).status_code
        == 409
    )

    admin_claim = client.post(
        f"/api/v1/projects/{project.id}/expenses",
        json=_claim_payload(),
        headers=auth_headers(admin),
    ).json()
    assert (
        client.post(
            f"/api/v1/expenses/{admin_claim['id']}/approve", headers=auth_headers(admin)
        ).status_code
        == 409
    )
    # A different admin can approve it
    assert (
        client.post(
            f"/api/v1/expenses/{admin_claim['id']}/approve", headers=auth_headers(other_admin)
        ).status_code
        == 200
    )


def test_reject_requires_reason_and_posts_nothing(client, db):
    claimant = make_user(db, role=UserRole.site_manager)
    approver = make_user(db, role=UserRole.project_manager)
    project = make_project(db)
    claim = client.post(
        f"/api/v1/projects/{project.id}/expenses",
        json=_claim_payload(),
        headers=auth_headers(claimant),
    ).json()

    assert (
        client.post(
            f"/api/v1/expenses/{claim['id']}/reject", json={}, headers=auth_headers(approver)
        ).status_code
        == 422
    )
    res = client.post(
        f"/api/v1/expenses/{claim['id']}/reject",
        json={"reason": "No receipt provided"},
        headers=auth_headers(approver),
    )
    assert res.status_code == 200
    assert res.json()["rejection_reason"] == "No receipt provided"
    assert db.scalars(select(CostEntry).where(CostEntry.project_id == project.id)).all() == []


def test_claimant_edit_rules(client, db):
    claimant = make_user(db, role=UserRole.site_manager)
    other = make_user(db, role=UserRole.site_manager)
    project = make_project(db)
    claim = client.post(
        f"/api/v1/projects/{project.id}/expenses",
        json=_claim_payload(),
        headers=auth_headers(claimant),
    ).json()

    # Claimant edits own pending claim
    assert (
        client.patch(
            f"/api/v1/expenses/{claim['id']}",
            json={"amount": "150.00"},
            headers=auth_headers(claimant),
        ).status_code
        == 200
    )
    # Another site manager cannot edit it
    assert (
        client.patch(
            f"/api/v1/expenses/{claim['id']}",
            json={"amount": "1.00"},
            headers=auth_headers(other),
        ).status_code
        == 403
    )
    # Claimant cancels
    assert (
        client.post(
            f"/api/v1/expenses/{claim['id']}/cancel", headers=auth_headers(claimant)
        ).status_code
        == 200
    )


def test_viewer_cannot_submit(client, db):
    viewer = auth_headers(make_user(db, role=UserRole.viewer))
    project = make_project(db)
    assert (
        client.post(
            f"/api/v1/projects/{project.id}/expenses", json=_claim_payload(), headers=viewer
        ).status_code
        == 403
    )


def test_queue_filters(client, db):
    claimant = make_user(db, role=UserRole.site_manager)
    project = make_project(db)
    client.post(
        f"/api/v1/projects/{project.id}/expenses",
        json=_claim_payload(),
        headers=auth_headers(claimant),
    )
    res = client.get("/api/v1/expenses?status=pending", headers=auth_headers(claimant))
    assert res.json()["total"] == 1
    res = client.get("/api/v1/expenses?mine=true", headers=auth_headers(claimant))
    assert res.json()["total"] == 1
    stranger = make_user(db, role=UserRole.site_manager)
    res = client.get("/api/v1/expenses?mine=true", headers=auth_headers(stranger))
    assert res.json()["total"] == 0
    assert fake_uuid()  # keep import used
