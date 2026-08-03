import { Link, createFileRoute } from "@tanstack/react-router";
import { Bank, Buildings, CalendarDots, Wallet, Warning } from "@phosphor-icons/react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { PageHeader } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { CardListSkeleton, PageSkeleton } from "@/components/ui/skeleton";
import { ProjectStatusBadge } from "@/features/projects/StatusBadge";
import {
  useBudgetAlerts,
  useDeadlines,
  useFinancialTrend,
  useOverview,
} from "@/lib/api/generated/endpoints";
import { fmtDate, money, pct } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/")({ component: DashboardPage });

function KpiCard({
  label,
  value,
  icon,
  tone,
  sub,
}: {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  tone?: "danger" | "default";
  sub?: string;
}) {
  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardContent className="flex items-center gap-3 p-4">
        <div
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg [&_svg]:size-5",
            tone === "danger" ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary",
          )}
        >
          {icon}
        </div>
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
          <div className="truncate text-xl font-semibold tabular-nums">{value}</div>
          {sub && <div className="truncate text-[11px] text-muted-foreground">{sub}</div>}
        </div>
      </CardContent>
    </Card>
  );
}

function monthLabel(key: string): string {
  const [year, month] = key.split("-");
  return new Date(Number(year), Number(month) - 1, 1).toLocaleString("en-US", {
    month: "short",
  });
}

function DashboardPage() {
  const { data: overview, isLoading } = useOverview();
  const { data: deadlines, isLoading: deadlinesLoading } = useDeadlines({ days: 21 });
  const { data: alerts, isLoading: alertsLoading } = useBudgetAlerts({ threshold_pct: 90 });
  const { data: trend } = useFinancialTrend({ months: 6 });

  if (isLoading || !overview) {
    return <PageSkeleton rows={6} />;
  }

  const trendData = (trend?.months ?? []).map((m) => ({
    name: monthLabel(m.month),
    cost: Number(m.cost),
    certified: Number(m.certified_net),
    paid: Number(m.paid),
  }));

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

      <div className="mb-5 grid grid-cols-2 gap-4 xl:grid-cols-5">
        <KpiCard label="Active projects" value={overview.active_projects} icon={<Buildings />} />
        <KpiCard
          label="Contract value"
          value={money(overview.portfolio_contract_value)}
          icon={<Wallet />}
        />
        <KpiCard
          label="Spend vs budget"
          value={`${money(overview.portfolio_actual)} / ${money(overview.portfolio_budget)}`}
          icon={<CalendarDots />}
        />
        <KpiCard
          label="Cash position"
          value={money(trend?.totals.portfolio_outstanding)}
          icon={<Bank />}
          sub={`${money(trend?.totals.portfolio_paid)} received of ${money(trend?.totals.portfolio_invoiced)} invoiced`}
        />
        <KpiCard
          label="Overdue tasks"
          value={overview.overdue_tasks}
          icon={<Warning />}
          tone={overview.overdue_tasks > 0 ? "danger" : "default"}
        />
      </div>

      <Card className="mb-4">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle>Revenue vs Cost — Last 6 Months</CardTitle>
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm bg-muted-foreground/40" /> Cost
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-0.5 w-3 rounded bg-primary" /> Certified
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-0.5 w-3 rounded bg-success" /> Paid
            </span>
          </div>
        </CardHeader>
        <CardContent>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
                <XAxis dataKey="name" tickLine={false} axisLine={false} fontSize={12} />
                <YAxis
                  tickFormatter={(v: number) => `${Math.round(v / 1000)}k`}
                  tickLine={false}
                  axisLine={false}
                  fontSize={12}
                  width={44}
                />
                <Tooltip
                  formatter={(value, name) => [money(Number(value)), String(name)]}
                  contentStyle={{
                    borderRadius: 8,
                    border: "1px solid var(--border)",
                    background: "var(--card)",
                    fontSize: 12,
                  }}
                />
                <Bar
                  dataKey="cost"
                  name="Cost"
                  fill="var(--muted-foreground)"
                  opacity={0.35}
                  radius={[3, 3, 0, 0]}
                  maxBarSize={42}
                />
                <Line
                  type="monotone"
                  dataKey="certified"
                  name="Certified"
                  stroke="var(--primary)"
                  strokeWidth={2.5}
                  dot={{ r: 3 }}
                />
                <Line
                  type="monotone"
                  dataKey="paid"
                  name="Paid"
                  stroke="var(--success)"
                  strokeWidth={2.5}
                  dot={{ r: 3 }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle>Budget vs Actual by Project</CardTitle>
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
            <CardTitle>Budget Alerts</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2.5">
            {alertsLoading && !alerts && <CardListSkeleton count={3} />}
            {!alertsLoading && !alerts?.length && (
              <p className="text-sm text-muted-foreground">No lines above 90% of budget.</p>
            )}
            {alerts?.slice(0, 6).map((a) => (
              <Link
                key={`${a.project_id}-${a.scope}-${a.item_code ?? "project"}`}
                to={a.item_code ? "/projects/$projectId/boq" : "/projects/$projectId"}
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
            <CardTitle>Upcoming Deadlines (21 Days)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {deadlinesLoading && !deadlines && <CardListSkeleton count={3} />}
            {!deadlinesLoading && !deadlines?.length && (
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
