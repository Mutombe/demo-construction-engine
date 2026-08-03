import { makeBadge, type Variant } from "@/features/procurement/StatusBadges";

const VALUATION: Record<string, [Variant, string]> = {
  draft: ["secondary", "Draft"],
  issued: ["default", "Issued"],
  paid: ["success", "Paid"],
  cancelled: ["destructive", "Cancelled"],
};

export const ValuationStatusBadge = makeBadge(VALUATION);
