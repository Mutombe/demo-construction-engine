import { createFileRoute } from "@tanstack/react-router";
import { PageSkeleton } from "@/components/ui/skeleton";
import { GanttChart } from "@/features/gantt/GanttChart";
import { useGetGantt } from "@/lib/api/generated/endpoints";

export const Route = createFileRoute("/_app/projects/$projectId/program")({
  component: ProgramTab,
});

function ProgramTab() {
  const { projectId } = Route.useParams();
  const { data, isLoading } = useGetGantt(projectId);

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
  return <GanttChart payload={data} />;
}
