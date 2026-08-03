import { format, parseISO } from "date-fns";

const currencyFmt = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const currencyFullFmt = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

export function money(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return currencyFmt.format(Number(value));
}

export function moneyExact(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return currencyFullFmt.format(Number(value));
}

export function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  return format(parseISO(value), "dd MMM yyyy");
}

export function fmtDateShort(value: string | null | undefined): string {
  if (!value) return "—";
  return format(parseISO(value), "dd MMM");
}

export function pct(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${value}%`;
}

export const STATUS_LABELS: Record<string, string> = {
  planning: "Planning",
  active: "Active",
  on_hold: "On Hold",
  completed: "Completed",
  cancelled: "Cancelled",
  not_started: "Not Started",
  in_progress: "In Progress",
  blocked: "Blocked",
  done: "Done",
};

export const ROLE_LABELS: Record<string, string> = {
  admin: "Administrator",
  project_manager: "Project Manager",
  site_manager: "Site Manager",
  procurement_officer: "Procurement Officer",
  viewer: "Viewer",
};
