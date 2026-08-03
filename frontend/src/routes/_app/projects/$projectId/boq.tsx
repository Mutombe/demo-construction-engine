import { createFileRoute } from "@tanstack/react-router";
import { DownloadSimple } from "@phosphor-icons/react";
import { toast } from "@/lib/toast";
import { Button } from "@/components/ui/button";
import { PageSkeleton } from "@/components/ui/skeleton";
import { BoqSheet } from "@/features/boq/BoqSheet";
import { downloadFile } from "@/lib/api/download";
import { useGetBoq } from "@/lib/api/generated/endpoints";

export const Route = createFileRoute("/_app/projects/$projectId/boq")({
  component: BoqTab,
});

function BoqTab() {
  const { projectId } = Route.useParams();
  const { data, isLoading } = useGetBoq(projectId);

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
      <div className="mb-3 flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={() => void exportCost("csv")}>
          <DownloadSimple /> Cost Report CSV
        </Button>
        <Button variant="outline" size="sm" onClick={() => void exportCost("xlsx")}>
          <DownloadSimple /> Cost Report Excel
        </Button>
      </div>
      <BoqSheet projectId={projectId} tree={data} />
    </div>
  );
}
