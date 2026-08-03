import { Link, createFileRoute } from "@tanstack/react-router";
import { Can } from "@/components/layout/Can";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EntityLink } from "@/components/ui/linked-row";
import { PortalAccessCard } from "@/features/portal/PortalAccessCard";
import { WorkStatusBadge } from "@/features/projects/StatusBadge";
import {
  useGetBoqSummary,
  useGetProject,
  useListCostEntries,
  useListPhases,
  useListTasks,
} from "@/lib/api/generated/endpoints";
import { fmtDate, money, STATUS_LABELS } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/projects/$projectId/")({
  component: OverviewTab,
});

function OverviewTab() {
  const { projectId } = Route.useParams();
  const { data: project } = useGetProject(projectId);
  const { data: phases } = useListPhases(projectId);
  const { data: tasks } = useListTasks(projectId);
  const { data: boq } = useGetBoqSummary(projectId);
  const { data: costs } = useListCostEntries(projectId, { page_size: 8 });

  const today = new Date().toISOString().slice(0, 10);
  const overdue = tasks?.filter(
    (t) =>
      t.planned_end &&
      t.planned_end < today &&
      !["done", "cancelled"].includes(t.status ?? ""),
  );

  return (
    <div className="grid gap-4 xl:grid-cols-3">
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle>Phases</CardTitle>
          <Link
            to="/projects/$projectId/program"
            params={{ projectId }}
            className="text-xs text-primary hover:underline"
          >
            View program →
          </Link>
        </CardHeader>
        <CardContent className="space-y-2">
          {!phases?.length && <p className="text-sm text-muted-foreground">No phases yet.</p>}
          {phases?.map((phase) => (
            <div
              key={phase.id}
              className="flex items-center justify-between gap-2 rounded-md border p-2.5"
            >
              <div>
                <div className="text-sm font-medium">
                  {phase.sequence}. {phase.name}
                </div>
                <div className="text-xs text-muted-foreground">
                  {fmtDate(phase.planned_start)} → {fmtDate(phase.planned_end)}
                </div>
              </div>
              <WorkStatusBadge status={phase.status ?? "not_started"} />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Budget by category</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2.5">
          {!boq?.by_category.length && (
            <p className="text-sm text-muted-foreground">No BOQ captured yet.</p>
          )}
          {boq?.by_category.map((cat) => {
            const used = Number(cat.budget) ? (Number(cat.actual) / Number(cat.budget)) * 100 : 0;
            return (
              <div key={cat.cost_category}>
                <div className="mb-1 flex justify-between text-sm">
                  <span className="capitalize">{cat.cost_category}</span>
                  <span
                    className={cn(
                      "font-medium",
                      used > 100 ? "text-destructive" : "text-muted-foreground",
                    )}
                  >
                    {money(cat.actual)} / {money(cat.budget)}
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                  <div
                    className={cn(
                      "h-full rounded-full",
                      used > 100 ? "bg-destructive" : "bg-primary",
                    )}
                    style={{ width: `${Math.min(100, used)}%` }}
                  />
                </div>
              </div>
            );
          })}
          {boq && Number(boq.unallocated_actual) > 0 && (
            <p className="pt-1 text-xs text-muted-foreground">
              + {money(boq.unallocated_actual)} unallocated site costs
            </p>
          )}
        </CardContent>
      </Card>

      <div className="space-y-4">
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className={cn(overdue?.length && "text-destructive")}>
              Overdue tasks {overdue?.length ? `(${overdue.length})` : ""}
            </CardTitle>
            <Link
              to="/projects/$projectId/tasks"
              params={{ projectId }}
              className="text-xs text-primary hover:underline"
            >
              View tasks →
            </Link>
          </CardHeader>
          <CardContent className="space-y-2">
            {!overdue?.length && (
              <p className="text-sm text-muted-foreground">Nothing overdue. 🎉</p>
            )}
            {overdue?.slice(0, 5).map((t) => (
              <div key={t.id} className="rounded-md border border-destructive/30 p-2.5">
                <div className="text-sm font-medium">
                  {t.wbs_code} {t.name}
                </div>
                <div className="text-xs text-muted-foreground">
                  Due {fmtDate(t.planned_end)} · {t.assignee_name ?? "Unassigned"} ·{" "}
                  {STATUS_LABELS[t.status ?? ""] ?? t.status}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent costs</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {!costs?.items.length && (
              <p className="text-sm text-muted-foreground">No cost entries yet.</p>
            )}
            {costs?.items.map((entry) => (
              <div key={entry.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="truncate text-muted-foreground">
                  {fmtDate(entry.entry_date)} ·{" "}
                  {entry.description ??
                    (entry.boq_item_code ? (
                      <EntityLink
                        to="/projects/$projectId/boq"
                        params={{ projectId }}
                        className="font-mono text-xs font-normal"
                      >
                        {entry.boq_item_code}
                      </EntityLink>
                    ) : (
                      "—"
                    ))}
                </span>
                <span className="shrink-0 font-medium">{money(entry.amount)}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        {project?.client_id && (
          <Can perm="project:write">
            <PortalAccessCard clientId={project.client_id} clientName={project.client_name} />
          </Can>
        )}
      </div>
    </div>
  );
}
