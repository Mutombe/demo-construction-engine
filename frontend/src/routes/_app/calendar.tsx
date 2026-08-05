import { keepPreviousData } from "@tanstack/react-query";
import { Link, createFileRoute } from "@tanstack/react-router";
import { CaretLeft, CaretRight, Diamond, Truck, Warning } from "@phosphor-icons/react";
import { z } from "zod";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Tooltip } from "@/components/ui/tooltip";
import { useGetCalendar, useListProjects } from "@/lib/api/generated/endpoints";
import { cn } from "@/lib/utils";

const searchSchema = z.object({
  month: z.string().optional(),
  project_id: z.string().optional(),
});

export const Route = createFileRoute("/_app/calendar")({
  validateSearch: searchSchema,
  component: CalendarPage,
});

const KIND_STYLE: Record<string, string> = {
  milestone: "bg-primary/15 text-primary",
  task_start: "bg-secondary text-secondary-foreground",
  task_end: "bg-secondary text-secondary-foreground",
  delivery: "bg-warning/15 text-warning",
  valuation: "bg-success/10 text-success",
  requisition: "bg-destructive/10 text-destructive",
};

const KIND_LABEL: Record<string, string> = {
  milestone: "Milestone",
  task_start: "Task starts",
  task_end: "Task due",
  delivery: "Delivery due",
  valuation: "Valuation period ends",
  requisition: "Materials needed",
};

const iso = (d: Date) => d.toISOString().slice(0, 10);

/** Monday-first grid covering the whole month plus the days either side that
 *  share its weeks, so the calendar is always a clean rectangle. */
function gridFor(monthStart: Date): Date[] {
  const first = new Date(monthStart);
  const offset = (first.getDay() + 6) % 7;
  const cursor = new Date(first);
  cursor.setDate(cursor.getDate() - offset);

  const last = new Date(first.getFullYear(), first.getMonth() + 1, 0);
  const trailing = (7 - ((last.getDay() + 6) % 7) - 1 + 7) % 7;
  const end = new Date(last);
  end.setDate(end.getDate() + trailing);

  const days: Date[] = [];
  for (let d = new Date(cursor); d <= end; d.setDate(d.getDate() + 1)) {
    days.push(new Date(d));
  }
  return days;
}

function CalendarPage() {
  const { month, project_id } = Route.useSearch();
  const navigate = Route.useNavigate();

  const anchor = month ? new Date(`${month}-01T00:00:00`) : new Date();
  const monthStart = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  const days = gridFor(monthStart);
  const windowStart = days[0] ?? monthStart;
  const windowEnd = days[days.length - 1] ?? monthStart;

  const { data: projects } = useListProjects({ page: 1, page_size: 100 });
  const { data } = useGetCalendar(
    {
      start: iso(windowStart),
      end: iso(windowEnd),
      project_id: project_id || undefined,
    },
    { query: { placeholderData: keepPreviousData } },
  );

  const byDay = new Map<string, typeof data extends undefined ? never : NonNullable<typeof data>["events"]>();
  for (const event of data?.events ?? []) {
    const list = byDay.get(event.day) ?? [];
    list.push(event);
    byDay.set(event.day, list);
  }

  const shift = (delta: number) => {
    const next = new Date(monthStart.getFullYear(), monthStart.getMonth() + delta, 1);
    void navigate({
      search: (prev) => ({ ...prev, month: `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}` }),
    });
  };

  const todayIso = iso(new Date());

  return (
    <div>
      <PageHeader
        title="Calendar"
        description="Deadlines, deliveries and valuation cut-offs in one place"
      />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Button variant="outline" size="icon" title="Previous month" onClick={() => shift(-1)}>
          <CaretLeft />
        </Button>
        <span className="min-w-44 text-center text-sm font-medium">
          {monthStart.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
        </span>
        <Button variant="outline" size="icon" title="Next month" onClick={() => shift(1)}>
          <CaretRight />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void navigate({ search: (prev) => ({ ...prev, month: undefined }) })}
        >
          Today
        </Button>
        <Select
          className="ml-auto w-56"
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
      </div>

      <div className="overflow-hidden rounded-lg border bg-card">
        <div className="grid grid-cols-7 border-b bg-muted/40">
          {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((label) => (
            <div
              key={label}
              className="px-2 py-1.5 text-center text-[11px] font-medium uppercase tracking-wide text-muted-foreground"
            >
              {label}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7">
          {days.map((day) => {
            const key = iso(day);
            const events = byDay.get(key) ?? [];
            const outside = day.getMonth() !== monthStart.getMonth();
            const weekend = day.getDay() === 0 || day.getDay() === 6;
            return (
              <div
                key={key}
                className={cn(
                  "min-h-28 border-b border-r p-1.5 last:border-r-0",
                  outside && "bg-muted/20",
                  weekend && !outside && "bg-muted/10",
                )}
              >
                <div
                  className={cn(
                    "mb-1 flex h-5 w-5 items-center justify-center rounded-full text-xs",
                    key === todayIso
                      ? "bg-primary font-semibold text-primary-foreground"
                      : outside
                        ? "text-muted-foreground/50"
                        : "text-muted-foreground",
                  )}
                >
                  {day.getDate()}
                </div>
                <div className="space-y-1">
                  {events.slice(0, 3).map((event, i) => (
                    <Tooltip
                      key={`${event.link}-${event.kind}-${i}`}
                      content={`${KIND_LABEL[event.kind] ?? event.kind} · ${event.project_code}`}
                    >
                      <Link
                        to={event.link}
                        className={cn(
                          "flex items-center gap-1 truncate rounded px-1 py-0.5 text-[11px] leading-tight",
                          KIND_STYLE[event.kind] ?? "bg-secondary",
                        )}
                      >
                        {event.kind === "milestone" && (
                          <Diamond className="size-2.5 shrink-0" weight="fill" />
                        )}
                        {event.kind === "delivery" && <Truck className="size-2.5 shrink-0" />}
                        {event.overdue && <Warning className="size-2.5 shrink-0" />}
                        <span className="truncate">{event.title}</span>
                      </Link>
                    </Tooltip>
                  ))}
                  {events.length > 3 && (
                    <div className="px-1 text-[10px] text-muted-foreground">
                      +{events.length - 3} more
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
        {Object.entries(KIND_LABEL).map(([kind, label]) => (
          <span key={kind} className="flex items-center gap-1.5">
            <span className={cn("size-2.5 rounded-sm", KIND_STYLE[kind])} />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}
