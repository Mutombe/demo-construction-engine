import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import AccountType, JournalSource, JournalStatus


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    account_type: AccountType
    description: str | None
    is_system: bool
    is_active: bool
    balance: Decimal
    normal_balance: str


class AccountCreate(BaseModel):
    code: str = Field(min_length=1, max_length=10)
    name: str = Field(min_length=1, max_length=120)
    account_type: AccountType
    description: str | None = None


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    is_active: bool | None = None


class JournalLineIn(BaseModel):
    account_id: uuid.UUID
    debit: Decimal = Field(default=Decimal("0"), ge=0)
    credit: Decimal = Field(default=Decimal("0"), ge=0)
    description: str | None = None


class JournalCreate(BaseModel):
    journal_date: date
    memo: str = Field(min_length=1, max_length=400)
    project_id: uuid.UUID | None = None
    lines: list[JournalLineIn] = Field(min_length=2)


class JournalLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    debit: Decimal
    credit: Decimal
    description: str | None
    account_code: str | None = None
    account_name: str | None = None


class JournalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doc_number: str
    journal_date: date
    memo: str
    status: JournalStatus
    source: JournalSource
    source_id: uuid.UUID | None
    project_id: uuid.UUID | None
    total: Decimal
    posted_at: datetime | None
    reversal_of: uuid.UUID | None


class JournalDetail(JournalRead):
    lines: list[JournalLineRead] = []


class TrialBalanceRow(BaseModel):
    account_id: uuid.UUID
    code: str
    name: str
    account_type: str
    debit: Decimal
    credit: Decimal
    balance: Decimal


class TrialBalance(BaseModel):
    as_at: date
    rows: list[TrialBalanceRow]
    total_debit: Decimal
    total_credit: Decimal
    balanced: bool


class StatementLine(BaseModel):
    code: str
    name: str
    amount: Decimal


class IncomeStatement(BaseModel):
    start: date
    end: date
    revenue: list[StatementLine]
    expenses: list[StatementLine]
    revenue_total: Decimal
    expense_total: Decimal
    net_result: Decimal


class BalanceSheet(BaseModel):
    as_at: date
    assets: list[StatementLine]
    liabilities: list[StatementLine]
    equity: list[StatementLine]
    asset_total: Decimal
    liability_total: Decimal
    equity_total: Decimal
    result_for_period: Decimal
    balanced: bool


class LedgerRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entry_date: date
    doc_number: str
    description: str | None
    debit: Decimal
    credit: Decimal
    balance_after: Decimal
    journal_id: uuid.UUID
    project_id: uuid.UUID | None


class UnpostedEntry(BaseModel):
    id: uuid.UUID
    entry_date: date
    description: str | None
    amount: Decimal
    project_id: uuid.UUID
