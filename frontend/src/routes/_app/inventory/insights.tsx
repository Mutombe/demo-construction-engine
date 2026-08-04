import { createFileRoute } from "@tanstack/react-router";
import { DownloadSimple, Warning } from "@phosphor-icons/react";
import { PageHeader } from "@/components/layout/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EntityLink } from "@/components/ui/linked-row";
import { CardListSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { InventoryTabs } from "@/features/inventory/InventoryTabs";
import { downloadFile } from "@/lib/api/download";
import {
  getGetStockItemQueryOptions,
  useGetDemandForecast,
  useGetInventoryAnalytics,
} from "@/lib/api/generated/endpoints";
import { fmtDate, money, moneyExact } from "@/lib/format";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/inventory/insights")({
  component: InventoryInsightsPage,
});

function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "warn" | "bad";
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
        <div
          className={cn(
            "mt-1 text-lg font-semibold tabular-nums",
            tone === "warn" && "text-warning",
            tone === "bad" && "text-destructive",
          )}
        >
          {value}
        </div>
        {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
      </CardContent>
    </Card>
  );
}

function InventoryInsightsPage() {
  const { data: analytics } = useGetInventoryAnalytics({ days: 90 });
  const { data: forecast } = useGetDemandForecast({ days: 90 });

  const byItem = new Map((forecast?.rows ?? []).map((r) => [r.stock_item_id, r]));
  const needsOrdering = (forecast?.rows ?? []).filter((r) => r.needs_ordering);

  return (
    <div>
      <PageHeader
        title="Inventory"
        description="What your stock is costing you, and what runs out next"
        actions={
          <Button
            variant="outline"
            onClick={() =>
              void downloadFile(
                "/api/v1/reports/inventory-analytics?days=90&format=xlsx",
                "inventory_analytics.xlsx",
              ).catch(() => toast.error("Export failed"))
            }
          >
            <DownloadSimple /> Export
          </Button>
        }
      />
      <InventoryTabs />

      {!analytics ? (
        <CardListSkeleton count={4} />
      ) : (
        <>
          <div className="mb-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat
              label="Stock value"
              value={money(analytics.total_stock_value)}
              hint="at weighted-average cost"
            />
            <Stat
              label="Carrying cost"
              value={money(analytics.annual_carrying_cost)}
              hint={`per year at ${Number(analytics.carrying_rate) * 100}%`}
              tone="warn"
            />
            <Stat
              label="Dead stock"
              value={money(analytics.dead_stock_value)}
              hint={`${analytics.dead_stock_count} item${analytics.dead_stock_count === 1 ? "" : "s"} not issued in 90 days`}
              tone={analytics.dead_stock_count > 0 ? "bad" : undefined}
            />
            <Stat
              label="Needs ordering"
              value={String(needsOrdering.length)}
              hint={
                forecast
                  ? `${forecast.lead_time_days}-day lead time from your deliveries`
                  : undefined
              }
              tone={needsOrdering.length > 0 ? "warn" : undefined}
            />
          </div>

          {needsOrdering.length > 0 && (
            <Card className="mb-5 border-warning/40">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Warning className="size-4 text-warning" />
                  Running out
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Item</TableHead>
                      <TableHead className="text-right">On Hand</TableHead>
                      <TableHead className="text-right">Used / Day</TableHead>
                      <TableHead className="text-right">Cover</TableHead>
                      <TableHead>Runs Out</TableHead>
                      <TableHead className="text-right">Suggested Order</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {needsOrdering.map((row) => (
                      <TableRow key={row.stock_item_id}>
                        <TableCell>
                          <EntityLink
                            to="/inventory/$itemId"
                            params={{ itemId: row.stock_item_id }}
                            prefetch={() => getGetStockItemQueryOptions(row.stock_item_id)}
                          >
                            {row.name}
                          </EntityLink>
                          <div className="font-mono text-xs text-muted-foreground">
                            {row.code}
                          </div>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {Number(row.qty_on_hand).toLocaleString()} {row.unit}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">
                          {row.daily_usage ? Number(row.daily_usage).toLocaleString() : "—"}
                        </TableCell>
                        <TableCell
                          className={cn(
                            "text-right tabular-nums",
                            (row.days_of_cover ?? 99) <= (row.lead_time_days ?? 14) &&
                              "font-semibold text-destructive",
                          )}
                        >
                          {row.days_of_cover !== null && row.days_of_cover !== undefined
                            ? `${row.days_of_cover}d`
                            : "—"}
                        </TableCell>
                        <TableCell className="text-sm">
                          {row.projected_stockout ? fmtDate(row.projected_stockout) : "—"}
                        </TableCell>
                        <TableCell className="text-right font-medium tabular-nums">
                          {row.suggested_order_quantity
                            ? `${Number(row.suggested_order_quantity).toLocaleString()} ${row.unit}`
                            : "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <p className="px-4 py-2 text-xs text-muted-foreground">
                  Cover assumes usage continues at the last 90 days' rate. Suggested order
                  covers the delivery lead time plus a buffer.
                </p>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Turnover and Ageing</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Item</TableHead>
                    <TableHead className="text-right">Stock Value</TableHead>
                    <TableHead className="text-right">Issued (90d)</TableHead>
                    <TableHead className="text-right">Turnover</TableHead>
                    <TableHead className="text-right">Days on Hand</TableHead>
                    <TableHead className="text-right">Carrying / Yr</TableHead>
                    <TableHead>Last Issued</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {analytics.rows.map((row) => {
                    const usage = byItem.get(row.stock_item_id);
                    return (
                      <TableRow key={row.stock_item_id}>
                        <TableCell>
                          <EntityLink
                            to="/inventory/$itemId"
                            params={{ itemId: row.stock_item_id }}
                            prefetch={() => getGetStockItemQueryOptions(row.stock_item_id)}
                          >
                            {row.name}
                          </EntityLink>
                          <div className="font-mono text-xs text-muted-foreground">
                            {row.code}
                            {row.is_dead_stock && (
                              <Badge variant="destructive" className="ml-1.5 px-1.5 text-[10px]">
                                dead
                              </Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {moneyExact(row.stock_value)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">
                          {moneyExact(row.issued_value)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {row.turnover_ratio !== null && row.turnover_ratio !== undefined ? (
                            `${Number(row.turnover_ratio).toFixed(1)}x`
                          ) : (
                            <span
                              className="text-muted-foreground"
                              title="Nothing was issued in this window, so there is no turnover to measure"
                            >
                              —
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">
                          {row.days_on_hand ?? "—"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">
                          {moneyExact(row.annual_carrying_cost)}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {row.last_issue ? (
                            <>
                              {fmtDate(row.last_issue)}
                              {row.days_since_issue !== null &&
                                row.days_since_issue !== undefined && (
                                  <span
                                    className={cn(
                                      "ml-1.5 text-xs",
                                      row.is_dead_stock && "text-destructive",
                                    )}
                                  >
                                    ({row.days_since_issue}d)
                                  </span>
                                )}
                            </>
                          ) : (
                            "never"
                          )}
                          {usage?.has_enough_history === false && (
                            <span className="ml-1.5 text-xs">· too little history</span>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
