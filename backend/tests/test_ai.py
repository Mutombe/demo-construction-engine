import json
from decimal import Decimal

from app.common.enums import UserRole
from app.modules.ai.schemas import ExtractedLine, QuoteExtraction
from tests.ai_fakes import (
    fake_response,
    text_block,
    text_delta_event,
    tool_start_event,
    tool_use_block,
)
from tests.factories import (
    auth_headers,
    fake_uuid,
    make_boq_item,
    make_boq_section,
    make_project,
    make_quote,
    make_rfq,
    make_supplier,
    make_user,
)


def _proc(db):
    return auth_headers(make_user(db, role=UserRole.procurement_officer))


# --- Status + gating --------------------------------------------------------


def test_ai_status_reflects_key(client, db, no_ai):
    user = auth_headers(make_user(db))
    assert client.get("/api/v1/ai/status", headers=user).json() == {"available": False}


def test_ai_endpoints_503_without_key(client, db, no_ai):
    headers = _proc(db)
    project = make_project(db)
    res = client.post(
        "/api/v1/ai/rfqs/generate",
        json={"project_id": str(project.id), "boq_item_ids": [fake_uuid()]},
        headers=headers,
    )
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "ai_not_configured"

    res = client.post(
        "/api/v1/ai/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers=headers,
    )
    assert res.status_code == 503


# --- Generate RFQ -----------------------------------------------------------


def test_generate_rfq_draft(client, db, fake_ai):
    headers = _proc(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section, description="Cement 42.5N", unit="t")
    fake_ai.messages.create_responses.append(
        fake_response(content=[text_block("## Introduction\nPlease quote...")])
    )

    res = client.post(
        "/api/v1/ai/rfqs/generate",
        json={"project_id": str(project.id), "boq_item_ids": [str(item.id)]},
        headers=headers,
    )
    assert res.status_code == 200
    draft = res.json()
    assert "Introduction" in draft["body"]
    assert draft["items"][0]["description"] == "Cement 42.5N"
    # Nothing persisted
    assert client.get(f"/api/v1/projects/{project.id}/rfqs", headers=headers).json()["total"] == 0
    # Model params respected
    call = fake_ai.messages.create_calls[0]
    assert call["model"] == "claude-opus-5"
    assert "temperature" not in call and "thinking" not in call


# --- Extraction -------------------------------------------------------------


def test_extract_quote_post_validation(client, db, fake_ai):
    headers = _proc(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section, unit="m3", quantity=Decimal("10"))
    rfq = make_rfq(db, project, [item])
    real_line_id = str(rfq.items[0].id)

    fake_ai.messages.parse_responses.append(
        fake_response(
            parsed_output=QuoteExtraction(
                supplier_name="SteelCo",
                currency="usd",
                payment_terms="30 days",
                delivery_terms=None,
                valid_until="2026-09-01",
                notes=None,
                lines=[
                    ExtractedLine(
                        rfq_item_id=real_line_id,
                        description="Concrete supply",
                        unit="m2",  # mismatch on purpose
                        quantity=12,
                        unit_price=150,
                        match_confidence="exact",
                    ),
                    ExtractedLine(
                        rfq_item_id=fake_uuid(),  # bogus id -> must be nulled
                        description="Mystery item",
                        unit=None,
                        quantity=1,
                        unit_price=99,
                        match_confidence="probable",
                    ),
                ],
            )
        )
    )

    res = client.post(
        f"/api/v1/rfqs/{rfq.id}/quotes/extract",
        json={"raw_text": "Dear sirs, please find our quotation attached..."},
        headers=headers,
    )
    assert res.status_code == 200
    out = res.json()
    assert out["supplier_name"] == "SteelCo"
    matched, bogus = out["lines"]
    assert matched["rfq_item_id"] == real_line_id
    assert matched["unit_mismatch"] is True
    assert matched["quantity_mismatch"] is True
    assert bogus["rfq_item_id"] is None
    assert bogus["match_confidence"] == "unmatched"


# --- Comparison -------------------------------------------------------------


def test_compare_requires_two_quotes(client, db, fake_ai):
    headers = _proc(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section)
    rfq = make_rfq(db, project, [item])
    make_quote(db, rfq, make_supplier(db))
    res = client.post(f"/api/v1/rfqs/{rfq.id}/compare", headers=headers)
    assert res.status_code == 409


def test_compare_matrix_is_deterministic(client, db, fake_ai):
    from app.modules.ai.schemas import (
        QuoteComparisonAnalysis,
        Recommendation,
    )

    headers = _proc(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    a = make_boq_item(db, section, quantity=Decimal("10"))
    b = make_boq_item(db, section, quantity=Decimal("4"))
    rfq = make_rfq(db, project, [a, b])
    line_ids = {item.boq_item_id: item.id for item in rfq.items}
    s1, s2 = make_supplier(db, name="Cheap Partial"), make_supplier(db, name="Full Cover")
    make_quote(db, rfq, s1, prices={line_ids[a.id]: Decimal("90")})  # subset
    make_quote(
        db,
        rfq,
        s2,
        prices={line_ids[a.id]: Decimal("100"), line_ids[b.id]: Decimal("50")},
    )

    fake_ai.messages.parse_responses.append(
        fake_response(
            parsed_output=QuoteComparisonAnalysis(
                summary="Full Cover offers complete coverage.",
                line_analysis=[],
                risk_flags=["Cheap Partial quoted only 1 of 2 lines"],
                recommendation=Recommendation(
                    supplier_id=str(s2.id), supplier_name="Full Cover", reasoning="Coverage."
                ),
            )
        )
    )

    res = client.post(f"/api/v1/rfqs/{rfq.id}/compare", headers=headers)
    assert res.status_code == 200
    body = res.json()
    matrix = body["matrix"]
    by_name = {s["supplier_name"]: s for s in matrix["suppliers"]}
    assert by_name["Cheap Partial"]["coverage_pct"] == 50.0
    assert by_name["Full Cover"]["coverage_pct"] == 100.0
    # Comparable basis = only line a (quoted by all): 10*90 vs 10*100
    assert Decimal(by_name["Cheap Partial"]["comparable_total"]) == Decimal("900.00")
    assert Decimal(by_name["Full Cover"]["comparable_total"]) == Decimal("1000.00")
    assert body["analysis"]["recommendation"]["supplier_name"] == "Full Cover"


# --- Chat SSE ---------------------------------------------------------------


def _parse_sse(raw: str) -> list[dict]:
    return [
        json.loads(frame[len("data: ") :])
        for frame in raw.split("\n\n")
        if frame.startswith("data: ")
    ]


def test_chat_stream_with_tool_round(client, db, fake_ai):
    headers = _proc(db)
    project = make_project(db)
    section = make_boq_section(db, project)
    item = make_boq_item(db, section)
    make_rfq(db, project, [item], doc_number="RFQ-CHAT-001")

    tool_block = tool_use_block("toolu_1", "list_rfqs", {"project_id": str(project.id)})
    fake_ai.messages.stream_scripts.extend(
        [
            (
                [tool_start_event("list_rfqs")],
                fake_response(stop_reason="tool_use", content=[tool_block]),
            ),
            (
                [text_delta_event("You have one RFQ: RFQ-CHAT-001.")],
                fake_response(
                    stop_reason="end_turn",
                    content=[text_block("You have one RFQ: RFQ-CHAT-001.")],
                ),
            ),
        ]
    )

    with client.stream(
        "POST",
        "/api/v1/ai/chat",
        json={
            "messages": [{"role": "user", "content": "List my RFQs"}],
            "project_id": str(project.id),
        },
        headers=headers,
    ) as res:
        assert res.status_code == 200
        raw = "".join(res.iter_text())

    events = _parse_sse(raw)
    kinds = [e["type"] for e in events]
    assert kinds == ["tool_start", "tool_result", "text", "done"]
    assert events[1]["is_error"] is False

    # The tool actually hit the DB: its result (2nd round message) contains the doc number
    second_call = fake_ai.messages.stream_calls[1]
    tool_result_msg = second_call["messages"][-1]
    assert "RFQ-CHAT-001" in tool_result_msg["content"][0]["content"]
    # Prompt caching set on system block
    assert second_call["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_chat_refusal_yields_error_event(client, db, fake_ai):
    headers = _proc(db)
    fake_ai.messages.stream_scripts.append(([], fake_response(stop_reason="refusal", content=[])))
    with client.stream(
        "POST",
        "/api/v1/ai/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers=headers,
    ) as res:
        raw = "".join(res.iter_text())
    kinds = [e["type"] for e in _parse_sse(raw)]
    assert kinds == ["error", "done"]


# --- Tool dispatcher --------------------------------------------------------


def test_tool_dispatcher_error_paths(db):
    from app.modules.ai.tools import run_tool

    out = run_tool(db, "nonexistent_tool", {})
    assert out.is_error

    out = run_tool(db, "get_project_summary", {"project_id": "not-a-uuid"})
    assert out.is_error

    out = run_tool(db, "list_projects", {})
    assert not out.is_error


# --- M3 tools ---------------------------------------------------------------


def test_m3_tools(db):
    from datetime import date

    from app.common.enums import UserRole as _UR
    from app.modules.ai.tools import run_tool
    from app.modules.expenses.schemas import ExpenseClaimCreate
    from app.modules.expenses.service import create_claim
    from app.modules.inventory.schemas import GoodsInRequest, StockItemCreate
    from app.modules.inventory.service import create_item, goods_in
    from app.modules.site.schemas import DiaryEntryCreate, SiteIssueCreate
    from app.modules.site.service import create_diary_entry, create_issue

    user = make_user(db, role=_UR.site_manager)
    project = make_project(db)
    create_diary_entry(
        db,
        project.id,
        DiaryEntryCreate(entry_date=date.today(), work_done="Poured slab", weather="rain"),
        user.id,
    )
    create_issue(db, project.id, SiteIssueCreate(title="Crack in wall", severity="high"), user.id)
    create_claim(
        db,
        project.id,
        ExpenseClaimCreate(
            category="fuel",
            expense_date=date.today(),
            amount=Decimal("50"),
            description="Diesel",
        ),
        user.id,
    )
    item = create_item(
        db,
        StockItemCreate(code="TST-1", name="Test item", unit="ea", reorder_level=Decimal("100")),
        user.id,
    )
    goods_in(db, item.id, GoodsInRequest(quantity=Decimal("10"), unit_cost=Decimal("5")), user.id)

    out = run_tool(db, "get_site_diary", {"project_id": str(project.id)})
    assert not out.is_error and "Poured slab" in out.text

    out = run_tool(db, "list_site_issues", {"project_id": str(project.id)})
    assert not out.is_error and "Crack in wall" in out.text

    out = run_tool(db, "list_expense_claims", {"project_id": str(project.id)})
    assert not out.is_error and "Diesel" in out.text and user.full_name in out.text

    out = run_tool(db, "get_stock_levels", {"low_stock_only": True})
    assert not out.is_error and "TST-1" in out.text and '"low_stock": true' in out.text

    out = run_tool(db, "get_site_diary", {"project_id": "garbage"})
    assert out.is_error


# --- Weekly report ----------------------------------------------------------


def test_weekly_report(client, db, fake_ai):
    from datetime import date, timedelta

    from app.common.enums import UserRole as _UR
    from app.modules.ai import prompts
    from app.modules.site.schemas import DiaryEntryCreate
    from app.modules.site.service import create_diary_entry

    user = make_user(db, role=_UR.site_manager)
    project = make_project(db)
    week_start = date.today() - timedelta(days=6)
    create_diary_entry(
        db,
        project.id,
        DiaryEntryCreate(entry_date=week_start, work_done="Excavated footings"),
        user.id,
    )

    fake_ai.messages.create_responses.append(
        fake_response(content=[text_block("# Weekly Report\n\nGood progress.")])
    )
    res = client.post(
        "/api/v1/ai/site/weekly-report",
        json={"project_id": str(project.id), "week_start": str(week_start)},
        headers=auth_headers(user),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["markdown"].startswith("# Weekly Report")
    assert body["period_end"] == str(week_start + timedelta(days=6))

    call = fake_ai.messages.create_calls[0]
    assert call["system"] == prompts.WEEKLY_REPORT_SYSTEM
    assert "Excavated footings" in call["messages"][0]["content"]


def test_weekly_report_role_and_gating(client, db, no_ai):
    from datetime import date

    viewer = make_user(db, role=UserRole.viewer)
    site = make_user(db, role=UserRole.site_manager)
    project = make_project(db)
    payload = {"project_id": str(project.id), "week_start": str(date.today())}

    assert (
        client.post(
            "/api/v1/ai/site/weekly-report", json=payload, headers=auth_headers(viewer)
        ).status_code
        == 403
    )
    res = client.post("/api/v1/ai/site/weekly-report", json=payload, headers=auth_headers(site))
    assert res.status_code == 503


def test_ingestion_history_chat_tool(client, db, fake_ai):
    from app.modules.ai.tools import CHAT_TOOLS, run_tool

    # append-only cache rule: the new tool must be the LAST entry
    assert CHAT_TOOLS[-1]["name"] == "get_ingestion_history"

    headers = _proc(db)
    upload = client.post(
        "/api/v1/ingestion/items",
        files={"file": ("tool-test.png", b"img-bytes", "image/png")},
        headers=headers,
    )
    assert upload.status_code == 201

    out = run_tool(db, "get_ingestion_history", {"days": 2})
    assert out.is_error is False
    assert "tool-test.png" in out.text
    out = run_tool(db, "get_ingestion_history", {"status": "posted"})
    assert "tool-test.png" not in out.text
