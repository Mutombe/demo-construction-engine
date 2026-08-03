import { Link, createFileRoute } from "@tanstack/react-router";
import { AlertTriangle, Building2, CalendarClock, Wallet } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { PageHeader } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { ProjectStatusBadge } from "@/features/projects/StatusBadge";
import { useBudgetAlerts, useDeadlines, useOverview } from "@/lib/api/generated/endpoints";
import { fmtDate, money, pct } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/")({ component: DashboardPage });

function KpiCard({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  tone?: "danger" | "default";
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <div
          className={cn(
            "flex h-10 w-10 items-center justify-center rounded-lg [&_svg]:size-5",
            tone === "danger" ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary",
          )}
        >
          {icon}
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
          <div className="text-xl font-semibold">{value}</div>
        </div>
      </CardContent>
    </Card>
  );
}

function DashboardPage() {
  const { data: overview, isLoading } = useOverview();
  const { data: deadlines } = useDeadlines({ days: 21 });
  const { data: alerts } = useBudgetAlerts({ threshold_pct: 90 });

  if (isLoading || !overview) {
    return <div className="p-8 text-center text-muted-foreground">Loading dashboard…</div>;
  }

  const chartData = overview.projects.map((p) => ({
    name: p.code,
    fullName: p.name,
    budget: Number(p.budget_total),
    actual: Number(p.actual_total),
    over: p.budget_used_pct !== null && p.budget_used_pct !== undefined && p.budget_used_pct > 100,
  }));

  return (
    <div>
      <PageHeader title="Dashboard" description="Portfolio health across all live projects" />

      <div className="mb-5 grid grid-cols-2 gap-4 xl:grid-cols-4">
        <KpiCard label="Active projects" value={overview.active_projects} icon={<Building2 />} />
        <KpiCard
          label="Contract value"
          value={money(overview.portfolio_contract_value)}
          icon={<Wallet />}
        />
        <KpiCard
          label="Spend vs budget"
          value={`${money(overview.portfolio_actual)} / ${money(overview.portfolio_budget)}`}
          icon={<CalendarClock />}
        />
        <KpiCard
          label="Overdue tasks"
          value={overview.overdue_tasks}
          icon={<AlertTriangle />}
          tone={overview.overdue_tasks > 0 ? "danger" : "default"}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle>Budget vs actual by project</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} barGap={2}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
                  <XAxis dataKey="name" tickLine={false} axisLine={false} fontSize={12} />
                  <YAxis
                    tickFormatter={(v: number) => `${Math.round(v / 1000)}k`}
                    tickLine={false}
                    axisLine={false}
                    fontSize={12}
                    width={40}
                  />
                  <Tooltip
                    formatter={(value, name) => [money(Number(value)), String(name)]}
                    labelFormatter={(label) =>
                      chartData.find((d) => d.name === label)?.fullName ?? String(label)
                    }
                  />
                  <Bar dataKey="budget" name="Budget" fill="var(--muted-foreground)" opacity={0.35} radius={[3, 3, 0, 0]} />
                  <Bar dataKey="actual" name="Actual" radius={[3, 3, 0, 0]}>
                    {chartData.map((d) => (
                      <Cell key={d.name} fill={d.over ? "var(--destructive)" : "var(--primary)"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Budget alerts</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2.5">
            {!alerts?.length && (
              <p className="text-sm text-muted-foreground">No lines above 90% of budget.</p>
            )}
            {alerts?.slice(0, 6).map((a) => (
              <Link
                key={`${a.project_id}-${a.scope}-${a.item_code ?? "project"}`}
                to="/projects/$projectId"
                params={{ projectId: a.project_id }}
                className="block rounded-md border p-2.5 transition-colors hover:bg-accent"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">
                    {a.item_code ? `${a.item_code} — ${a.description}` : a.project_name}
                  </span>
                  <span
                    className={cn(
                      "shrink-0 text-sm font-semibold",
                      a.used_pct > 100 ? "text-destructive" : "text-warning",
                    )}
                  >
                    {a.used_pct}%
                  </span>
                </div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  {a.project_code} · {money(a.actual)} of {money(a.budget)}
                </div>
              </Link>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle>Projects</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {overview.projects.map((p) => (
              <Link
                key={p.id}
                to="/projects/$projectId"
                params={{ projectId: p.id }}
                className="block rounded-md border p-3 transition-colors hover:bg-accent"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-medium">{p.name}</span>
                      <ProjectStatusBadge status={p.status} />
                    </div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {p.code} · {p.client_name ?? "—"} · due {fmtDate(p.planned_end)}
                      {p.overdue_tasks > 0 && (
                        <span className="ml-2 font-medium text-destructive">
                          {p.overdue_tasks} overdue
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="w-40 shrink-0">
                    <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                      <span>Progress</span>
                      <span>{pct(p.progress_pct)}</span>
                    </div>
                    <Progress value={p.progress_pct} />
                  </div>
                </div>
              </Link>
            ))}
          </CardContent>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Upcoming deadlines (21 days)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {!deadlines?.length && (
              <p className="text-sm text-muted-foreground">Nothing due in the next 3 weeks.</p>
            )}
            {deadlines?.slice(0, 8).map((d) => (
              <Link
                key={d.task_id}
                to="/projects/$projectId/tasks"
                params={{ projectId: d.project_id }}
                className="flex items-center justify-between gap-2 rounded-md border p-2.5 transition-colors hover:bg-accent"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{d.task_name}</div>
                  <div className="text-xs text-muted-foreground">
                    {d.project_code} · {d.assignee_name ?? "Unassigned"}
                  </div>
                </div>
                <div
                  className={cn(
                    "shrink-0 text-xs font-semibold",
                    d.is_overdue ? "text-destructive" : "text-muted-foreground",
                  )}
                >
                  {d.is_overdue ? `${-d.days_left}d late` : `${d.days_left}d`}
                </div>
              </Link>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
