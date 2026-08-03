import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal

import anthropic
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AiNotConfiguredError,
    AiRateLimitedError,
    AiUpstreamError,
    ConflictError,
    ValidationFailedError,
)
from app.modules.ai import prompts
from app.modules.ai.client import MODEL, get_client
from app.modules.ai.schemas import (
    ChatMessage,
    ComparisonMatrix,
    ExtractedLineOut,
    MatrixCell,
    MatrixRow,
    MatrixSupplier,
    PoTermsDraft,
    QuoteComparisonAnalysis,
    QuoteComparisonResponse,
    QuoteExtraction,
    QuoteExtractionOut,
    RfqDraft,
    RfqDraftItem,
    WeeklyReportDraft,
)
from app.modules.ai.tools import CHAT_TOOLS, run_tool
from app.modules.boq.models import BoqItem
from app.modules.company.models import CompanySettings
from app.modules.procurement.service import get_quote, get_rfq, list_quotes
from app.modules.projects.service import get_project

MAX_TOOL_ROUNDS = 8
ZERO = Decimal("0")


@contextmanager
def _map_ai_errors():
    try:
        yield
    except anthropic.AuthenticationError as exc:
        raise AiNotConfiguredError("The configured AI API key was rejected") from exc
    except anthropic.RateLimitError as exc:
        raise AiRateLimitedError("The AI service is rate limiting requests") from exc
    except anthropic.APIStatusError as exc:
        raise AiUpstreamError(f"AI service error (HTTP {exc.status_code})") from exc
    except anthropic.APIConnectionError as exc:
        raise AiUpstreamError("Could not reach the AI service") from exc


def _check_refusal(response) -> None:
    if response.stop_reason == "refusal":
        raise AiUpstreamError("The AI declined this request; rephrase and try again")


def _text_of(response) -> str:
    parts = [block.text for block in response.content if block.type == "text"]
    return "".join(parts).strip()


def _company_name(db: Session) -> str:
    from sqlalchemy import select

    settings_row = db.scalar(select(CompanySettings).limit(1))
    return settings_row.name if settings_row else "the company"


# --- Action A: generate RFQ draft -------------------------------------------


def generate_rfq_draft(
    db: Session,
    project_id: uuid.UUID,
    boq_item_ids: list[uuid.UUID],
    title: str | None,
    instructions: str | None,
) -> RfqDraft:
    project = get_project(db, project_id)
    items: list[BoqItem] = []
    for item_id in boq_item_ids:
        item = db.get(BoqItem, item_id)
        if item is None or item.project_id != project_id:
            raise ValidationFailedError("BOQ item does not exist in this project")
        items.append(item)

    item_lines = "\n".join(
        f"- {i.item_code} | {i.description} | {i.quantity} {i.unit} | "
        f"category: {i.cost_category.value}"
        for i in items
    )
    client_name = project.client.name if project.client else "the client"
    user_content = (
        f"Company: {_company_name(db)}.\n"
        f"Project: {project.code} — {project.name} for {client_name}.\n"
        f"Site: {project.site_address or 'n/a'}, {project.city or ''}.\n"
        f"Items to be quoted:\n{item_lines}\n"
        f"Additional instructions from the buyer: {instructions or 'none'}\n"
        "Draft the RFQ body."
    )

    with _map_ai_errors():
        response = get_client().messages.create(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "medium"},
            system=prompts.RFQ_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )
    _check_refusal(response)

    return RfqDraft(
        title=title or f"Supply of materials — {project.name}",
        body=_text_of(response),
        # Deterministic echo: line data never round-trips through the model
        items=[
            RfqDraftItem(
                boq_item_id=i.id,
                item_code=i.item_code,
                description=i.description,
                unit=i.unit,
                quantity=i.quantity,
            )
            for i in items
        ],
    )


# --- Action B1: extract quote -----------------------------------------------


def extract_quote(db: Session, rfq_id: uuid.UUID, raw_text: str) -> QuoteExtractionOut:
    rfq = get_rfq(db, rfq_id)
    rfq_items = {str(item.id): item for item in rfq.items}
    line_table = "\n".join(
        f"- rfq_item_id: {item.id} | {item.description} | {item.quantity} {item.unit}"
        for item in rfq.items
    )
    user_content = f"RFQ lines to match against:\n{line_table}\n---RAW QUOTE TEXT---\n{raw_text}"

    with _map_ai_errors():
        response = get_client().messages.parse(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "low"},
            system=prompts.EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
            output_format=QuoteExtraction,
        )
    _check_refusal(response)
    extraction: QuoteExtraction | None = response.parsed_output
    if extraction is None:
        raise AiUpstreamError("The AI response could not be parsed; try again")

    lines: list[ExtractedLineOut] = []
    seen: set[str] = set()
    for line in extraction.lines:
        rfq_item = None
        rfq_item_id = None
        confidence = line.match_confidence
        if line.rfq_item_id and line.rfq_item_id in rfq_items and line.rfq_item_id not in seen:
            rfq_item = rfq_items[line.rfq_item_id]
            rfq_item_id = rfq_item.id
            seen.add(line.rfq_item_id)
        else:
            confidence = "unmatched"
        quantity = Decimal(str(line.quantity))
        out = ExtractedLineOut(
            rfq_item_id=rfq_item_id,
            description=line.description,
            unit=line.unit,
            quantity=quantity,
            unit_price=Decimal(str(line.unit_price)),
            match_confidence=confidence,
        )
        if rfq_item is not None:
            out.unit_mismatch = (line.unit or "").strip().lower() != rfq_item.unit.strip().lower()
            out.quantity_mismatch = quantity != rfq_item.quantity
        lines.append(out)

    currency = (extraction.currency or "").strip().upper() or None
    return QuoteExtractionOut(
        supplier_name=extraction.supplier_name,
        currency=currency,
        currency_warning=bool(currency and currency not in ("USD", "US$", "$")),
        payment_terms=extraction.payment_terms,
        delivery_terms=extraction.delivery_terms,
        valid_until=extraction.valid_until,
        lines=lines,
        notes=extraction.notes,
    )


# --- Action B2: compare quotes ----------------------------------------------


def build_comparison_matrix(db: Session, rfq_id: uuid.UUID) -> ComparisonMatrix:
    rfq = get_rfq(db, rfq_id)
    quotes = list_quotes(db, rfq_id)
    if len(quotes) < 2:
        raise ConflictError("At least two quotes are needed to compare")

    rows: list[MatrixRow] = []
    quoted_by_all: list[uuid.UUID] = []
    for rfq_item in rfq.items:
        cells: dict[str, MatrixCell] = {}
        prices = {}
        for quote in quotes:
            match = next((li for li in quote.items if li.rfq_item_id == rfq_item.id), None)
            if match is None:
                cells[str(quote.id)] = MatrixCell()
            else:
                cells[str(quote.id)] = MatrixCell(
                    quote_item_id=match.id,
                    unit_price=match.unit_price,
                    amount=match.amount,
                    unit_mismatch=match.unit_mismatch,
                    quantity_mismatch=match.quantity_mismatch,
                )
                prices[str(quote.id)] = match.unit_price
        if prices:
            cheapest = min(prices.values())
            for quote_id, price in prices.items():
                if price == cheapest:
                    cells[quote_id].is_cheapest = True
        if len(prices) == len(quotes):
            quoted_by_all.append(rfq_item.id)
        rows.append(
            MatrixRow(
                rfq_item_id=rfq_item.id,
                description=rfq_item.description,
                unit=rfq_item.unit,
                quantity=rfq_item.quantity,
                cells=cells,
            )
        )

    suppliers: list[MatrixSupplier] = []
    for quote in quotes:
        comparable = sum(
            (li.amount for li in quote.items if li.rfq_item_id in quoted_by_all),
            ZERO,
        )
        cheapest_count = sum(1 for row in rows if row.cells[str(quote.id)].is_cheapest)
        suppliers.append(
            MatrixSupplier(
                quote_id=quote.id,
                supplier_id=quote.supplier_id,
                supplier_name=quote.supplier_name or "Unknown",
                status=quote.status.value,
                total_amount=quote.total_amount,
                comparable_total=comparable,
                coverage_pct=quote.coverage_pct,
                cheapest_line_count=cheapest_count,
                payment_terms=quote.payment_terms,
                delivery_terms=quote.delivery_terms,
                valid_until=str(quote.valid_until) if quote.valid_until else None,
            )
        )

    return ComparisonMatrix(rfq_id=rfq.id, suppliers=suppliers, rows=rows)


def compare_quotes(db: Session, rfq_id: uuid.UUID) -> QuoteComparisonResponse:
    matrix = build_comparison_matrix(db, rfq_id)

    with _map_ai_errors():
        response = get_client().messages.parse(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "medium"},
            system=prompts.COMPARE_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Pre-computed comparison data (all arithmetic verified):\n"
                        + matrix.model_dump_json()
                    ),
                }
            ],
            output_format=QuoteComparisonAnalysis,
        )
    _check_refusal(response)
    analysis: QuoteComparisonAnalysis | None = response.parsed_output
    if analysis is None:
        raise AiUpstreamError("The AI response could not be parsed; try again")
    return QuoteComparisonResponse(matrix=matrix, analysis=analysis)


# --- Action C: PO terms -----------------------------------------------------


def draft_po_terms(db: Session, quote_id: uuid.UUID) -> PoTermsDraft:
    quote = get_quote(db, quote_id)
    rfq = quote.rfq
    supplier = quote.supplier
    user_content = (
        f"RFQ: {rfq.doc_number} — {rfq.title}.\n"
        f"Supplier: {supplier.name if supplier else 'unknown'}.\n"
        f"Quote received {quote.received_date}, valid until {quote.valid_until or 'n/a'}.\n"
        f"Quoted payment terms: {quote.payment_terms or 'not stated'}.\n"
        f"Quoted delivery terms: {quote.delivery_terms or 'not stated'}.\n"
        f"Quote total: {quote.total_amount}.\n"
        "Draft the purchase order commercial terms, then on a new line after the "
        "marker '---NOTES---' add any short internal notes for the procurement team."
    )

    with _map_ai_errors():
        response = get_client().messages.create(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "medium"},
            system=prompts.PO_TERMS_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )
    _check_refusal(response)
    text = _text_of(response)
    terms, _, notes = text.partition("---NOTES---")
    return PoTermsDraft(terms=terms.strip(), notes=notes.strip())


# --- Action D: weekly site report -------------------------------------------


def generate_weekly_report(
    db: Session,
    project_id: uuid.UUID,
    week_start,
    week_end,
) -> WeeklyReportDraft:
    from datetime import timedelta

    from sqlalchemy import func, select

    from app.modules.costs.models import CostEntry
    from app.modules.projects.service import project_summary
    from app.modules.site.models import SiteDiaryEntry, SiteIssue

    project = get_project(db, project_id)
    period_end = week_end or (week_start + timedelta(days=6))
    summary = project_summary(db, project_id)

    entries = db.scalars(
        select(SiteDiaryEntry)
        .where(
            SiteDiaryEntry.project_id == project_id,
            SiteDiaryEntry.entry_date >= week_start,
            SiteDiaryEntry.entry_date <= period_end,
        )
        .order_by(SiteDiaryEntry.entry_date)
    ).all()
    diary_lines = (
        "\n".join(
            f"- {e.entry_date} | {e.weather.value} | labour {e.labour_headcount} | "
            f"plant: {e.plant_equipment or 'n/a'} | work: {e.work_done}"
            + (f" | delays: {e.delays}" if e.delays else "")
            for e in entries
        )
        or "(no diary entries recorded this period)"
    )

    issues = db.scalars(select(SiteIssue).where(SiteIssue.project_id == project_id)).all()
    raised = [i for i in issues if week_start <= i.raised_date <= period_end]
    resolved = [
        i for i in issues if i.resolved_date and week_start <= i.resolved_date <= period_end
    ]
    still_open = [i for i in issues if i.status.value == "open"]

    def _issue_lines(items):
        return (
            "\n".join(
                f"- [{i.severity.value}] {i.title}"
                + (f" (resolved {i.resolved_date})" if i.resolved_date else "")
                for i in items
            )
            or "(none)"
        )

    period_costs = db.execute(
        select(CostEntry.source, func.sum(CostEntry.amount))
        .where(
            CostEntry.project_id == project_id,
            CostEntry.entry_date >= week_start,
            CostEntry.entry_date <= period_end,
        )
        .group_by(CostEntry.source)
    ).all()
    cost_lines = (
        "\n".join(f"- {source.value}: {total}" for source, total in period_costs)
        or "(no costs recorded this period)"
    )

    client_name = project.client.name if project.client else "the client"
    user_content = (
        f"Company: {_company_name(db)}.\n"
        f"Project: {project.code} — {project.name} for {client_name}.\n"
        f"Reporting period: {week_start} to {period_end}.\n"
        f"Overall progress: {summary.progress_pct}%. "
        f"All amounts are in USD. "
        f"Budget: {summary.budget_total} | actual to date: {summary.actual_total} | "
        f"overdue tasks: {summary.overdue_tasks}.\n\n"
        f"Daily site diary this period:\n{diary_lines}\n\n"
        f"Issues raised this period:\n{_issue_lines(raised)}\n\n"
        f"Issues resolved this period:\n{_issue_lines(resolved)}\n\n"
        f"Issues still open:\n{_issue_lines(still_open)}\n\n"
        f"Costs recorded this period by source:\n{cost_lines}\n\n"
        "Write the weekly progress report."
    )

    with _map_ai_errors():
        response = get_client().messages.create(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "medium"},
            system=prompts.WEEKLY_REPORT_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )
    _check_refusal(response)
    return WeeklyReportDraft(
        project_id=project_id,
        period_start=week_start,
        period_end=period_end,
        markdown=_text_of(response),
    )


# --- Chat -------------------------------------------------------------------


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def chat_stream(
    db: Session, client_messages: list[ChatMessage], project_id: uuid.UUID | None
) -> Iterator[str]:
    client = get_client()

    messages: list[dict] = []
    for i, msg in enumerate(client_messages):
        content = msg.content
        if i == len(client_messages) - 1 and msg.role == "user" and project_id:
            content = f"[Context: the user is currently viewing project {project_id}]\n{content}"
        messages.append({"role": msg.role, "content": content})

    system = [
        {
            "type": "text",
            "text": prompts.CHAT_SYSTEM,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    try:
        for _round in range(MAX_TOOL_ROUNDS):
            with client.messages.stream(
                model=MODEL,
                max_tokens=8000,
                system=system,
                tools=CHAT_TOOLS,
                messages=messages,
            ) as stream:
                for event in stream:
                    if event.type == "content_block_delta" and event.delta.type == "text_delta":
                        yield _sse({"type": "text", "delta": event.delta.text})
                    elif (
                        event.type == "content_block_start"
                        and event.content_block.type == "tool_use"
                    ):
                        yield _sse({"type": "tool_start", "name": event.content_block.name})
                final = stream.get_final_message()

            if final.stop_reason == "refusal":
                yield _sse(
                    {
                        "type": "error",
                        "code": "ai_refused",
                        "detail": "The assistant declined this request.",
                    }
                )
                break
            if final.stop_reason != "tool_use":
                break

            messages.append({"role": "assistant", "content": final.content})
            results = []
            for block in final.content:
                if block.type == "tool_use":
                    output = run_tool(db, block.name, block.input)
                    yield _sse(
                        {"type": "tool_result", "name": block.name, "is_error": output.is_error}
                    )
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": output.text,
                            "is_error": output.is_error,
                        }
                    )
            # All tool results go back in ONE user message
            messages.append({"role": "user", "content": results})
        else:
            yield _sse(
                {
                    "type": "error",
                    "code": "tool_loop_limit",
                    "detail": "The assistant used too many lookups; try a narrower question.",
                }
            )
    except anthropic.RateLimitError:
        yield _sse(
            {
                "type": "error",
                "code": "ai_rate_limited",
                "detail": "The AI service is busy; try again shortly.",
            }
        )
    except anthropic.APIConnectionError:
        yield _sse(
            {"type": "error", "code": "ai_unreachable", "detail": "Could not reach the AI service."}
        )
    except anthropic.APIStatusError as exc:
        yield _sse(
            {
                "type": "error",
                "code": "ai_upstream_error",
                "detail": f"AI service error (HTTP {exc.status_code}).",
            }
        )
    yield _sse({"type": "done"})
