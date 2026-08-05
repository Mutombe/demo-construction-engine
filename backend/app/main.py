from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.exceptions import register_exception_handlers
from app.modules.admin.router import public_router as invites_public_router
from app.modules.accounting.router import router as accounting_router
from app.modules.admin.router import router as admin_router
from app.modules.ai.router import router as ai_router
from app.modules.auth.router import router as auth_router
from app.modules.boq.router import router as boq_router
from app.modules.clients.router import router as clients_router
from app.modules.comments.router import router as comments_router
from app.modules.company.router import router as company_router
from app.modules.costs.router import router as costs_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.expenses.router import router as expenses_router
from app.modules.ingestion.router import router as ingestion_router
from app.modules.inventory.router import router as inventory_router
from app.modules.media.router import router as media_router
from app.modules.notifications.router import router as notifications_router
from app.modules.payroll.router import router as payroll_router
from app.modules.portal.router import links_router as portal_links_router
from app.modules.portal.router import portal_router
from app.modules.procurement.router import router as procurement_router
from app.modules.requisitions.router import router as requisitions_router
from app.modules.projects.router import router as projects_router
from app.modules.reports.router import router as reports_router
from app.modules.search.router import router as search_router
from app.modules.site.router import router as site_router
from app.modules.tasks.router import router as tasks_router
from app.modules.users.router import router as users_router
from app.modules.valuations.router import router as valuations_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Construction ERP API",
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
        # Route function names double as OpenAPI operation ids so the generated
        # frontend hooks read as useListProjects() instead of useListProjectsApiV1ProjectsGet()
        generate_unique_id_function=lambda route: route.name,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)

    @app.get("/healthz", tags=["health"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    api = APIRouter(prefix="/api/v1")
    api.include_router(auth_router)  # login/refresh are anonymous by design
    # Accepting an invite happens before the account exists, so it cannot sit
    # behind authentication. The single-use hashed token is the credential.
    api.include_router(invites_public_router)

    # Authenticated by default: anonymous access is impossible by omission
    protected = APIRouter(dependencies=[Depends(get_current_user)])
    protected.include_router(users_router)
    protected.include_router(clients_router)
    protected.include_router(projects_router)
    protected.include_router(tasks_router)
    protected.include_router(boq_router)
    protected.include_router(costs_router)
    protected.include_router(dashboard_router)
    protected.include_router(procurement_router)
    protected.include_router(requisitions_router)
    protected.include_router(site_router)
    protected.include_router(expenses_router)
    protected.include_router(inventory_router)
    protected.include_router(valuations_router)
    protected.include_router(payroll_router)
    protected.include_router(portal_links_router)
    protected.include_router(notifications_router)
    protected.include_router(media_router)
    protected.include_router(reports_router)
    protected.include_router(search_router)
    protected.include_router(ingestion_router)
    protected.include_router(ai_router)
    protected.include_router(admin_router)
    protected.include_router(company_router)
    protected.include_router(comments_router)
    protected.include_router(accounting_router)
    api.include_router(protected)

    # Client portal: separate auth surface (X-Portal-Token), deliberately NOT
    # under `protected` — portal visitors are clients, not staff users.
    api.include_router(portal_router)

    app.include_router(api)
    return app


app = create_app()
