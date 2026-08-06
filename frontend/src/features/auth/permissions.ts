import type { Role } from "./store";

export type Permission =
  | "project:read"
  | "project:write"
  | "task:read"
  | "task:write"
  | "boq:read"
  | "boq:write"
  | "cost:read"
  | "cost:write"
  | "client:write"
  | "procurement:read"
  | "procurement:write"
  | "po:approve"
  | "site:read"
  | "site:write"
  | "expense:read"
  | "expense:submit"
  | "expense:approve"
  | "inventory:read"
  | "inventory:write"
  | "inventory:issue"
  | "valuation:read"
  | "valuation:write"
  | "ingestion:use"
  | "ingestion:approve"
  | "payroll:read"
  | "payroll:write"
  | "timesheet:write"
  | "media:write"
  | "requisition:create"
  | "requisition:action"
  | "users:manage"
  | "accounting:read"
  | "settings:manage";

const READ_ALL: Permission[] = [
  "project:read",
  "task:read",
  "boq:read",
  "cost:read",
  "procurement:read",
  "site:read",
  "expense:read",
  "inventory:read",
  "valuation:read",
];

/** Exported so Settings can show the same table the app enforces, which
 *  means the displayed matrix cannot drift from actual behaviour. */
export const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  admin: [
    "accounting:read",
    ...READ_ALL,
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
    "users:manage",
    "settings:manage",
  ],
  project_manager: [
    "accounting:read",
    ...READ_ALL,
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
  ],
  site_manager: [...READ_ALL, "media:write", "requisition:create", "task:write", "cost:write", "site:write", "expense:submit", "inventory:issue", "ingestion:use", "timesheet:write"],
  procurement_officer: [...READ_ALL, "media:write", "requisition:action", "procurement:write", "po:approve", "expense:submit", "inventory:write", "inventory:issue", "ingestion:use", "ingestion:approve"],
  viewer: [...READ_ALL],
};

/** What the server says this session may do.
 *
 *  Set once at sign-in from /permissions/me. The compiled ROLE_PERMISSIONS
 *  table below is only the fallback for the moment before that arrives — the
 *  matrix is editable now, so a table baked into the bundle would be a
 *  snapshot of whatever it was on the day of the last deploy.
 */
let live: Set<string> | null = null;

export function setLivePermissions(permissions: string[] | null): void {
  live = permissions ? new Set(permissions) : null;
}

export function can(role: Role | undefined, permission: Permission): boolean {
  if (live) return live.has(permission);
  if (!role) return false;
  return ROLE_PERMISSIONS[role]?.includes(permission) ?? false;
}
