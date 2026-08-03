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


# --- Measurement sheets -------------------------------------------------------


def _measured_setup(db):
    """Project with two BOQ items (100 m3 @ 150, 500 kg @ 2)."""
    from tests.factories import make_boq_item, make_boq_section

    project = make_project(
        db, contract_value=Decimal("1000000"), retention_pct=Decimal("10")
    )
    section = make_boq_section(db, project)
    a = make_boq_item(
        db, section, description="Concrete", unit="m3",
        quantity=Decimal("100"), rate=Decimal("150"),
    )
    b = make_boq_item(
        db, section, description="Rebar", unit="kg",
        quantity=Decimal("500"), rate=Decimal("2"),
    )
    return project, a, b


def test_measurement_derives_gross_and_recomputes(client, db):
    headers = _pm(db)
    project, a, b = _measured_setup(db)
    val = _create(client, headers, project.id, "1").json()

    res = client.put(
        f"/api/v1/valuations/{val['id']}/measurement",
        json={"lines": [
            {"boq_item_id": str(a.id), "qty_to_date": "40"},
            {"boq_item_id": str(b.id), "qty_to_date": "200"},
        ]},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    # gross = 40*150 + 200*2 = 6400; retention 10% = 640
    assert Decimal(body["gross_valuation"]) == Decimal("6400.00")
    assert Decimal(body["retention_amount"]) == Decimal("640.00")
    assert body["is_measured"] is True
    assert len(body["lines"]) == 2

    # replace-all: re-measuring only item a drops item b
    res = client.put(
        f"/api/v1/valuations/{val['id']}/measurement",
        json={"lines": [{"boq_item_id": str(a.id), "qty_to_date": "50"}]},
        headers=headers,
    ).json()
    assert Decimal(res["gross_valuation"]) == Decimal("7500.00")
    assert len(res["lines"]) == 1

    # direct gross PATCH is blocked while measured
    patched = client.patch(
        f"/api/v1/valuations/{val['id']}",
        json={"gross_valuation": "9999"},
        headers=headers,
    )
    assert patched.status_code == 409

    # clearing the sheet reverts to single-figure mode
    cleared = client.put(
        f"/api/v1/valuations/{val['id']}/measurement", json={"lines": []}, headers=headers
    ).json()
    assert cleared["is_measured"] is False
    patched = client.patch(
        f"/api/v1/valuations/{val['id']}", json={"gross_valuation": "8000"}, headers=headers
    )
    assert patched.status_code == 200


def test_measurement_context_previous_qty_and_snapshots(client, db):
    headers = _pm(db)
    project, a, b = _measured_setup(db)

    v1 = _create(client, headers, project.id, "1").json()
    client.put(
        f"/api/v1/valuations/{v1['id']}/measurement",
        json={"lines": [{"boq_item_id": str(a.id), "qty_to_date": "30"}]},
        headers=headers,
    )
    client.post(f"/api/v1/valuations/{v1['id']}/issue", json={}, headers=headers)

    # snapshots survive a later BOQ rate change
    a.rate = Decimal("999")
    db.flush()
    detail = client.get(f"/api/v1/valuations/{v1['id']}", headers=headers).json()
    assert Decimal(detail["lines"][0]["rate"]) == Decimal("150")
    assert Decimal(detail["gross_valuation"]) == Decimal("4500.00")

    # context for the next draft prefills previous qty from the certificate
    v2 = _create(client, headers, project.id, "4500").json()
    ctx = client.get(f"/api/v1/valuations/{v2['id']}/measurement", headers=headers).json()
    items = {i["item_code"]: i for i in ctx["sections"][0]["items"]}
    a_row = items[[k for k, v in items.items() if v["boq_item_id"] == str(a.id)][0]]
    assert Decimal(a_row["previous_qty"]) == Decimal("30")
    assert a_row["current_qty"] is None


def test_measurement_guards(client, db):
    headers = _pm(db)
    project, a, _ = _measured_setup(db)
    other_project = make_project(db)
    val = _create(client, headers, project.id, "1").json()

    # foreign BOQ item and duplicates rejected
    from tests.factories import make_boq_item, make_boq_section

    foreign_item = make_boq_item(db, make_boq_section(db, other_project))
    res = client.put(
        f"/api/v1/valuations/{val['id']}/measurement",
        json={"lines": [{"boq_item_id": str(foreign_item.id), "qty_to_date": "1"}]},
        headers=headers,
    )
    assert res.status_code == 422
    res = client.put(
        f"/api/v1/valuations/{val['id']}/measurement",
        json={"lines": [
            {"boq_item_id": str(a.id), "qty_to_date": "1"},
            {"boq_item_id": str(a.id), "qty_to_date": "2"},
        ]},
        headers=headers,
    )
    assert res.status_code == 422

    # measuring an issued valuation is blocked
    client.put(
        f"/api/v1/valuations/{val['id']}/measurement",
        json={"lines": [{"boq_item_id": str(a.id), "qty_to_date": "10"}]},
        headers=headers,
    )
    client.post(f"/api/v1/valuations/{val['id']}/issue", json={}, headers=headers)
    res = client.put(
        f"/api/v1/valuations/{val['id']}/measurement",
        json={"lines": [{"boq_item_id": str(a.id), "qty_to_date": "20"}]},
        headers=headers,
    )
    assert res.status_code == 409


def test_certificate_pdf_staff_endpoint(client, db):
    headers = _pm(db)
    project = make_project(db, contract_value=Decimal("100000"), retention_pct=Decimal("5"))
    val = _create(client, headers, project.id, "20000").json()
    # drafts have no certificate
    assert (
        client.get(f"/api/v1/valuations/{val['id']}/certificate", headers=headers).status_code
        == 409
    )
    client.post(f"/api/v1/valuations/{val['id']}/issue", json={}, headers=headers)
    res = client.get(f"/api/v1/valuations/{val['id']}/certificate", headers=headers)
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF")


def test_payslip_pdfs(client, db):
    from datetime import timedelta

    from tests.factories import make_timesheet, make_worker

    headers = _pm(db)
    project = make_project(db)
    worker = make_worker(db, full_name="Slip Test")
    make_timesheet(db, worker, project)
    run = client.post(
        "/api/v1/pay-runs",
        json={
            "period_start": str(date.today() - timedelta(days=6)),
            "period_end": str(date.today()),
        },
        headers=headers,
    ).json()
    combined = client.get(f"/api/v1/pay-runs/{run['id']}/payslips", headers=headers)
    assert combined.status_code == 200
    assert combined.content.startswith(b"%PDF")
    line_id = run["lines"][0]["id"]
    single = client.get(
        f"/api/v1/pay-runs/{run['id']}/lines/{line_id}/payslip", headers=headers
    )
    assert single.status_code == 200
    assert single.content.startswith(b"%PDF")


def test_certificate_pdf_survives_unicode_names(client, db):
    headers = _pm(db)
    project = make_project(db, name="Riverside — Block “A”…", contract_value=Decimal("50000"))
    val = _create(client, headers, project.id, "10000").json()
    client.post(f"/api/v1/valuations/{val['id']}/issue", json={}, headers=headers)
    res = client.get(f"/api/v1/valuations/{val['id']}/certificate", headers=headers)
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF")
