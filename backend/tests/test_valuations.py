from datetime import date
from decimal import Decimal

from app.common.enums import UserRole
from tests.factories import auth_headers, make_project, make_task, make_user


def _pm(db):
    return auth_headers(make_user(db, role=UserRole.project_manager))


def _create(client, headers, project_id, gross, **kw):
    return client.post(
        f"/api/v1/projects/{project_id}/valuations",
        json={"period_end": str(date.today()), "gross_valuation": str(gross), **kw},
        headers=headers,
    )


def test_create_numbering_and_math(client, db):
    headers = _pm(db)
    project = make_project(
        db, contract_value=Decimal("1000000"), retention_pct=Decimal("10")
    )
    year = date.today().year

    res = _create(client, headers, project.id, "100000")
    assert res.status_code == 201
    v1 = res.json()
    assert v1["doc_number"] == f"INV-{year}-001"
    assert v1["valuation_number"] == 1
    assert Decimal(v1["retention_amount"]) == Decimal("10000.00")
    assert Decimal(v1["previous_certified"]) == Decimal("0")
    assert Decimal(v1["net_certified"]) == Decimal("90000.00")


def test_second_valuation_previous_certified_invariant(client, db):
    headers = _pm(db)
    project = make_project(
        db, contract_value=Decimal("1000000"), retention_pct=Decimal("10")
    )
    v1 = _create(client, headers, project.id, "100000").json()
    client.post(f"/api/v1/valuations/{v1['id']}/issue", json={}, headers=headers)

    v2 = _create(client, headers, project.id, "250000").json()
    assert v2["valuation_number"] == 2
    assert Decimal(v2["retention_amount"]) == Decimal("25000.00")
    assert Decimal(v2["previous_certified"]) == Decimal("90000.00")
    assert Decimal(v2["net_certified"]) == Decimal("135000.00")
    # Invariant: sum of nets == latest gross - latest retention
    assert Decimal(v1["net_certified"]) + Decimal(v2["net_certified"]) == Decimal(
        "250000"
    ) - Decimal("25000")


def test_no_retention_project(client, db):
    headers = _pm(db)
    project = make_project(db, contract_value=Decimal("500000"), retention_pct=None)
    v = _create(client, headers, project.id, "50000").json()
    assert Decimal(v["retention_amount"]) == Decimal("0")
    assert Decimal(v["net_certified"]) == Decimal("50000.00")


def test_single_draft_rule(client, db):
    headers = _pm(db)
    project = make_project(db, contract_value=Decimal("1000000"))
    assert _create(client, headers, project.id, "10000").status_code == 201
    assert _create(client, headers, project.id, "20000").status_code == 409


def test_gross_guards(client, db):
    headers = _pm(db)
    project = make_project(
        db, contract_value=Decimal("100000"), retention_pct=Decimal("5")
    )
    v1 = _create(client, headers, project.id, "50000").json()
    client.post(f"/api/v1/valuations/{v1['id']}/issue", json={}, headers=headers)

    # Below latest certified gross
    assert _create(client, headers, project.id, "40000").status_code == 422
    # Above contract value
    assert _create(client, headers, project.id, "150000").status_code == 422
    # Equal to latest certified is fine (no additional work certified)
    assert _create(client, headers, project.id, "50000").status_code == 201


def test_patch_recomputes(client, db):
    headers = _pm(db)
    project = make_project(
        db, contract_value=Decimal("1000000"), retention_pct=Decimal("10")
    )
    v = _create(client, headers, project.id, "100000").json()
    res = client.patch(
        f"/api/v1/valuations/{v['id']}", json={"gross_valuation": "200000"}, headers=headers
    )
    assert res.status_code == 200
    assert Decimal(res.json()["retention_amount"]) == Decimal("20000.00")
    assert Decimal(res.json()["net_certified"]) == Decimal("180000.00")


def test_transitions(client, db):
    headers = _pm(db)
    project = make_project(db, contract_value=Decimal("1000000"))
    v = _create(client, headers, project.id, "100000").json()

    # Pay before issue -> 409
    assert (
        client.post(f"/api/v1/valuations/{v['id']}/pay", json={}, headers=headers).status_code
        == 409
    )
    assert (
        client.post(f"/api/v1/valuations/{v['id']}/issue", json={}, headers=headers).status_code
        == 200
    )
    # Edit after issue -> 409; delete after issue -> 409
    assert (
        client.patch(
            f"/api/v1/valuations/{v['id']}", json={"notes": "x"}, headers=headers
        ).status_code
        == 409
    )
    assert client.delete(f"/api/v1/valuations/{v['id']}", headers=headers).status_code == 409
    res = client.post(f"/api/v1/valuations/{v['id']}/pay", json={}, headers=headers)
    assert res.status_code == 200
    assert res.json()["paid_date"] is not None
    # Cancel paid -> 409
    assert (
        client.post(f"/api/v1/valuations/{v['id']}/cancel", headers=headers).status_code == 409
    )


def test_cancel_latest_only(client, db):
    headers = _pm(db)
    project = make_project(db, contract_value=Decimal("1000000"))
    v1 = _create(client, headers, project.id, "100000").json()
    client.post(f"/api/v1/valuations/{v1['id']}/issue", json={}, headers=headers)
    v2 = _create(client, headers, project.id, "200000").json()
    client.post(f"/api/v1/valuations/{v2['id']}/issue", json={}, headers=headers)

    # v1 is not the latest -> cannot cancel
    assert (
        client.post(f"/api/v1/valuations/{v1['id']}/cancel", headers=headers).status_code == 409
    )
    # v2 can be cancelled
    assert (
        client.post(f"/api/v1/valuations/{v2['id']}/cancel", headers=headers).status_code == 200
    )


def test_revenue_summary(client, db):
    headers = _pm(db)
    project = make_project(
        db, contract_value=Decimal("1000000"), retention_pct=Decimal("10")
    )
    make_task(db, project, progress_pct=50, weight=Decimal("1"))

    v1 = _create(client, headers, project.id, "100000").json()
    client.post(f"/api/v1/valuations/{v1['id']}/issue", json={}, headers=headers)
    client.post(f"/api/v1/valuations/{v1['id']}/pay", json={}, headers=headers)
    v2 = _create(client, headers, project.id, "250000").json()
    client.post(f"/api/v1/valuations/{v2['id']}/issue", json={}, headers=headers)

    summary = client.get(
        f"/api/v1/projects/{project.id}/revenue-summary", headers=headers
    ).json()
    assert Decimal(summary["certified_gross"]) == Decimal("250000.00")
    assert Decimal(summary["retention_held"]) == Decimal("25000.00")
    assert Decimal(summary["invoiced_to_date"]) == Decimal("225000.00")
    assert Decimal(summary["paid_to_date"]) == Decimal("90000.00")
    assert Decimal(summary["outstanding"]) == Decimal("135000.00")
    assert Decimal(summary["suggested_gross"]) == Decimal("500000.00")  # 50% progress
    assert summary["valuation_count"] == 2


def test_rbac(client, db):
    project = make_project(db, contract_value=Decimal("1000000"))
    for role, expected in [
        (UserRole.viewer, 403),
        (UserRole.site_manager, 403),
        (UserRole.procurement_officer, 403),
        (UserRole.admin, 201),
    ]:
        headers = auth_headers(make_user(db, role=role))
        res = _create(client, headers, project.id, "1000")
        assert res.status_code == expected, role
        if expected == 201:
            client.delete(f"/api/v1/valuations/{res.json()['id']}", headers=headers)
