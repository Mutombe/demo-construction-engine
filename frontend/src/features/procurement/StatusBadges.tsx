import { Badge } from "@/components/ui/badge";

export type Variant = "default" | "secondary" | "success" | "warning" | "destructive" | "outline";

const RFQ: Record<string, [Variant, string]> = {
  draft: ["secondary", "Draft"],
  issued: ["default", "Issued"],
  closed: ["success", "Closed"],
};

const QUOTE: Record<string, [Variant, string]> = {
  received: ["secondary", "Received"],
  accepted: ["success", "Accepted"],
  rejected: ["outline", "Rejected"],
};

const PO: Record<string, [Variant, string]> = {
  draft: ["secondary", "Draft"],
  issued: ["default", "Issued"],
  received: ["success", "Received"],
  cancelled: ["destructive", "Cancelled"],
};

export function makeBadge(map: Record<string, [Variant, string]>) {
  return function StatusBadge({ status }: { status: string }) {
    const [variant, label] = map[status] ?? ["secondary", status];
    return <Badge variant={variant}>{label}</Badge>;
  };
}

export const RfqStatusBadge = makeBadge(RFQ);
export const QuoteStatusBadge = makeBadge(QUOTE);
export const PoStatusBadge = makeBadge(PO);
