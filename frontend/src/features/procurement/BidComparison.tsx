import { Link } from "@tanstack/react-router";
import { Trophy, WarningCircle } from "@phosphor-icons/react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/list-state";
import { TableSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip } from "@/components/ui/tooltip";
import { useCompareBids } from "@/lib/api/generated/endpoints";
import { moneyExact } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Every bid on this enquiry with the bidder's record beside the price.
 *
 *  This is the only screen where the supplier history has to appear. Kept
 *  anywhere else it becomes something people look up after the order has gone
 *  out, which is too late to be worth having collected. */
export function BidComparison({ rfqId }: { rfqId: string }) {
  const query = useCompareBids(rfqId);
  const rows = query.data ?? [];

  const cheapest = rows[0];
  // Worth flagging when the cheapest bid is also the one with the worst
  // record, because that is exactly the decision people get wrong.
  const bestRated = rows.reduce<(typeof rows)[number] | null>((best, row) => {
    if (row.overall == null) return best;
    if (!best || Number(row.overall) > Number(best.overall)) return row;
    return best;
  }, null);
  const conflict =
    cheapest && bestRated && cheapest.quote_id !== bestRated.quote_id;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Bids</CardTitle>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Cheapest first, with what each supplier has actually been like to deal with.
        </p>
      </CardHeader>
      <CardContent className="p-0">
        {conflict && (
          <div className="mx-4 mb-3 flex items-start gap-2 rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-sm">
            <WarningCircle weight="fill" className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
            <span className="text-muted-foreground">
              The cheapest bid is not the best-rated one.{" "}
              <span className="font-medium text-foreground">{bestRated?.supplier_name}</span>{" "}
              scores {Number(bestRated?.overall).toFixed(1)} against{" "}
              {cheapest.overall != null
                ? Number(cheapest.overall).toFixed(1)
                : "no record yet"}
              , at{" "}
              {bestRated?.above_lowest_pct != null
                ? `${Number(bestRated.above_lowest_pct).toFixed(1)}% more`
                : "a higher price"}
              .
            </span>
          </div>
        )}

        {query.isError ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        ) : query.isLoading ? (
          <TableSkeleton columns={6} />
        ) : rows.length ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Supplier</TableHead>
                <TableHead className="num">Bid</TableHead>
                <TableHead className="num">vs cheapest</TableHead>
                <TableHead className="num">Quality</TableHead>
                <TableHead className="num">Delivery</TableHead>
                <TableHead className="num">Overall</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row, index) => (
                <TableRow key={row.quote_id}>
                  <TableCell>
                    <Link
                      to="/procurement/suppliers/$supplierId"
                      params={{ supplierId: row.supplier_id }}
                      className="font-medium hover:underline"
                    >
                      {row.supplier_name ?? "Supplier"}
                    </Link>
                    <div className="mt-0.5 flex items-center gap-1.5">
                      {index === 0 && (
                        <Badge variant="success" className="gap-1">
                          <Trophy className="h-3 w-3" /> Cheapest
                        </Badge>
                      )}
                      {row.assessments === 0 ? (
                        <Tooltip content="Never assessed, which is not the same as assessed badly.">
                          <span className="text-xs text-muted-foreground">No record</span>
                        </Tooltip>
                      ) : (
                        row.provisional && (
                          <span className="text-xs text-muted-foreground">
                            {row.assessments} judged
                          </span>
                        )
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="num font-medium">
                    {moneyExact(row.total_amount)}
                  </TableCell>
                  <TableCell className="num text-muted-foreground">
                    {row.above_lowest_pct == null || Number(row.above_lowest_pct) === 0
                      ? "—"
                      : `+${Number(row.above_lowest_pct).toFixed(1)}%`}
                  </TableCell>
                  <TableCell className="num">
                    <Cell value={row.quality} />
                  </TableCell>
                  <TableCell className="num">
                    <Cell value={row.delivery} />
                  </TableCell>
                  <TableCell className="num">
                    <Cell value={row.overall} strong />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <EmptyState
            icon={<Trophy />}
            title="No bids yet"
            hint="Prices come back here as suppliers respond to the enquiry."
          />
        )}
      </CardContent>
    </Card>
  );
}

function Cell({
  value,
  strong,
}: {
  value: string | number | null | undefined;
  strong?: boolean;
}) {
  if (value == null) return <span className="text-muted-foreground">—</span>;
  const score = Number(value);
  return (
    <span
      className={cn(
        "tabular-nums",
        strong && "font-medium",
        score >= 4
          ? "text-success"
          : score >= 3
            ? undefined
            : "text-destructive",
      )}
    >
      {score.toFixed(1)}
    </span>
  );
}
