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
  | "users:manage"
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

const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  admin: [
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
    "valuation:write",
    "ingestion:use",
    "ingestion:approve",
    "payroll:read",
    "payroll:write",
    "timesheet:write",
  ],
  site_manager: [...READ_ALL, "media:write", "task:write", "cost:write", "site:write", "expense:submit", "inventory:issue", "ingestion:use", "timesheet:write"],
  procurement_officer: [...READ_ALL, "media:write", "procurement:write", "po:approve", "expense:submit", "inventory:write", "inventory:issue", "ingestion:use", "ingestion:approve"],
  viewer: [...READ_ALL],
};

export function can(role: Role | undefined, permission: Permission): boolean {
  if (!role) return false;
  return ROLE_PERMISSIONS[role]?.includes(permission) ?? false;
}
