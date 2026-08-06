"""The shape of the chart of accounts.

Six levels, the same discipline the parameter chart uses, fitted to a
contractor rather than a landlord:

    1. Report        Balance Sheet | Profit and Loss
    2. Class         Asset, Contra Asset, Liability, Equity, Income, Expense
    3. Subclass      the code-range owner
    4. Type          Cash and Cash Equivalents, Receivables, Plant, ...
    5. Subtype       Bank, Cash, Retention, Immovable, Movable, ...
    6. Account       4-digit code and name

A code range is OWNED by its subclass. A code may be used once, ever, and only
by an account of the subclass that owns its range, so a glance at 2100 tells
you it is a current liability without opening anything. Unused codes inside a
range stay reserved for that subclass rather than being available to whoever
asks first.

The ranges below are chosen to fit the chart this system already posts to, so
adopting the taxonomy renumbers nothing and no history moves.
"""

# subclass -> (label, low, high) inclusive
SUBCLASS_RANGES: dict[str, tuple[str, int, int]] = {
    "noncurrent_assets": ("Non-current Assets", 1, 999),
    "current_assets": ("Current Assets", 1000, 1999),
    "current_liabilities": ("Current Liabilities", 2000, 2999),
    "equity": ("Equity", 3000, 3999),
    "revenue": ("Revenue", 4000, 4999),
    "cost_of_works": ("Cost of Works", 5000, 5999),
    "overheads": ("Overheads and Administration", 6000, 6999),
    "other_income_expense": ("Other Income and Expense", 7000, 7999),
    "taxation": ("Taxation", 8000, 8999),
    "suspense": ("Suspense and Opening Balances", 9000, 9999),
}

REPORTS = {"balance_sheet": "Balance Sheet", "profit_loss": "Profit and Loss"}

CLASSES = {
    "asset": "Asset",
    "contra_asset": "Contra Asset",
    "liability": "Liability",
    "equity": "Equity",
    "income": "Income",
    "expense": "Expense",
}

# report -> class -> subclasses it may use
TAXONOMY: dict[str, dict[str, list[str]]] = {
    "balance_sheet": {
        "asset": ["noncurrent_assets", "current_assets"],
        # Accumulated depreciation and provisions sit against the asset they
        # reduce rather than becoming liabilities.
        "contra_asset": ["noncurrent_assets", "current_assets"],
        "liability": ["current_liabilities", "suspense"],
        "equity": ["equity"],
    },
    "profit_loss": {
        "income": ["revenue", "other_income_expense"],
        "expense": [
            "cost_of_works",
            "overheads",
            "other_income_expense",
            "taxation",
        ],
    },
}

TYPES_BY_SUBCLASS: dict[str, list[str]] = {
    "noncurrent_assets": ["Plant and Equipment", "Motor Vehicles", "Property", "Other"],
    "current_assets": [
        "Cash and Cash Equivalents",
        "Receivables",
        "Retention Receivable",
        "Inventory",
        "Work in Progress",
        "Prepayments",
        "Other",
    ],
    "current_liabilities": [
        "Payables",
        "Retention Payable",
        "Payroll Liabilities",
        "Tax Liabilities",
        "Provisions",
        "Other",
    ],
    "equity": ["Capital", "Retained Earnings"],
    "revenue": ["Contract Revenue", "Variations", "Claims"],
    "cost_of_works": [
        "Materials",
        "Labour",
        "Plant",
        "Subcontract",
        "Preliminaries",
        "Other",
    ],
    "overheads": ["Administration", "Establishment", "Depreciation", "Finance"],
    "other_income_expense": ["Other Income", "Other Expense"],
    "taxation": ["Income Tax", "Withholding Tax"],
    "suspense": ["Suspense", "Opening Balances"],
}

SUBTYPES_BY_TYPE: dict[str, list[str]] = {
    "Cash and Cash Equivalents": ["Bank", "Cash", "Mobile Money"],
    "Receivables": ["Trade Debtors", "Other Debtors"],
    "Retention Receivable": ["Contract Retention"],
    "Inventory": ["Materials on Site", "Materials in Store"],
    "Work in Progress": ["Uncertified Work", "Contract Asset"],
    "Payables": ["Trade Creditors", "Subcontractors", "Other Creditors"],
    "Retention Payable": ["Subcontract Retention"],
    "Payroll Liabilities": ["Wages Payable", "Statutory Deductions"],
    "Tax Liabilities": ["VAT", "Withholding Tax", "Income Tax"],
    "Plant and Equipment": ["Owned Plant", "Accumulated Depreciation"],
    "Contract Revenue": ["Certified Work", "Retention Released"],
    "Materials": ["Purchased", "Issued from Store"],
    "Labour": ["Own Labour", "Casual Labour"],
    "Subcontract": ["Domestic", "Nominated"],
}


def subclass_for_code(code: str) -> str | None:
    """Which subclass owns this code, or None if it falls outside every range."""
    try:
        number = int(code)
    except (TypeError, ValueError):
        return None
    for slug, (_, low, high) in SUBCLASS_RANGES.items():
        if low <= number <= high:
            return slug
    return None


def range_of(subclass: str) -> tuple[int, int] | None:
    entry = SUBCLASS_RANGES.get(subclass)
    return (entry[1], entry[2]) if entry else None


def normal_balance_for(account_class: str) -> str:
    """Derived from the class, never stored: an asset that credits normally is
    a bug rather than a configuration choice. A contra asset is the deliberate
    exception — it lives on the asset side of the sheet and credits."""
    return "debit" if account_class in ("asset", "expense") else "credit"


def report_for(account_class: str) -> str:
    return "profit_loss" if account_class in ("income", "expense") else "balance_sheet"
