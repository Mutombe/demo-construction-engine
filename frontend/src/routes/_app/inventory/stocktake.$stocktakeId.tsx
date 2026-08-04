import { createFileRoute } from "@tanstack/react-router";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { EntityLink } from "@/components/ui/linked-row";
import { DetailSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  getGetStockItemQueryOptions,
  getGetStocktakeQueryOptions,
  useGetStocktake,
} from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/inventory/stocktake/$stocktakeId")({
  component: StocktakeDetailPage,
  loader: ({ context: { queryClient }, params }) =>
    queryClient.ensureQueryData(getGetStocktakeQueryOptions(params.stocktakeId)),
});

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-0.5 text-sm">{children}</div>
    </div>
  );
}

function StocktakeDetailPage() {
  const { stocktakeId } = Route.useParams();
  const { data: stocktake } = useGetStocktake(stocktakeId);

  if (!stocktake) return <DetailSkeleton />;

  const lines = stocktake.lines ?? [];
  const counted = lines.filter(
    (l) => l.counted_quantity !== null && l.counted_quantity !== undefined,
  );
  const variances = counted.filter((l) => Number(l.variance_quantity) !== 0);

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Inventory", to: "/inventory" },
          { label: "Stocktake", to: "/inventory/stocktake" },
          { label: stocktake.doc_number },
        ]}
      />

      <div className="mb-5 flex items-center gap-2.5">
        <h1 className="text-xl font-semibold tracking-tight">{stocktake.doc_number}</h1>
        <Badge
          variant={
            stocktake.status === "approved"
              ? "success"
              : stocktake.status === "counting"
                ? "warning"
                : "outline"
          }
        >
          {stocktake.status}
        </Badge>
      </div>

      <Card className="mb-4">
        <CardContent className="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-4">
          <Meta label="Count date">{fmtDate(stocktake.count_date)}</Meta>
          <Meta label="Counted">
            {stocktake.counted_count} of {stocktake.line_count} lines
          </Meta>
          <Meta label="Lines with a variance">
            {/* The number that matters: how much of the shelf disagreed */}
            {variances.length}
          </Meta>
          <Meta label="Net variance">
            <span
              className={cn(
                "font-semibold tabular-nums",
                Number(stocktake.variance_value) < 0 && "text-destructive",
                Number(stocktake.variance_value) > 0 && "text-success",
              )}
            >
              {moneyExact(stocktake.variance_value)}
            </span>
          </Meta>
          {stocktake.approved_at && (
            <Meta label="Approved">{fmtDate(stocktake.approved_at)}</Meta>
          )}
          {stocktake.notes && (
            <div className="sm:col-span-2 xl:col-span-4">
              <Meta label="Notes">{stocktake.notes}</Meta>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Item</TableHead>
                <TableHead className="text-right">Expected</TableHead>
                <TableHead className="text-right">Counted</TableHead>
                <TableHead className="text-right">Variance</TableHead>
                <TableHead className="text-right">Value</TableHead>
                <TableHead>Note</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((line) => {
                const wasCounted =
                  line.counted_quantity !== null && line.counted_quantity !== undefined;
                const variance = Number(line.variance_quantity);
                return (
                  <TableRow key={line.id}>
                    <TableCell>
                      <EntityLink
                        to="/inventory/$itemId"
                        params={{ itemId: line.stock_item_id }}
                        prefetch={() => getGetStockItemQueryOptions(line.stock_item_id)}
                      >
                        {line.name}
                      </EntityLink>
                      <div className="font-mono text-xs text-muted-foreground">
                        {line.code}
                      </div>
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {Number(line.expected_quantity).toLocaleString()} {line.unit}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {wasCounted
                        ? Number(line.counted_quantity).toLocaleString()
                        : "not counted"}
                    </TableCell>
                    <TableCell
                      className={cn(
                        "text-right tabular-nums",
                        variance < 0 && "text-destructive",
                        variance > 0 && "text-success",
                      )}
                    >
                      {wasCounted ? variance.toLocaleString() : "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {wasCounted ? moneyExact(line.variance_value) : "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {line.notes ?? ""}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
