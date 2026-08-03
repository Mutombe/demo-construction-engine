import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.common.enums import UserRole
from app.core.deps import DbDep, require_roles
from app.core.exceptions import AiNotConfiguredError
from app.modules.ai import service
from app.modules.ai.client import ai_available
from app.modules.ai.schemas import (
    AiStatus,
    ChatRequest,
    PoTermsDraft,
    PoTermsRequest,
    QuoteComparisonResponse,
    QuoteExtractionOut,
    QuoteExtractRequest,
    RfqDraft,
    RfqGenerateRequest,
    WeeklyReportDraft,
    WeeklyReportRequest,
)

router = APIRouter(tags=["ai"])

proc_write = Depends(require_roles(UserRole.procurement_officer, UserRole.project_manager))


def _require_ai() -> None:
    if not ai_available():
        raise AiNotConfiguredError()


@router.get("/ai/status", response_model=AiStatus)
def get_ai_status() -> AiStatus:
    return AiStatus(available=ai_available())


@router.post("/ai/rfqs/generate", response_model=RfqDraft, dependencies=[proc_write])
def generate_rfq_draft(body: RfqGenerateRequest, db: DbDep) -> RfqDraft:
    _require_ai()
    return service.generate_rfq_draft(
        db, body.project_id, body.boq_item_ids, body.title, body.instructions
    )


@router.post(
    "/rfqs/{rfq_id}/quotes/extract",
    response_model=QuoteExtractionOut,
    dependencies=[proc_write],
)
def extract_quote(rfq_id: uuid.UUID, body: QuoteExtractRequest, db: DbDep) -> QuoteExtractionOut:
    _require_ai()
    return service.extract_quote(db, rfq_id, body.raw_text)


@router.post(
    "/rfqs/{rfq_id}/compare",
    response_model=QuoteComparisonResponse,
    dependencies=[proc_write],
)
def compare_quotes(rfq_id: uuid.UUID, db: DbDep) -> QuoteComparisonResponse:
    _require_ai()
    return service.compare_quotes(db, rfq_id)


@router.post("/purchase-orders/draft-terms", response_model=PoTermsDraft, dependencies=[proc_write])
def draft_po_terms(body: PoTermsRequest, db: DbDep) -> PoTermsDraft:
    _require_ai()
    return service.draft_po_terms(db, body.quote_id)


@router.post(
    "/ai/site/weekly-report",
    response_model=WeeklyReportDraft,
    dependencies=[Depends(require_roles(UserRole.site_manager, UserRole.project_manager))],
)
def generate_weekly_report(body: WeeklyReportRequest, db: DbDep) -> WeeklyReportDraft:
    _require_ai()
    return service.generate_weekly_report(db, body.project_id, body.week_start, body.week_end)


@router.post("/ai/chat")
def chat(body: ChatRequest, db: DbDep) -> StreamingResponse:
    _require_ai()
    return StreamingResponse(
        service.chat_stream(db, body.messages, body.project_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
