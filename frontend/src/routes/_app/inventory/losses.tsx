import { createFileRoute, Link } from "@tanstack/react-router";
import { TrashSimple, Warning } from "@phosphor-icons/react";
import { PageHeader } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorState } from "@/components/ui/list-state";
import { TableSkeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/ui/stat-card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { InventoryTabs } from "@/features/inventory/InventoryTabs";
import { useGetLossReport } from "@/lib/api/generated/endpoints";
import { money, moneyExact } from "@/lib/format";

export const Route = createFileRoute("/_app/inventory/losses")({
  validateSearch: (search: Record<string, unknown>): { start?: string; end?: string } => ({
    start: typeof search.start === "string" ? search.start : undefined,
    end: typeof search.end === "string" ? search.end : undefined,
  }),
  component: Losses,
});

const REASON_LABELS: Record<string, string> = {
  correction: "Count correction",
  wastage: "Wastage",
  breakage: "Breakage",
  theft: "Theft",
  expiry: "Out of date",
  site_loss: "Lost on site",
};

/** Corrections are shown but never counted. The stock was not there to begin
 *  with, so nothing was lost by it. */
const NOT_A_LOSS = "correction";

function monthsAgo(count: number) {
  const now = new Date();
  now.setMonth(now.getMonth() - count);
  return now.toISOString().slice(0, 10);
}

function Losses() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  const start = search.start ?? monthsAgo(3);
  const end = search.end ?? new Date().toISOString().slice(0, 10);

  const query = useGetLossReport({ start, end });
  const { data, isLoading } = query;

  const byReason = (data?.by_reason ?? []).filter((row) => row.reason !== NOT_A_LOSS);
  const worst = byReason[0];

  return (
    <div>
      <PageHeader
        title="Stock Losses"
        description="What left the store without reaching a job, and why"
      />
      <InventoryTabs />

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="from">From</Label>
          <Input
            id="from"
            type="date"
            value={start}
            className="w-40"
            onChange={(e) =>
              void navigate({ search: (old) => ({ ...old, start: e.target.value }) })
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="to">To</Label>
          <Input
            id="to"
            type="date"
            value={end}
            className="w-40"
            onChange={(e) =>
              void navigate({ search: (old) => ({ ...old, end: e.target.value }) })
            }
          />
        </div>
      </div>

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <StatCard
          label="Lost"
          value={money(data?.total_value ?? 0)}
          icon={<TrashSimple />}
          tone={Number(data?.total_value ?? 0) > 0 ? "negative" : "default"}
          sub="wastage, breakage, theft, expiry"
        />
        <StatCard
          label="Biggest Cause"
          value={worst ? REASON_LABELS[worst.reason] ?? worst.reason : "—"}
          sub={worst ? money(worst.value) : "nothing recorded"}
        />
        <StatCard
          label="Count Corrections"
          value={money(data?.correction_value ?? 0)}
          sub="not a loss — the book was wrong"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">By cause</CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Each of these needs a different answer. Wastage is a rate to manage, breakage is
              handling, theft is security — averaging them together produces a number nobody
              can act on.
            </p>
          </CardHeader>
          <CardContent className="p-0">
            {query.isError ? (
              <ErrorState error={query.error} onRetry={() => void query.refetch()} />
            ) : isLoading && !data ? (
              <TableSkeleton columns={4} />
            ) : (data?.by_reason ?? []).length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Cause</TableHead>
                    <TableHead className="num">Movements</TableHead>
                    <TableHead className="num">Quantity</TableHead>
                    <TableHead className="num">Value</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(data?.by_reason ?? []).map((row) => (
                    <TableRow key={row.reason}>
                      <TableCell>
                        {REASON_LABELS[row.reason] ?? row.reason}
                        {row.reason === NOT_A_LOSS && (
                          <span className="ml-1.5 text-xs text-muted-foreground">
                            not counted
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="num text-muted-foreground">
                        {row.movements}
                      </TableCell>
                      <TableCell className="num text-muted-foreground">
                        {Number(row.quantity).toLocaleString()}
                      </TableCell>
                      <TableCell
                        className={
                          row.reason === NOT_A_LOSS ? "num text-muted-foreground" : "num"
                        }
                      >
                        {moneyExact(row.value)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <EmptyState
                icon={<Warning />}
                title="Nothing written off"
                hint="No stock has left the store except by being issued to a job."
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Worst items</CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              By value, so a cheap material lost by the tonne does not hide an expensive one
              lost by the handful.
            </p>
          </CardHeader>
          <CardContent className="p-0">
            {query.isError ? (
              <ErrorState error={query.error} onRetry={() => void query.refetch()} />
            ) : isLoading && !data ? (
              <TableSkeleton columns={4} />
            ) : (data?.by_item ?? []).length ? (
              <Table maxHeight="55vh">
                <TableHeader>
                  <TableRow>
                    <TableHead>Item</TableHead>
                    <TableHead>Causes</TableHead>
                    <TableHead className="num">Quantity</TableHead>
                    <TableHead className="num">Value</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(data?.by_item ?? []).map((row) => (
                    <TableRow key={row.stock_item_id}>
                      <TableCell>
                        <Link
                          to="/inventory/$itemId"
                          params={{ itemId: row.stock_item_id }}
                          className="font-medium hover:underline"
                        >
                          {row.code}
                        </Link>
                        <div className="text-xs text-muted-foreground">{row.name}</div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {(row.reasons ?? [])
                          .map((r) => REASON_LABELS[r] ?? r)
                          .join(", ")}
                      </TableCell>
                      <TableCell className="num text-muted-foreground">
                        {Number(row.quantity).toLocaleString()} {row.unit}
                      </TableCell>
                      <TableCell className="num font-medium">{moneyExact(row.value)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <EmptyState icon={<TrashSimple />} title="Nothing lost" />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
