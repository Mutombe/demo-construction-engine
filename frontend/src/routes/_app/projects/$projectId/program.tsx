import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { FlagBanner, Path, Warning } from "@phosphor-icons/react";
import { useState } from "react";
import { Can } from "@/components/layout/Can";
import { Button } from "@/components/ui/button";
import { confirmDialog } from "@/components/ui/confirm";
import { PageSkeleton } from "@/components/ui/skeleton";
import { GanttChart } from "@/features/gantt/GanttChart";
import { errDetail } from "@/lib/api/errors";
import {
  useClearBaseline,
  useGetGantt,
  useSetBaseline,
} from "@/lib/api/generated/endpoints";
import { fmtDate } from "@/lib/format";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/projects/$projectId/program")({
  component: ProgramTab,
});

function ProgramTab() {
  const { projectId } = Route.useParams();
  const queryClient = useQueryClient();
  const { data, isLoading } = useGetGantt(projectId);
  const setBaseline = useSetBaseline();
  const clearBaseline = useClearBaseline();
  const [showCritical, setShowCritical] = useState(true);
  const [showBaseline, setShowBaseline] = useState(true);

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["/api/v1/projects"] });

  const saveBaseline = async () => {
    const already = data?.has_baseline;
    if (
      already &&
      !(await confirmDialog({
        title: "Re-baseline programme",
        message:
          "Replace the saved baseline with the current dates? Slippage will then be measured against today's programme.",
        tone: "danger",
      }))
    )
      return;
    try {
      await setBaseline.mutateAsync({ projectId });
      await refresh();
      toast.success("Baseline saved — slippage now measured against it");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const removeBaseline = async () => {
    if (
      !(await confirmDialog({
        title: "Clear baseline",
        message: "Remove the saved baseline? Slippage will no longer be tracked.",
        tone: "danger",
      }))
    )
      return;
    try {
      await clearBaseline.mutateAsync({ projectId });
      await refresh();
      toast.success("Baseline cleared");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  if (isLoading || !data) {
    return <PageSkeleton rows={6} />;
  }
  if (!data.tasks.length && !data.phases.length) {
    return (
      <div className="rounded-lg border bg-card p-10 text-center text-muted-foreground">
        No phases or tasks scheduled yet — add them under the Tasks tab.
      </div>
    );
  }

  const slippage = data.worst_slippage_days ?? 0;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm">
          <Path className={cn("size-4", showCritical ? "text-destructive" : "text-muted-foreground")} />
          <span className="text-muted-foreground">Critical path:</span>
          <span className="font-medium tabular-nums">
            {data.critical_path_length} task{data.critical_path_length === 1 ? "" : "s"}
          </span>
          {data.project_finish && (
            <span className="text-muted-foreground">
              · finishes {fmtDate(data.project_finish)}
            </span>
          )}
        </div>

        {data.has_baseline && (
          <div
            className={cn(
              "flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm",
              slippage > 0 && "border-warning/50",
            )}
          >
            {slippage > 0 ? (
              <Warning className="size-4 text-warning" />
            ) : (
              <FlagBanner className="size-4 text-muted-foreground" />
            )}
            <span className="text-muted-foreground">Against baseline:</span>
            <span
              className={cn("font-medium tabular-nums", slippage > 0 && "text-warning")}
            >
              {slippage > 0 ? `${slippage} days late` : "on programme"}
            </span>
          </div>
        )}

        <div className="ml-auto flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={showCritical}
              onChange={(e) => setShowCritical(e.target.checked)}
            />
            Critical path
          </label>
          {data.has_baseline && (
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={showBaseline}
                onChange={(e) => setShowBaseline(e.target.checked)}
              />
              Baseline
            </label>
          )}
          <Can perm="task:write">
            <Button
              variant="outline"
              size="sm"
              disabled={setBaseline.isPending}
              onClick={() => void saveBaseline()}
            >
              <FlagBanner /> {data.has_baseline ? "Re-baseline" : "Set Baseline"}
            </Button>
            {data.has_baseline && (
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive"
                disabled={clearBaseline.isPending}
                onClick={() => void removeBaseline()}
              >
                Clear
              </Button>
            )}
          </Can>
        </div>
      </div>

      <GanttChart payload={data} showCritical={showCritical} showBaseline={showBaseline} />
    </div>
  );
}
