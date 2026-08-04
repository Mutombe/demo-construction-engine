import { TrendDown, TrendUp } from "@phosphor-icons/react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CardListSkeleton } from "@/components/ui/skeleton";
import { useCashflowForecast } from "@/lib/api/generated/endpoints";
import { money } from "@/lib/format";
import { cn } from "@/lib/utils";

function monthLabel(key: string): string {
  const [year = 0, month = 1] = key.split("-").map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString(undefined, {
    month: "short",
    year: "2-digit",
  });
}

/** Forward cash view: receipts due and work still to certify against orders
 *  already placed and the payroll run-rate. */
export function CashflowCard({ projectId }: { projectId?: string }) {
  const { data, isLoading } = useCashflowForecast({
    months: 6,
    ...(projectId ? { project_id: projectId } : {}),
  });

  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Cash-Flow Forecast</CardTitle>
        </CardHeader>
        <CardContent>
          <CardListSkeleton count={3} />
        </CardContent>
      </Card>
    );
  }

  const rows = data.months.map((m) => ({
    name: monthLabel(m.month),
    inflow: Number(m.inflow_receivable) + Number(m.inflow_forecast),
    outflow: -(Number(m.outflow_committed) + Number(m.outflow_payroll)),
    cumulative: Number(m.cumulative),
    receivable: Number(m.inflow_receivable),
    forecast: Number(m.inflow_forecast),
    committed: Number(m.outflow_committed),
    payroll: Number(m.outflow_payroll),
  }));
  const closing = Number(data.closing_position);
  const worst = data.months.find((m) => m.month === data.worst_month);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>Cash Flow, Next 6 Months</CardTitle>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-success" /> In
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-destructive" /> Out
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 bg-primary" /> Cumulative
          </span>
        </div>
      </CardHeader>
      <CardContent>
        <div className="mb-3 grid gap-3 sm:grid-cols-3">
          <div className="rounded-md border p-3">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              Owed to us today
            </div>
            <div className="text-lg font-semibold tabular-nums">
              {money(data.opening_receivables)}
            </div>
            <div className="text-xs text-muted-foreground">certified, not yet paid</div>
          </div>
          <div className="rounded-md border p-3">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              Closing position
            </div>
            <div
              className={cn(
                "flex items-center gap-1.5 text-lg font-semibold tabular-nums",
                closing < 0 ? "text-destructive" : "text-success",
              )}
            >
              {closing < 0 ? <TrendDown className="size-4" /> : <TrendUp className="size-4" />}
              {money(closing)}
            </div>
            <div className="text-xs text-muted-foreground">
              {money(data.total_inflow)} in · {money(data.total_outflow)} out
            </div>
          </div>
          <div className="rounded-md border p-3">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              Tightest month
            </div>
            <div
              className={cn(
                "text-lg font-semibold tabular-nums",
                worst && Number(worst.net) < 0 && "text-warning",
              )}
            >
              {data.worst_month ? monthLabel(data.worst_month) : "—"}
            </div>
            <div className="text-xs text-muted-foreground">
              {worst ? `${money(worst.net)} net` : "nothing scheduled"}
            </div>
          </div>
        </div>

        <ResponsiveContainer width="100%" height={220}>
          <ComposedChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke="var(--muted-foreground)" />
            <YAxis
              tick={{ fontSize: 11 }}
              stroke="var(--muted-foreground)"
              tickFormatter={(v: number) => money(Math.abs(v))}
            />
            <Tooltip
              contentStyle={{
                background: "var(--card)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                fontSize: 12,
              }}
              formatter={(value, name) => [money(Math.abs(Number(value))), String(name)]}
            />
            <Bar dataKey="inflow" name="Money in" fill="var(--success)" radius={[3, 3, 0, 0]} />
            <Bar
              dataKey="outflow"
              name="Money out"
              fill="var(--destructive)"
              radius={[0, 0, 3, 3]}
            />
            <Line
              type="monotone"
              dataKey="cumulative"
              name="Cumulative"
              stroke="var(--primary)"
              strokeWidth={2}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
        <p className="mt-2 text-xs text-muted-foreground">
          Built from certificates issued, contract value still to certify, purchase orders
          already issued, and the payroll run-rate of the last three months.
        </p>
      </CardContent>
    </Card>
  );
}
