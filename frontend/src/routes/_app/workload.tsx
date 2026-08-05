import { keepPreviousData } from "@tanstack/react-query";
import { Link, createFileRoute } from "@tanstack/react-router";
import { CalendarBlank, UsersThree, Warning } from "@phosphor-icons/react";
import { z } from "zod";
import { PageHeader } from "@/components/layout/AppShell";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Select } from "@/components/ui/select";
import { Tooltip } from "@/components/ui/tooltip";
import { useGetWorkload, useListProjects } from "@/lib/api/generated/endpoints";
import { cn } from "@/lib/utils";

const searchSchema = z.object({
  weeks: z.number().int().min(1).max(12).optional().default(4),
  project_id: z.string().optional(),
  limit: z.number().int().min(1).max(10).optional().default(2),
});

export const Route = createFileRoute("/_app/workload")({
  validateSearch: searchSchema,
  component: WorkloadPage,
});

const iso = (d: Date) => d.toISOString().slice(0, 10);

function WorkloadPage() {
  const { weeks, project_id, limit } = Route.useSearch();
  const navigate = Route.useNavigate();

  const start = new Date();
  const end = new Date();
  end.setDate(end.getDate() + weeks * 7 - 1);

  const { data: projects } = useListProjects({ page: 1, page_size: 100 });
  const { data, isLoading } = useGetWorkload(
    { start: iso(start), end: iso(end), project_id: project_id || undefined, limit },
    { query: { placeholderData: keepPreviousData } },
  );

  const stretched = data?.people.filter((p) => p.overloaded_days > 0).length ?? 0;

  return (
    <div>
      <PageHeader
        title="Workload"
        description="Who is booked on what, and where the days collide"
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Select
          className="w-56"
          value={project_id ?? ""}
          onChange={(e) =>
            void navigate({
              search: (prev) => ({ ...prev, project_id: e.target.value || undefined }),
            })
          }
        >
          <option value="">Every project</option>
          {projects?.items.map((p) => (
            <option key={p.id} value={p.id}>
              {p.code} {p.name}
            </option>
          ))}
        </Select>
        <Select
          className="w-40"
          value={String(weeks)}
          onChange={(e) =>
            void navigate({ search: (prev) => ({ ...prev, weeks: Number(e.target.value) }) })
          }
        >
          <option value="2">Next 2 weeks</option>
          <option value="4">Next 4 weeks</option>
          <option value="8">Next 8 weeks</option>
          <option value="12">Next 12 weeks</option>
        </Select>
        <Select
          className="w-52"
          value={String(limit)}
          onChange={(e) =>
            void navigate({ search: (prev) => ({ ...prev, limit: Number(e.target.value) }) })
          }
        >
          <option value="1">Flag above 1 job a day</option>
          <option value="2">Flag above 2 jobs a day</option>
          <option value="3">Flag above 3 jobs a day</option>
          <option value="4">Flag above 4 jobs a day</option>
        </Select>
        {stretched > 0 && (
          <Badge variant="warning" className="ml-auto">
            <Warning className="mr-1 size-3" />
            {stretched} {stretched === 1 ? "person is" : "people are"} double booked
          </Badge>
        )}
      </div>

      {isLoading && !data && (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-28 animate-pulse rounded-lg border bg-muted/40" />
          ))}
        </div>
      )}

      {data && data.people.length === 0 && (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={<UsersThree />}
              title="No open work in this window"
              hint="Assign someone to a task with dates and it will show up here."
            />
          </CardContent>
        </Card>
      )}

      <div className="space-y-3">
        {data?.people.map((person) => (
          <Card key={person.user_id ?? "unassigned"}>
            <CardContent className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-medium">{person.full_name}</h3>
                    {person.overloaded_days > 0 && (
                      <Badge variant="warning">
                        {person.overloaded_days}{" "}
                        {person.overloaded_days === 1 ? "day" : "days"} double booked
                      </Badge>
                    )}
                    {person.user_id === null && <Badge variant="outline">Nobody assigned</Badge>}
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {person.open_tasks} open {person.open_tasks === 1 ? "job" : "jobs"} ·{" "}
                    {person.busy_days} busy {person.busy_days === 1 ? "day" : "days"} · peak{" "}
                    {person.peak_concurrency} at once
                    {person.hours_booked > 0 && <> · {person.hours_booked}h booked</>}
                  </p>
                </div>
                <div className="text-right text-xs text-muted-foreground">
                  {person.next_free_day ? (
                    <>
                      <CalendarBlank className="mr-1 inline size-3" />
                      Free from{" "}
                      {new Date(`${person.next_free_day}T00:00:00`).toLocaleDateString(undefined, {
                        day: "numeric",
                        month: "short",
                      })}
                    </>
                  ) : (
                    <span>Booked solid</span>
                  )}
                </div>
              </div>

              <DayStrip days={person.days} />

              <ul className="mt-3 space-y-1">
                {person.tasks.map((task) => (
                  <li key={task.id} className="flex items-center gap-2 text-sm">
                    <span
                      className={cn(
                        "size-1.5 shrink-0 rounded-full",
                        task.status === "blocked"
                          ? "bg-destructive"
                          : task.status === "in_progress"
                            ? "bg-primary"
                            : "bg-muted-foreground/40",
                      )}
                    />
                    <Link
                      to="/projects/$projectId"
                      params={{ projectId: task.project_id }}
                      className="truncate underline-offset-2 hover:text-primary hover:underline"
                    >
                      {task.name}
                    </Link>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {task.project_code}
                    </span>
                    {!task.is_scheduled && (
                      <Tooltip content="No dates, so it cannot be placed on the calendar">
                        <span className="shrink-0 text-xs text-muted-foreground">· undated</span>
                      </Tooltip>
                    )}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

/** One cell per day. Colour is load, not status: empty, busy, over. */
function DayStrip({
  days,
}: {
  days: { day: string; task_count: number; over: boolean }[];
}) {
  return (
    <div className="mt-3 flex flex-wrap gap-0.5">
      {days.map((day) => {
        const date = new Date(`${day.day}T00:00:00`);
        const weekend = date.getDay() === 0 || date.getDay() === 6;
        return (
          <Tooltip
            key={day.day}
            content={`${date.toLocaleDateString(undefined, {
              weekday: "short",
              day: "numeric",
              month: "short",
            })} — ${day.task_count} ${day.task_count === 1 ? "job" : "jobs"}`}
          >
            <span
              className={cn(
                "h-6 w-2.5 rounded-sm",
                day.over
                  ? "bg-warning"
                  : day.task_count > 0
                    ? "bg-primary/70"
                    : weekend
                      ? "bg-muted"
                      : "bg-muted/60",
              )}
            />
          </Tooltip>
        );
      })}
    </div>
  );
}
