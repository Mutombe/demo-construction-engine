import { makeBadge } from "@/features/procurement/StatusBadges";

export const ExpenseStatusBadge = makeBadge({
  pending: ["warning", "Pending"],
  approved: ["success", "Approved"],
  rejected: ["destructive", "Rejected"],
  cancelled: ["outline", "Cancelled"],
});
