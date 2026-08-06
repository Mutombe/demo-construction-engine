import { keepPreviousData } from "@tanstack/react-query";
import { Link, createFileRoute } from "@tanstack/react-router";
import { CalendarBlank, Diamond, ListChecks, UserCircle, Warning } from "@phosphor-icons/react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { PageSkeleton } from "@/components/ui/skeleton";
import { CommentThread } from "@/features/comments/CommentThread";
import { WorkStatusBadge } from "@/features/projects/StatusBadge";
import { useGetProject, useGetTask, useListTasks } from "@/lib/api/generated/endpoints";
import { fmtDate } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/tasks/$taskId")({
  component: TaskDetail,
});

const PRIORITY_TONE: Record<string, string> = {
  urgent: "bg-destructive/10 text-destructive",
  high: "bg-warning/15 text-warning",
  normal: "bg-secondary text-secondary-foreground",
  low: "bg-muted text-muted-foreground",
};

function TaskDetail() {
  const { taskId } = Route.useParams();
  const { data: task } = useGetTask(taskId);
  const { data: project } = useGetProject(task?.project_id ?? "", {
    query: { enabled: !!task?.project_id },
  });
  // Subtasks and the parent both come from the project's task list, which is
  // already loaded on the way in rather than costing another round trip.
  const { data: siblings } = useListTasks(
    task?.project_id ?? "",
    undefined,
    { query: { enabled: !!task?.project_id, placeholderData: keepPreviousData } },
  );

  if (!task) return <PageSkeleton rows={4} />;

  const subtasks = (siblings ?? []).filter((t) => t.parent_id === task.id);
  const parent = (siblings ?? []).find((t) => t.id === task.parent_id);
  const overdue =
    task.planned_end && task.status !== "done" && new Date(task.planned_end) < new Date();

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Projects", to: "/projects" },
          ...(project
            ? [{ label: `${project.code} ${project.name}`, to: `/projects/${project.id}` }]
            : []),
          { label: task.name },
        ]}
      />

      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {task.is_milestone && <Diamond className="size-4 text-primary" weight="fill" />}
            <h1 className="text-xl font-semibold tracking-tight">{task.name}</h1>
            <WorkStatusBadge status={task.status ?? "not_started"} />
            {task.priority !== "normal" && (
              <span
                className={cn(
                  "rounded px-1.5 py-0.5 text-xs font-medium capitalize",
                  PRIORITY_TONE[task.priority ?? "normal"],
                )}
              >
                {task.priority}
              </span>
            )}
          </div>
          {parent && (
            <p className="mt-1 text-sm text-muted-foreground">
              Part of{" "}
              <Link
                to="/tasks/$taskId"
                params={{ taskId: parent.id }}
                className="underline-offset-2 hover:text-primary hover:underline"
              >
                {parent.name}
              </Link>
            </p>
          )}
          {(task.tags ?? []).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {(task.tags ?? []).map((tag) => (
                <span
                  key={tag}
                  className="rounded bg-secondary px-1.5 py-0.5 text-xs text-secondary-foreground"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {task.description && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Scope</CardTitle>
              </CardHeader>
              <CardContent className="whitespace-pre-wrap text-sm leading-relaxed">
                {task.description}
              </CardContent>
            </Card>
          )}

          {subtasks.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <ListChecks className="size-4" />
                  Steps
                  <span className="text-sm font-normal text-muted-foreground">
                    {subtasks.filter((t) => t.status === "done").length} of {subtasks.length} done
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5">
                {subtasks.map((sub) => (
                  <div key={sub.id} className="flex items-center gap-2 text-sm">
                    <span
                      className={cn(
                        "size-1.5 shrink-0 rounded-full",
                        sub.status === "done" ? "bg-success" : "bg-muted-foreground/40",
                      )}
                    />
                    <Link
                      to="/tasks/$taskId"
                      params={{ taskId: sub.id }}
                      className={cn(
                        "flex-1 truncate underline-offset-2 hover:text-primary hover:underline",
                        sub.status === "done" && "text-muted-foreground line-through",
                      )}
                    >
                      {sub.name}
                    </Link>
                    {sub.assignee_name && (
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {sub.assignee_name}
                      </span>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Discussion</CardTitle>
            </CardHeader>
            <CardContent>
              <CommentThread entityType="task" entityId={taskId} />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Progress</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <div className="mb-1 flex justify-between text-sm">
                  <span className="text-muted-foreground">Complete</span>
                  <span className="font-medium tabular-nums">{task.progress_pct}%</span>
                </div>
                <Progress value={task.progress_pct ?? 0} />
              </div>
              <Detail
                icon={<UserCircle />}
                label="Assigned to"
                value={task.assignee_name ?? "Nobody"}
              />
              <Detail icon={<CalendarBlank />} label="Phase" value={task.phase_name ?? "—"} />
              <Detail
                icon={<CalendarBlank />}
                label="Planned"
                value={
                  task.planned_start && task.planned_end
                    ? `${fmtDate(task.planned_start)} to ${fmtDate(task.planned_end)}`
                    : "No dates set"
                }
              />
              {overdue && (
                <p className="flex items-center gap-1.5 text-sm text-destructive">
                  <Warning className="size-4" /> Past its planned finish
                </p>
              )}
              {task.wbs_code && (
                <Detail icon={<ListChecks />} label="WBS" value={task.wbs_code} />
              )}
            </CardContent>
          </Card>

          {(task.predecessor_ids ?? []).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Waiting on</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5">
                {(task.predecessor_ids ?? []).map((id) => {
                  const dep = (siblings ?? []).find((t) => t.id === id);
                  return (
                    <Link
                      key={id}
                      to="/tasks/$taskId"
                      params={{ taskId: id }}
                      className="block truncate text-sm underline-offset-2 hover:text-primary hover:underline"
                    >
                      {dep?.name ?? "Another task"}
                    </Link>
                  );
                })}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function Detail({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-baseline gap-2 text-sm">
      <span className="mt-0.5 text-muted-foreground [&_svg]:size-3.5">{icon}</span>
      <span className="text-muted-foreground">{label}</span>
      <span className="ml-auto truncate text-right font-medium">{value}</span>
    </div>
  );
}
