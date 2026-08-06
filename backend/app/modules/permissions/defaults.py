"""The permission vocabulary, and the matrix the system starts with.

Lifted verbatim from the rules the app already enforced, so switching to a
stored matrix changes nobody's access on the day it ships. Editing is the new
part; the starting point is exactly what it was.
"""

from app.common.enums import UserRole

# module -> actions. The module is what a person recognises on the sidebar;
# the action is what they are trying to do to it.
PERMISSIONS: dict[str, list[str]] = {
    "project": ["read", "write"],
    "task": ["read", "write"],
    "boq": ["read", "write"],
    "cost": ["read", "write"],
    "client": ["write"],
    "procurement": ["read", "write"],
    "po": ["approve"],
    "requisition": ["create", "action"],
    "site": ["read", "write"],
    "expense": ["read", "submit", "approve"],
    "inventory": ["read", "write", "issue"],
    "valuation": ["read", "write"],
    "payroll": ["read", "write"],
    "timesheet": ["write"],
    "media": ["write"],
    "ingestion": ["use", "approve"],
    "accounting": ["read"],
    "users": ["manage"],
    "settings": ["manage"],
}

MODULE_LABELS: dict[str, str] = {
    "project": "Projects",
    "task": "Tasks and programme",
    "boq": "Bills of quantities",
    "cost": "Cost ledger",
    "client": "Clients",
    "procurement": "Procurement",
    "po": "Purchase orders",
    "requisition": "Material requests",
    "site": "Site diary and issues",
    "expense": "Expenses",
    "inventory": "Inventory",
    "valuation": "Valuations",
    "payroll": "Payroll",
    "timesheet": "Timesheets",
    "media": "Documents and photos",
    "ingestion": "AI inbox",
    "accounting": "Accounting",
    "users": "Users",
    "settings": "Settings",
}

ACTION_LABELS: dict[str, str] = {
    "read": "View",
    "write": "Create and edit",
    "create": "Raise",
    "action": "Action",
    "approve": "Approve",
    "submit": "Submit",
    "issue": "Issue out",
    "use": "Use",
    "manage": "Manage",
}


def all_permissions() -> list[str]:
    return [f"{module}:{action}" for module, actions in PERMISSIONS.items() for action in actions]


_READ_ALL = [
    "project:read",
    "task:read",
    "boq:read",
    "cost:read",
    "procurement:read",
    "site:read",
    "expense:read",
    "inventory:read",
    "valuation:read",
]

_MANAGER = [
    *_READ_ALL,
    "accounting:read",
    "project:write",
    "task:write",
    "boq:write",
    "cost:write",
    "client:write",
    "procurement:write",
    "po:approve",
    "site:write",
    "expense:submit",
    "expense:approve",
    "inventory:write",
    "inventory:issue",
    "media:write",
    "requisition:create",
    "requisition:action",
    "valuation:write",
    "ingestion:use",
    "ingestion:approve",
    "payroll:read",
    "payroll:write",
    "timesheet:write",
]

DEFAULT_MATRIX: dict[UserRole, list[str]] = {
    UserRole.admin: [*_MANAGER, "users:manage", "settings:manage"],
    UserRole.project_manager: list(_MANAGER),
    UserRole.site_manager: [
        *_READ_ALL,
        "media:write",
        "requisition:create",
        "task:write",
        "cost:write",
        "site:write",
        "expense:submit",
        "inventory:issue",
        "ingestion:use",
        "timesheet:write",
    ],
    UserRole.procurement_officer: [
        *_READ_ALL,
        "media:write",
        "requisition:action",
        "procurement:write",
        "po:approve",
        "expense:submit",
        "inventory:write",
        "inventory:issue",
        "ingestion:use",
        "ingestion:approve",
    ],
    UserRole.viewer: list(_READ_ALL),
}
