"""Fills the last tables that were still empty.

    uv run python -m scripts.seed_remaining

Run after `scripts.seed`, `scripts.seed_fleet` and `scripts.seed_commercial`.

Thirteen tables had nothing in them, which meant banking, period close,
permissions, stocktakes and supplier payments all opened on empty screens even
though the machinery behind them worked. Everything here goes through the real
services, so the ledger stays balanced and the numbers are the ones the rules
produce.

Idempotent, and each block commits on its own so a dropped connection to a
database on the other side of an ocean does not throw away a finished one.
"""

import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

import app.modules  # noqa: F401
from app.common.enums import UserRole
from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.accounting import banking, payables, service as accounting
from app.modules.accounting.models import (
    Account,
    BankAccount,
    BankTransaction,
    ExchangeRate,
    FiscalPeriod,
)
from app.modules.users.models import User

TODAY = date.today()


def _admin(db):
    return db.scalar(select(User).where(User.role == UserRole.admin))


# --- Permissions -------------------------------------------------------------


def seed_permissions(db) -> None:
    """The role matrix, written down rather than implied by code.

    Until this exists the permissions screen has nothing to show and every
    answer comes from the defaults in Python, which is exactly the thing the
    module was built to stop.
    """
    from app.modules.permissions import service as permissions
    from app.modules.permissions.models import RolePermission, UserPermissionOverride

    created = permissions.ensure_seeded(db)
    db.flush()

    # One person with a deliberate exception, so the override screen shows what
    # an override actually looks like rather than an empty list.
    if not db.scalar(select(func.count()).select_from(UserPermissionOverride)):
        site = db.scalar(select(User).where(User.role == UserRole.site_manager))
        if site is not None:
            db.add(
                UserPermissionOverride(
                    user_id=site.id,
                    permission="procurement:read",
                    allowed=True,
                )
            )
    total = db.scalar(select(func.count()).select_from(RolePermission))
    print(f"permissions: {total} role rows ({created} new), 1 personal override")


# --- Money that moves --------------------------------------------------------


def seed_fiscal_periods(db) -> None:
    """Twelve months, with the ones already reported shut.

    Closing is the point: posting into a month somebody has already reported on
    is refused rather than quietly changing a statement that has been read.
    """
    if db.scalar(select(func.count()).select_from(FiscalPeriod)):
        print("fiscal periods: already open")
        return

    admin = _admin(db)
    year = TODAY.year
    closed = 0
    for month in range(1, 13):
        starts = date(year, month, 1)
        ends = (date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)) - timedelta(
            days=1
        )
        # Anything more than two months old is closed; the current month and
        # the one before it stay open so the demo can still post.
        shut = (year, month) < (TODAY.year, TODAY.month - 1 if TODAY.month > 1 else 1)
        db.add(
            FiscalPeriod(
                year=year,
                month=month,
                starts_on=starts,
                ends_on=ends,
                is_closed=shut,
                closed_by=getattr(admin, "id", None) if shut else None,
            )
        )
        closed += 1 if shut else 0
    db.flush()
    print(f"fiscal periods: 12 months, {closed} closed")


def seed_exchange_rates(db) -> None:
    """A rate per month, kept rather than overwritten.

    A journal posted in March has to keep translating at March's rate, or last
    year's accounts change every time somebody updates a number.
    """
    if db.scalar(select(func.count()).select_from(ExchangeRate)):
        print("exchange rates: already recorded")
        return

    # ZWL against USD over the year, moving the way it actually moves.
    rate = Decimal("3600")
    added = 0
    for month in range(1, 13):
        effective = date(TODAY.year, month, 1)
        if effective > TODAY:
            break
        db.add(
            ExchangeRate(
                from_currency="USD",
                to_currency="ZWL",
                rate=rate,
                effective_date=effective,
                source="Reserve Bank auction",
            )
        )
        rate = (rate * Decimal("1.085")).quantize(Decimal("0.000001"))
        added += 1
    db.flush()
    print(f"exchange rates: {added} monthly USD/ZWL rates")


def seed_bank(db) -> None:
    """A bank account, a month of statement lines, and a reconciliation.

    The statement deliberately does not agree with the ledger to begin with —
    that difference is the entire work of reconciling, and an account that
    matches perfectly demonstrates nothing.
    """
    if db.scalar(select(func.count()).select_from(BankAccount)):
        print("bank: already opened")
        return

    admin = _admin(db)
    accounting.ensure_chart(db)
    gl = db.scalar(select(Account).where(Account.code == accounting.BANK))
    if gl is None:
        print("bank: no cash account on the chart")
        return

    account = BankAccount(
        name="Main Current Account",
        bank_name="CBZ Bank",
        account_number="0224-118-9007",
        branch="Kwame Nkrumah",
        currency="USD",
        kind="bank",
        gl_account_id=gl.id,
        opening_balance=Decimal("125000.00"),
        created_by=getattr(admin, "id", None),
    )
    db.add(account)
    db.flush()

    class _Line:
        def __init__(self, transaction_date, description, reference, amount):
            self.transaction_date = transaction_date
            self.description = description
            self.reference = reference
            self.amount = Decimal(amount)

    lines = [
        (26, "Client receipt — valuation 4", "RCT-0041", "84500.00"),
        (24, "Readymix supplier payment", "EFT-9912", "-31200.00"),
        (21, "Diesel — bulk delivery", "EFT-9918", "-8640.00"),
        (18, "Wages transfer", "PAY-0311", "-46800.00"),
        (15, "Client receipt — retention release", "RCT-0044", "18250.00"),
        (12, "Plant hire — Hitachi ZX130", "EFT-9931", "-15600.00"),
        (9, "Bank charges", "CHG-0088", "-410.00"),
        (7, "Reinforcement supplier payment", "EFT-9940", "-22400.00"),
        (4, "Client receipt — valuation 5", "RCT-0049", "67300.00"),
        (2, "Interest received", "INT-0012", "312.40"),
    ]
    added = banking.import_lines(
        db,
        account.id,
        [
            _Line(TODAY - timedelta(days=days), description, reference, amount)
            for days, description, reference, amount in lines
        ],
    )
    db.flush()

    # Match what can be matched automatically, and leave the rest showing as
    # the work still to do.
    matched = 0
    for suggestion in banking.suggest_matches(db, account.id):
        try:
            banking.match(db, suggestion["transaction_id"], suggestion["journal_id"])
            matched += 1
        except Exception:
            continue
    db.flush()
    print(f"bank: 1 account, {added} statement lines, {matched} matched automatically")


def seed_reconciliation(db) -> None:
    """Sign off the month against a statement that genuinely agrees.

    `complete` refuses while anything is unexplained, which is the point of it
    — a reconciliation you can finish while it is still out is box-ticking. So
    the closing figure here is derived from what the books and the timing
    differences actually say, the way a real statement that reconciles would
    read, rather than a number picked to look tidy.
    """
    from app.modules.accounting.models import BankReconciliation

    if db.scalar(select(func.count()).select_from(BankReconciliation)):
        print("reconciliation: already done")
        return

    account = db.scalar(select(BankAccount).limit(1))
    if account is None:
        return
    admin = _admin(db)
    as_at = TODAY - timedelta(days=1)

    # books = statement + in transit − unpresented, so the statement that
    # reconciles is the books less the timing differences.
    probe = banking.summary(db, account.id, as_at, Decimal("0"))
    statement_balance = (
        Decimal(probe["book_balance"])
        - Decimal(probe["deposits_in_transit"])
        + Decimal(probe["unpresented_payments"])
    ).quantize(Decimal("0.01"))

    banking.complete(
        db,
        account.id,
        as_at,
        statement_balance,
        admin,
        "Month-end reconciliation against the CBZ statement",
    )
    db.flush()
    print(f"reconciliation: 1 completed at a statement balance of {statement_balance}")


def seed_supplier_payments(db) -> None:
    """Pay some of what is owed, so payables age instead of sitting forever."""
    from app.modules.accounting.models import SupplierPayment
    from app.modules.accounting.schemas import PaymentAllocationIn, SupplierPaymentCreate
    from app.common.enums import PoStatus
    from app.modules.procurement.models import PurchaseOrder

    if db.scalar(select(func.count()).select_from(SupplierPayment)):
        print("supplier payments: already made")
        return

    admin = _admin(db)
    received = list(
        db.scalars(
            select(PurchaseOrder)
            .where(PurchaseOrder.status == PoStatus.received)
            .order_by(PurchaseOrder.order_date)
            .limit(6)
        )
    )
    if not received:
        print("supplier payments: nothing has been received to pay for")
        return

    by_supplier: dict = {}
    for order in received:
        by_supplier.setdefault(order.supplier_id, []).append(order)

    paid = 0
    for index, (supplier_id, orders) in enumerate(list(by_supplier.items())[:3]):
        # The last one is paid in part, so the ageing report has something
        # outstanding on it rather than every invoice settled in full.
        part = index == len(by_supplier) - 1 and len(orders) > 0
        allocations = []
        total = Decimal("0")
        for order in orders:
            amount = Decimal(order.total_amount or 0)
            if amount <= 0:
                continue
            if part:
                amount = (amount * Decimal("0.6")).quantize(Decimal("0.01"))
            allocations.append(
                PaymentAllocationIn(purchase_order_id=order.id, amount=amount)
            )
            total += amount
        if not allocations or total <= 0:
            continue

        payables.create_payment(
            db,
            SupplierPaymentCreate(
                supplier_id=supplier_id,
                payment_date=TODAY - timedelta(days=10 - index * 3),
                amount=total,
                method="EFT",
                reference=f"EFT-{9950 + index}",
                allocations=allocations,
            ),
            admin,
        )
        paid += 1
    db.flush()
    print(f"supplier payments: {paid} made, one of them in part")


def seed_retention_release(db) -> None:
    from app.modules.subcontracts import service as subcontracts
    from app.modules.subcontracts.models import RetentionRelease, Subcontract

    if db.scalar(select(func.count()).select_from(RetentionRelease)):
        print("retention releases: already released")
        return

    admin = _admin(db)

    class _Release:
        amount = None  # everything still held
        released_on = TODAY - timedelta(days=5)
        reason = "Practical completion certified"

    for contract in db.scalars(select(Subcontract)):
        summary = subcontracts.subcontract_summary(db, contract.id)
        if Decimal(summary["retention_outstanding"]) <= 0:
            continue
        # Half of what is held, so the register still has something on it.
        class _Half(_Release):
            amount = (Decimal(summary["retention_outstanding"]) / 2).quantize(
                Decimal("0.01")
            )

        subcontracts.release_retention(db, contract.id, _Half(), admin)
        db.flush()
        print(f"retention releases: 1 part release of {_Half.amount}")
        return
    print("retention releases: nothing held to release")


# --- Plant and stores --------------------------------------------------------


def seed_equipment_certificates(db) -> None:
    """Insurance and roadworthiness across the yard, including two that lapsed.

    A register where everything is in date proves nothing: the screen exists to
    show the machine that cannot legally go out.
    """
    from app.modules.fleet.models import Equipment, EquipmentCertificate

    if db.scalar(select(func.count()).select_from(EquipmentCertificate)):
        print("equipment certificates: already filed")
        return

    admin = _admin(db)
    machines = list(db.scalars(select(Equipment).order_by(Equipment.code)))
    filed = 0
    lapsed = 0

    for index, machine in enumerate(machines):
        # Two machines are deliberately out of date, and one crane gets its
        # thorough examination so it can still be sent to site.
        offset = -20 if index in (3, 11) else 120 + index * 11
        db.add(
            EquipmentCertificate(
                equipment_id=machine.id,
                cert_type="insurance",
                reference=f"POL/{2026}/{4400 + index}",
                issued_on=TODAY - timedelta(days=245),
                expires_on=TODAY + timedelta(days=offset),
                created_by=getattr(admin, "id", None),
            )
        )
        filed += 1
        lapsed += 1 if offset < 0 else 0

        if machine.meter_type.value == "kilometres":
            db.add(
                EquipmentCertificate(
                    equipment_id=machine.id,
                    cert_type="roadworthiness",
                    reference=f"COF/{7100 + index}",
                    expires_on=TODAY + timedelta(days=90 + index * 7),
                    created_by=getattr(admin, "id", None),
                )
            )
            filed += 1
        if machine.category.value == "crane":
            db.add(
                EquipmentCertificate(
                    equipment_id=machine.id,
                    cert_type="thorough_examination",
                    reference=f"TE/{2026}/{88 + index}",
                    expires_on=TODAY + timedelta(days=150),
                    created_by=getattr(admin, "id", None),
                )
            )
            filed += 1

    db.flush()
    print(f"equipment certificates: {filed} filed, {lapsed} already lapsed")


def seed_stocktake(db) -> None:
    """A completed count, with a couple of lines that did not agree.

    The variance is the point. A stocktake where every line matches is a
    stocktake nobody needed to do.
    """
    from app.modules.inventory import service as inventory
    from app.modules.inventory.models import Stocktake, StockItem
    from app.modules.inventory.schemas import (
        StocktakeCountLine,
        StocktakeCountSet,
        StocktakeCreate,
    )

    if db.scalar(select(func.count()).select_from(Stocktake)):
        print("stocktakes: already counted")
        return

    admin = _admin(db)
    items = list(
        db.scalars(select(StockItem).where(StockItem.is_active.is_(True)).limit(12))
    )
    if not items:
        print("stocktakes: nothing to count")
        return

    stocktake = inventory.create_stocktake(
        db,
        StocktakeCreate(count_date=TODAY - timedelta(days=2), notes="Quarterly count"),
        admin.id,
    )
    db.flush()

    lines = []
    varied = 0
    for index, line in enumerate(stocktake.lines):
        expected = Decimal(line.expected_quantity or 0)
        # Most agree; two are short and one is over, which is what a real count
        # looks like.
        if index == 1 and expected >= 3:
            counted, varied = expected - 2, varied + 1
        elif index == 4 and expected >= 5:
            counted, varied = expected - 4, varied + 1
        elif index == 6:
            counted, varied = expected + 1, varied + 1
        else:
            counted = expected
        lines.append(
            StocktakeCountLine(stock_item_id=line.stock_item_id, counted_quantity=counted)
        )

    inventory.set_stocktake_counts(db, stocktake.id, StocktakeCountSet(lines=lines))
    db.flush()
    inventory.approve_stocktake(db, stocktake.id, admin.id)
    db.flush()
    print(f"stocktakes: 1 counted and approved, {varied} lines did not agree")


def main() -> None:
    if settings.environment == "production":
        print("Refusing to run against production")
        sys.exit(1)

    db = SessionLocal()
    try:
        for step in (
            seed_permissions,
            seed_fiscal_periods,
            seed_exchange_rates,
            seed_equipment_certificates,
            seed_stocktake,
            seed_supplier_payments,
            seed_retention_release,
            seed_bank,
            seed_reconciliation,
        ):
            try:
                step(db)
                db.commit()
            except Exception as exc:
                db.rollback()
                print(f"{step.__name__}: FAILED — {exc}")
        print("\nRemaining tables complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
