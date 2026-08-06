import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends

from decimal import Decimal

from pydantic import BaseModel, Field

from app.common.enums import UserRole
from app.core.deps import CurrentUser, DbDep, require_roles
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.accounting import banking, cvr, payables, service, subsidiary
from app.modules.accounting.models import Account, Journal
from app.modules.accounting.schemas import (
    AccountCreate,
    AccountRead,
    AccountUpdate,
    BalanceSheet,
    IncomeStatement,
    JournalCreate,
    JournalDetail,
    JournalRead,
    LedgerRow,
    Ageing,
    OpenPurchaseOrder,
    SupplierPaymentCreate,
    SupplierPaymentRead,
    TrialBalance,
    UnpostedEntry,
)
from sqlalchemy import select

router = APIRouter(prefix="/accounting", tags=["accounting"])

# The books are not general reading: they expose company-wide position, which
# site and procurement roles have no business seeing.
books_read = Depends(require_roles(UserRole.admin, UserRole.project_manager))
books_write = Depends(require_roles(UserRole.admin))


@router.get("/accounts", response_model=list[AccountRead], dependencies=[books_read])
def list_accounts(db: DbDep, active_only: bool = False) -> list[AccountRead]:
    service.ensure_chart(db)
    stmt = select(Account).order_by(Account.code)
    if active_only:
        stmt = stmt.where(Account.is_active.is_(True))
    return [AccountRead.model_validate(a) for a in db.scalars(stmt)]


@router.post("/accounts", response_model=AccountRead, status_code=201)
def create_account(body: AccountCreate, db: DbDep, _=books_write) -> AccountRead:
    if db.scalar(select(Account).where(Account.code == body.code)):
        raise ConflictError(f"Account {body.code} already exists")
    account = Account(**body.model_dump())
    db.add(account)
    db.flush()
    return AccountRead.model_validate(account)


@router.patch("/accounts/{account_id}", response_model=AccountRead)
def update_account(
    account_id: uuid.UUID, body: AccountUpdate, db: DbDep, _=books_write
) -> AccountRead:
    account = db.get(Account, account_id)
    if account is None:
        raise NotFoundError("Account not found")
    updates = body.model_dump(exclude_unset=True)
    if account.is_system and updates.get("is_active") is False:
        raise ConflictError(
            f"{account.code} is used by automatic posting and cannot be deactivated"
        )
    for field, value in updates.items():
        setattr(account, field, value)
    db.flush()
    return AccountRead.model_validate(account)


@router.get("/accounts/{account_id}/ledger", response_model=list[LedgerRow])
def get_account_ledger(
    account_id: uuid.UUID,
    db: DbDep,
    _=books_read,
    start: date | None = None,
    end: date | None = None,
) -> list[LedgerRow]:
    if db.get(Account, account_id) is None:
        raise NotFoundError("Account not found")
    return [
        LedgerRow.model_validate(row) for row in service.account_ledger(db, account_id, start, end)
    ]


@router.get("/journals", response_model=list[JournalRead], dependencies=[books_read])
def list_journals(
    db: DbDep,
    start: date | None = None,
    end: date | None = None,
    project_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[JournalRead]:
    stmt = select(Journal).order_by(Journal.journal_date.desc(), Journal.doc_number.desc())
    if start:
        stmt = stmt.where(Journal.journal_date >= start)
    if end:
        stmt = stmt.where(Journal.journal_date <= end)
    if project_id:
        stmt = stmt.where(Journal.project_id == project_id)
    return [JournalRead.model_validate(j) for j in db.scalars(stmt.limit(min(limit, 500)))]


def _detail(journal) -> JournalDetail:
    out = JournalDetail.model_validate(journal)
    for line, source in zip(out.lines, journal.lines, strict=False):
        line.account_code = source.account.code if source.account else None
        line.account_name = source.account.name if source.account else None
    return out


@router.get("/journals/{journal_id}", response_model=JournalDetail, dependencies=[books_read])
def get_journal(journal_id: uuid.UUID, db: DbDep) -> JournalDetail:
    return _detail(service.get_journal(db, journal_id))


@router.post("/journals", response_model=JournalDetail, status_code=201)
def create_journal(
    body: JournalCreate, db: DbDep, user: CurrentUser, _=books_write
) -> JournalDetail:
    """Creates a draft. Posting is a separate, deliberate act."""
    journal = service.create_journal(
        db,
        journal_date=body.journal_date,
        memo=body.memo,
        project_id=body.project_id,
        created_by=user.id,
        lines=[line.model_dump() for line in body.lines],
    )
    return _detail(service.get_journal(db, journal.id))


@router.post("/journals/{journal_id}/post", response_model=JournalDetail)
def post_journal(
    journal_id: uuid.UUID, db: DbDep, user: CurrentUser, _=books_write
) -> JournalDetail:
    service.post(db, journal_id, user)
    return _detail(service.get_journal(db, journal_id))


@router.post("/journals/{journal_id}/reverse", response_model=JournalDetail)
def reverse_journal(
    journal_id: uuid.UUID, db: DbDep, user: CurrentUser, _=books_write
) -> JournalDetail:
    """Corrects by writing the mirror image. Nothing is ever deleted."""
    reversal = service.reverse(db, journal_id, user)
    return _detail(service.get_journal(db, reversal.id))


@router.get("/trial-balance", response_model=TrialBalance, dependencies=[books_read])
def get_trial_balance(db: DbDep, as_at: date | None = None) -> TrialBalance:
    return TrialBalance.model_validate(service.trial_balance(db, as_at))


@router.get("/income-statement", response_model=IncomeStatement, dependencies=[books_read])
def get_income_statement(
    db: DbDep,
    start: date | None = None,
    end: date | None = None,
    project_id: uuid.UUID | None = None,
) -> IncomeStatement:
    today = date.today()
    start = start or today.replace(month=1, day=1)
    end = end or today
    if end < start:
        raise ValidationFailedError("The end of the period cannot precede its start")
    return IncomeStatement.model_validate(service.income_statement(db, start, end, project_id))


@router.get("/balance-sheet", response_model=BalanceSheet, dependencies=[books_read])
def get_balance_sheet(db: DbDep, as_at: date | None = None) -> BalanceSheet:
    return BalanceSheet.model_validate(service.balance_sheet(db, as_at or date.today()))


@router.get("/unposted", response_model=list[UnpostedEntry], dependencies=[books_read])
def list_unposted(db: DbDep) -> list[UnpostedEntry]:
    """The control that makes a posting failure visible. Should be empty."""
    rows = [
        UnpostedEntry(
            id=e.id,
            entry_date=e.entry_date,
            description=e.description,
            amount=e.amount,
            project_id=e.project_id,
        )
        for e in service.unposted_cost_entries(db)
    ]
    rows += [
        UnpostedEntry(
            id=v.id,
            entry_date=v.period_end,
            description=f"{v.doc_number} certified, not in the books",
            amount=v.net_certified,
            project_id=v.project_id,
        )
        for v in service.unposted_valuations(db)
    ]
    return rows


@router.post("/unposted/post", response_model=dict)
def post_unposted(db: DbDep, user: CurrentUser, _=books_write) -> dict:
    return {"posted": service.post_missing(db, user)}


@router.get("/period-summary", response_model=dict, dependencies=[books_read])
def period_summary(db: DbDep) -> dict:
    """The two numbers a director asks for first, without opening a statement."""
    today = date.today()
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    this_month = service.income_statement(db, month_start, today)
    last_month = service.income_statement(db, last_month_end.replace(day=1), last_month_end)
    sheet = service.balance_sheet(db, today)
    return {
        "month_revenue": this_month["revenue_total"],
        "month_expenses": this_month["expense_total"],
        "month_result": this_month["net_result"],
        "last_month_result": last_month["net_result"],
        "receivables": next(
            (a["amount"] for a in sheet["assets"] if a["code"] == service.ACCOUNTS_RECEIVABLE),
            0,
        ),
        "payables": next(
            (a["amount"] for a in sheet["liabilities"] if a["code"] == service.ACCOUNTS_PAYABLE),
            0,
        ),
        "retention_held": next(
            (a["amount"] for a in sheet["assets"] if a["code"] == service.RETENTION_RECEIVABLE),
            0,
        ),
        "balanced": sheet["balanced"],
    }


# --- Who owes what ----------------------------------------------------------


@router.get("/receivables", response_model=Ageing, dependencies=[books_read])
def get_receivables(db: DbDep, as_at: date | None = None) -> Ageing:
    """Aged from the issue date. Retention is excluded: it is withheld by
    agreement, not overdue."""
    return Ageing.model_validate(payables.receivables_ageing(db, as_at))


@router.get("/payables", response_model=Ageing, dependencies=[books_read])
def get_payables(db: DbDep, as_at: date | None = None) -> Ageing:
    """Aged from the date goods were received, which is when the debt became
    real — the order date would age something not yet delivered."""
    return Ageing.model_validate(payables.payables_ageing(db, as_at))


@router.get("/suppliers/{supplier_id}/open-orders", response_model=list[OpenPurchaseOrder])
def list_open_orders(supplier_id: uuid.UUID, db: DbDep, _=books_read) -> list[OpenPurchaseOrder]:
    """What could be paid right now, with what is left on each."""
    from app.common.enums import PoStatus
    from app.modules.procurement.models import PurchaseOrder

    orders = list(
        db.scalars(
            select(PurchaseOrder)
            .where(
                PurchaseOrder.supplier_id == supplier_id,
                PurchaseOrder.status == PoStatus.received,
            )
            .order_by(PurchaseOrder.received_date)
        )
    )
    paid = payables.po_outstanding(db, [po.id for po in orders])
    out = []
    for po in orders:
        outstanding = po.total_amount - paid.get(po.id, 0)
        if outstanding <= 0:
            continue
        out.append(
            OpenPurchaseOrder(
                id=po.id,
                doc_number=po.doc_number,
                supplier_id=po.supplier_id,
                received_date=po.received_date,
                total_amount=po.total_amount,
                outstanding=outstanding,
            )
        )
    return out


@router.get("/payments", response_model=list[SupplierPaymentRead], dependencies=[books_read])
def list_payments(db: DbDep, supplier_id: uuid.UUID | None = None) -> list[SupplierPaymentRead]:
    return [_payment_read(p) for p in payables.list_payments(db, supplier_id)]


@router.post("/payments", response_model=SupplierPaymentRead, status_code=201)
def create_payment(
    body: SupplierPaymentCreate, db: DbDep, user: CurrentUser, _=books_write
) -> SupplierPaymentRead:
    """Records the payment and posts it: debit what was owed, credit the bank."""
    return _payment_read(payables.create_payment(db, body, user))


def _payment_read(payment) -> SupplierPaymentRead:
    out = SupplierPaymentRead.model_validate(payment)
    out.supplier_name = payment.supplier.name if payment.supplier else None
    return out


# --- Per-party ledgers -------------------------------------------------------


@router.get("/subsidiary", response_model=list[dict], dependencies=[books_read])
def list_subsidiary_accounts(db: DbDep, entity_type: str | None = None) -> list[dict]:
    return [
        {
            "id": p.id,
            "code": p.code,
            "name": p.name,
            "entity_type": p.entity_type,
            "entity_id": p.entity_id,
            "currency": p.currency,
            "balance": p.balance,
        }
        for p in subsidiary.list_pockets(db, entity_type)
    ]


@router.get("/subsidiary/{subsidiary_id}/statement", response_model=dict)
def get_statement(
    subsidiary_id: uuid.UUID,
    db: DbDep,
    _=books_read,
    start: date | None = None,
    end: date | None = None,
) -> dict:
    """One party's account, as you would send it to them."""
    result = subsidiary.statement(db, subsidiary_id, start, end)
    result["entries"] = [
        {
            "id": e.id,
            "entry_date": e.entry_date,
            "doc_number": e.doc_number,
            "description": e.description,
            "debit": e.debit,
            "credit": e.credit,
            "balance_after": e.balance_after,
            "journal_id": e.journal_id,
        }
        for e in result["entries"]
    ]
    return result


@router.get("/subsidiary-reconciliation", response_model=list[dict], dependencies=[books_read])
def get_subsidiary_reconciliation(db: DbDep) -> list[dict]:
    """Proves the pockets still add up to their control account. A difference
    means every ageing built on them is wrong until it is explained."""
    return subsidiary.reconcile(db)


# --- Cash at bank ------------------------------------------------------------


class StatementLineIn(BaseModel):
    transaction_date: date
    description: str
    reference: str | None = None
    amount: Decimal


class StatementImport(BaseModel):
    lines: list[StatementLineIn] = Field(min_length=1)


class MatchRequest(BaseModel):
    journal_id: uuid.UUID


class CompleteRequest(BaseModel):
    statement_date: date
    statement_balance: Decimal
    notes: str | None = None


@router.get("/bank-accounts", response_model=list[dict], dependencies=[books_read])
def list_bank_accounts(db: DbDep) -> list[dict]:
    from app.modules.accounting.models import BankAccount

    out = []
    for account in db.scalars(select(BankAccount).order_by(BankAccount.name)):
        out.append(
            {
                "id": account.id,
                "name": account.name,
                "bank_name": account.bank_name,
                "account_number": account.account_number,
                "currency": account.currency,
                "kind": account.kind,
                "is_active": account.is_active,
                "book_balance": banking.book_balance(db, account, date.today()),
            }
        )
    return out


@router.get("/bank-accounts/{bank_account_id}/reconciliation", response_model=dict)
def get_reconciliation(
    bank_account_id: uuid.UUID,
    db: DbDep,
    _=books_read,
    as_at: date | None = None,
    statement_balance: Decimal | None = None,
) -> dict:
    """The reconciliation laid out the way it is written on paper."""
    result = banking.summary(db, bank_account_id, as_at or date.today(), statement_balance)
    result["unmatched_statement_lines"] = [
        {
            "id": line.id,
            "transaction_date": line.transaction_date,
            "description": line.description,
            "reference": line.reference,
            "amount": line.amount,
        }
        for line in result["unmatched_statement_lines"]
    ]
    result["unmatched_book_entries"] = [
        {
            "journal_id": row.journal_id,
            "entry_date": row.entry_date,
            "doc_number": row.doc_number,
            "description": row.description,
            "debit": row.debit,
            "credit": row.credit,
        }
        for row in result["unmatched_book_entries"]
    ]
    return result


@router.get("/bank-accounts/{bank_account_id}/suggested-matches", response_model=list[dict])
def get_suggested_matches(bank_account_id: uuid.UUID, db: DbDep, _=books_read) -> list[dict]:
    """Suggests rather than decides: matching on amount and a few days is right
    often enough to save the work and wrong often enough that it must not post
    itself."""
    return banking.suggest_matches(db, bank_account_id)


@router.post("/bank-accounts/{bank_account_id}/statement", response_model=dict)
def import_statement(
    bank_account_id: uuid.UUID, body: StatementImport, db: DbDep, _=books_write
) -> dict:
    return {"imported": banking.import_lines(db, bank_account_id, body.lines)}


@router.post("/bank-transactions/{transaction_id}/match", response_model=dict)
def match_transaction(
    transaction_id: uuid.UUID, body: MatchRequest, db: DbDep, _=books_write
) -> dict:
    line = banking.match(db, transaction_id, body.journal_id)
    return {"id": line.id, "matched_journal_id": line.matched_journal_id}


@router.post("/bank-transactions/{transaction_id}/unmatch", response_model=dict)
def unmatch_transaction(transaction_id: uuid.UUID, db: DbDep, _=books_write) -> dict:
    line = banking.unmatch(db, transaction_id)
    return {"id": line.id, "matched_journal_id": None}


@router.post("/bank-accounts/{bank_account_id}/reconcile", response_model=dict)
def complete_reconciliation(
    bank_account_id: uuid.UUID, body: CompleteRequest, db: DbDep, user: CurrentUser, _=books_write
) -> dict:
    """Refuses while anything is unexplained: a reconciliation you can finish
    while it is still out is a box-ticking exercise."""
    record = banking.complete(
        db, bank_account_id, body.statement_date, body.statement_balance, user, body.notes
    )
    return {
        "id": record.id,
        "statement_date": record.statement_date,
        "statement_balance": record.statement_balance,
        "book_balance": record.book_balance,
        "is_complete": record.is_complete,
    }


# --- Cost value reconciliation ----------------------------------------------


@router.get("/cvr/{project_id}", response_model=dict, dependencies=[books_read])
def get_cvr(project_id: uuid.UUID, db: DbDep) -> dict:
    """Whether the job is making money, as opposed to whether it has billed."""
    return cvr.cost_value_reconciliation(db, project_id)


@router.get("/cvr", response_model=list[dict], dependencies=[books_read])
def get_portfolio_cvr(db: DbDep) -> list[dict]:
    return cvr.portfolio(db)
