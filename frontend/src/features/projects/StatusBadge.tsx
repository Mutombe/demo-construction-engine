import { Badge } from "@/components/ui/badge";
import { STATUS_LABELS } from "@/lib/format";

const PROJECT_VARIANTS: Record<string, "default" | "secondary" | "success" | "warning" | "destructive" | "outline"> = {
  planning: "secondary",
  active: "success",
  on_hold: "warning",
  completed: "default",
  cancelled: "destructive",
};

const WORK_VARIANTS: typeof PROJECT_VARIANTS = {
  not_started: "secondary",
  in_progress: "default",
  blocked: "destructive",
  done: "success",
  cancelled: "outline",
};

export function ProjectStatusBadge({ status }: { status: string }) {
  return <Badge variant={PROJECT_VARIANTS[status] ?? "secondary"}>{STATUS_LABELS[status] ?? status}</Badge>;
}

export function WorkStatusBadge({ status }: { status: string }) {
  return <Badge variant={WORK_VARIANTS[status] ?? "secondary"}>{STATUS_LABELS[status] ?? status}</Badge>;
}
