import { makeBadge, type Variant } from "@/features/procurement/StatusBadges";

const INGESTION: Record<string, [Variant, string]> = {
  received: ["secondary", "Received"],
  failed: ["destructive", "Failed"],
  needs_info: ["warning", "Needs review"],
  drafted: ["default", "Ready to approve"],
  posted: ["success", "Posted"],
  rejected: ["outline", "Rejected"],
};

export const IngestionStatusBadge = makeBadge(INGESTION);
