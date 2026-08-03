import { Link, Outlet, createFileRoute, useRouterState } from "@tanstack/react-router";
import { PencilSimple } from "@phosphor-icons/react";
import { useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Can } from "@/components/layout/Can";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { PageSkeleton } from "@/components/ui/skeleton";
import { ProjectFormDialog } from "@/features/projects/ProjectFormDialog";
import { ProjectStatusBadge } from "@/features/projects/StatusBadge";
import {
  getGetProjectQueryOptions,
  useGetProject,
  useGetProjectSummary,
} from "@/lib/api/generated/endpoints";
import { fmtDate, money, pct } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/projects/$projectId")({
  component: ProjectDetailLayout,
  loader: ({ context: { queryClient }, params }) =>
    queryClient.ensureQueryData(getGetProjectQueryOptions(params.projectId)),
});

const TABS = [
  { to: "/projects/$projectId", label: "Overview", exact: true },
  { to: "/projects/$projectId/program", label: "Program", exact: false },
  { to: "/projects/$projectId/boq", label: "BOQ", exact: false },
  { to: "/projects/$projectId/tasks", label: "Tasks", exact: false },
  { to: "/projects/$projectId/procurement", label: "Procurement", exact: false },
  { to: "/projects/$projectId/site", label: "Site", exact: false },
  { to: "/projects/$projectId/valuations", label: "Valuations", exact: false },
  { to: "/projects/$projectId/documents", label: "Documents", exact: false },
] as const;

function ProjectDetailLayout() {
  const { projectId } = Route.useParams();
  const { data: project } = useGetProject(projectId);
  const { data: summary } = useGetProjectSummary(projectId);
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const [editOpen, setEditOpen] = useState(false);

  if (!project) {
    return <PageSkeleton rows={5} />;
  }

  const overBudget =
    summary?.budget_variance_pct !== null &&
    summary?.budget_variance_pct !== undefined &&
    summary.budget_variance_pct > 0;

  return (
    <div>
      <div className="mb-4">
        <Breadcrumbs
          items={[{ label: "Projects", to: "/projects" }, { label: project.name }]}
        />
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="text-xl font-semibold tracking-tight">{project.name}</h1>
              <ProjectStatusBadge status={project.status ?? "planning"} />
            </div>
            <div className="mt-1 text-sm text-muted-foreground">
              {project.code} · {project.client_name ?? "—"} ·{" "}
              {fmtDate(project.planned_start)} → {fmtDate(project.planned_end)} ·{" "}
              {money(project.contract_value)} contract
            </div>
          </div>
          <div className="flex items-center gap-5">
            {summary && (
              <>
                <div className="w-44">
                  <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                    <span>Progress</span>
                    <span>{pct(summary.progress_pct)}</span>
                  </div>
                  <Progress value={summary.progress_pct} />
                </div>
                <div className="text-right">
                  <div className="text-xs uppercase tracking-wide text-muted-foreground">
                    Spend vs budget
                  </div>
                  <div
                    className={cn(
                      "text-sm font-semibold",
                      overBudget ? "text-destructive" : "text-foreground",
                    )}
                  >
                    {money(summary.actual_total)} / {money(summary.budget_total)}
                    {summary.budget_variance_pct !== null &&
                      summary.budget_variance_pct !== undefined && (
                        <span className="ml-1 text-xs">
                          ({summary.budget_variance_pct > 0 ? "+" : ""}
                          {summary.budget_variance_pct}%)
                        </span>
                      )}
                  </div>
                </div>
              </>
            )}
            <Can perm="project:write">
              <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
                <PencilSimple /> Edit
              </Button>
            </Can>
          </div>
        </div>
      </div>

      <div className="mb-5 border-b">
        <nav className="-mb-px flex gap-1">
          {TABS.map((tab) => {
            const href = tab.to.replace("$projectId", projectId);
            const active = tab.exact ? pathname === href : pathname.startsWith(href);
            return (
              <Link
                key={tab.label}
                to={tab.to}
                params={{ projectId }}
                className={cn(
                  "border-b-2 px-3.5 py-2 text-sm font-medium transition-colors",
                  active
                    ? "border-primary text-primary"
                    : "border-transparent text-muted-foreground hover:border-border hover:text-foreground",
                )}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>
      </div>

      <Outlet />
      <ProjectFormDialog open={editOpen} onOpenChange={setEditOpen} project={project} />
    </div>
  );
}
