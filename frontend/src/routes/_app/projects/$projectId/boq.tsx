import { createFileRoute } from "@tanstack/react-router";
import { DownloadSimple, ListChecks, Table as TableIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { toast } from "@/lib/toast";
import { Button } from "@/components/ui/button";
import { PageSkeleton } from "@/components/ui/skeleton";
import { BoqSheet } from "@/features/boq/BoqSheet";
import { VariationRegister } from "@/features/boq/VariationRegister";
import { downloadFile } from "@/lib/api/download";
import { useGetBoq } from "@/lib/api/generated/endpoints";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/projects/$projectId/boq")({
  component: BoqTab,
});

const VIEWS = [
  { key: "sheet", label: "Bill of Quantities", icon: <TableIcon /> },
  { key: "variations", label: "Variation Register", icon: <ListChecks /> },
] as const;

function BoqTab() {
  const { projectId } = Route.useParams();
  const { data, isLoading } = useGetBoq(projectId);
  const [view, setView] = useState<"sheet" | "variations">("sheet");

  const exportCost = (format: "csv" | "xlsx") =>
    downloadFile(
      `/api/v1/reports/project-cost?project_id=${projectId}&format=${format}`,
      `project_cost_report.${format}`,
    ).catch(() => toast.error("Export failed"));

  if (isLoading || !data) {
    return <PageSkeleton rows={5} />;
  }
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex gap-1 rounded-md border p-1">
          {VIEWS.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setView(item.key)}
              className={cn(
                "flex items-center gap-1.5 rounded-sm px-3 py-1.5 text-sm font-medium transition-colors",
                view === item.key
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => void exportCost("csv")}>
            <DownloadSimple /> Cost Report CSV
          </Button>
          <Button variant="outline" size="sm" onClick={() => void exportCost("xlsx")}>
            <DownloadSimple /> Cost Report Excel
          </Button>
        </div>
      </div>
      {view === "sheet" ? (
        <BoqSheet projectId={projectId} tree={data} />
      ) : (
        <VariationRegister projectId={projectId} />
      )}
    </div>
  );
}
