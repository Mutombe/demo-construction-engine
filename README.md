# Construction ERP

Production-grade Construction ERP for a single construction company.

**Milestone 1: Project Management core** — projects, phases, tasks with dependencies,
program (Gantt) view, Bill of Quantities & budgets, cost tracking, and dashboards,
behind role-based access control.

**Milestone 2: Procurement + AI Copilot** — supplier registry, RFQs built from BOQ
items, supplier quotes with coverage/mismatch flags, purchase orders whose receipt
posts actuals into the cost ledger; plus an AI copilot (`claude-opus-5`): AI-drafted
RFQ documents, structured quote extraction from pasted text, quote comparison with a
reasoned recommendation, AI-drafted PO terms, and a streaming chat assistant with
read-only database tools. AI endpoints return **drafts only** — persistence always
flows through the normal CRUD endpoints — and degrade gracefully (503
`ai_not_configured`) when `ANTHROPIC_API_KEY` is absent.

**Milestone 3: Site, Expenses, Inventory** — daily site diaries (one per project per
day) with an issues/incidents register; expense claims with an approval workflow
(approval posts `cost_entries` with `source=expense`; self-approval blocked); a
central store with weighted-average costing where goods-in, project issues
(`source=inventory_issue` cost posting) and adjustments form an immutable movement
ledger. The AI copilot gained four site/expense/stock chat tools and a new action:
a Claude-drafted client-facing **weekly site report** built from the period's
diaries, issues, and costs.

## Stack

| Layer    | Tech |
|----------|------|
| Backend  | FastAPI · SQLAlchemy 2 (sync) · PostgreSQL 17 · Alembic · PyJWT + Argon2 |
| AI       | Anthropic Python SDK · `claude-opus-5` · structured outputs (`messages.parse`) · SSE streaming chat with tool use · prompt caching |
| Frontend | React 19 · Vite · TypeScript (strict) · TanStack Router/Query · Tailwind v4 · orval (OpenAPI→hooks codegen) |
| Repo     | Monorepo: `backend/` + `frontend/` · uv for Python deps · npm for JS |

## Getting started

### 1. PostgreSQL

Either `docker compose up -d db` (if you have Docker), **or** portable binaries as set up
on this machine:

```powershell
C:\Users\PC\tools\pg17b\pgsql\bin\pg_ctl.exe -D C:\Users\PC\tools\pg17b\data -o "-p 5432" start
```

Databases `construction_erp` and `construction_erp_test` owned by role `erp`/`erp`.

### 2. Backend

```powershell
cd backend
uv sync                          # install deps
uv run alembic upgrade head      # apply migrations
uv run python -m scripts.seed    # realistic demo data (idempotent, dev-only)
uv run uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

Seeded logins (password `demo1234`): `admin@demo.local`, `pm@demo.local`,
`site@demo.local`, `procurement@demo.local`, `viewer@demo.local`.

### 3. Frontend

```powershell
cd frontend
npm install
npm run dev                      # http://localhost:5173 (proxies /api → :8000)
```

### Tests & checks

```powershell
cd backend
uv run pytest                    # 63 tests against the real test database
uv run ruff check app tests scripts

cd frontend
npm run typecheck
npm run build
```

### Regenerating the API client

After changing backend endpoints/schemas:

```powershell
cd backend  ; uv run python -c "import json; from app.main import app; json.dump(app.openapi(), open('openapi.json','w'), indent=1)"
cd frontend ; npm run api:gen
```

Generated code lives in `frontend/src/lib/api/generated/` — never edit it by hand.

## Architecture notes

- **Vertical slices**: each backend domain lives in `app/modules/<name>/` with its own
  `router / service / models / schemas`. Routers do HTTP only; services own business logic.
- **Auth**: 15-min JWT access tokens (held in memory client-side) + opaque rotating
  refresh tokens stored hashed, delivered as an httpOnly cookie scoped to the refresh
  path. Token reuse revokes the whole session chain.
- **RBAC**: single global role per user (`admin`, `project_manager`, `site_manager`,
  `procurement_officer`, `viewer`); admin passes every check. All routes are
  authenticated by default via the router mount.
- **Money & quantities** are `Numeric`, never floats. BOQ `amount` is a Postgres
  generated column (`quantity × rate`) so stored totals can never drift.
- **Progress** is never stored on projects/phases — always computed as
  Σ(progress × weight) / Σ(weight), weight defaulting to planned duration.
- **Task dependencies** are cycle-checked (DFS, transitive) in the service layer;
  cross-project dependencies are rejected.
- **BOQ variations** never mutate original lines (`item_type`: original/variation/omission).
- **Cost entries** ledger accepts unallocated costs (nullable `boq_item_id`) and has a
  `source` discriminator ready for the future expenses/PO/invoice modules.
