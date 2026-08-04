import { keepPreviousData } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { ArrowsLeftRight } from "@phosphor-icons/react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Can } from "@/components/layout/Can";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { EntityLink } from "@/components/ui/linked-row";
import { DEFAULT_PAGE_SIZE, PaginationBar } from "@/components/ui/pagination";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PageSkeleton, TableSkeleton } from "@/components/ui/skeleton";
import { TransferDialog } from "@/features/inventory/TransferDialog";
import { makeBadge } from "@/features/procurement/StatusBadges";
import {
  getGetStockItemQueryOptions,
  useGetStockItem,
  useGetStockItemLevels,
  useListStockBatches,
  useListStockMovements,
} from "@/lib/api/generated/endpoints";
import type { StockItemRead } from "@/lib/api/generated/model";
import { fmtDate, moneyExact } from "@/lib/format";

export const Route = createFileRoute("/_app/inventory/$itemId")({
  component: StockItemDetailPage,
  loader: ({ context: { queryClient }, params }) =>
    queryClient.ensureQueryData(getGetStockItemQueryOptions(params.itemId)),
});

const MovementTypeBadge = makeBadge({
  goods_in: ["success", "Goods In"],
  issue: ["default", "Issue"],
  adjustment: ["secondary", "Adjustment"],
  transfer: ["outline", "Transfer"],
});

function StockItemDetailPage() {
  const { itemId } = Route.useParams();
  const { data: item } = useGetStockItem(itemId);
  const { data: levels } = useGetStockItemLevels(itemId);
  const { data: batches } = useListStockBatches({ item_id: itemId });
  const [transferring, setTransferring] = useState<StockItemRead | null>(null);
  const [movementsPage, setMovementsPage] = useState(1);
  const { data: movements, isLoading: movementsLoading } = useListStockMovements(
    itemId,
    { page: movementsPage, page_size: DEFAULT_PAGE_SIZE },
    { query: { placeholderData: keepPreviousData } },
  );

  if (!item) {
    return <PageSkeleton rows={4} />;
  }

  return (
    <div>
      <Breadcrumbs
        items={[{ label: "Inventory", to: "/inventory" }, { label: item.name }]}
      />
      <div className="mb-5">
        <div className="flex items-center gap-2.5">
          <h1 className="text-xl font-semibold tracking-tight">{item.name}</h1>
          <span className="font-mono text-sm text-muted-foreground">{item.code}</span>
          {item.low_stock && <Badge variant="warning">Low stock</Badge>}
          {!item.is_active && <Badge variant="outline">Inactive</Badge>}
        </div>
        {item.barcode && (
          <div className="mt-1 font-mono text-xs text-muted-foreground">
            Barcode {item.barcode}
          </div>
        )}
      </div>

      <div className="mb-5 grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Card>
          <CardContent className="p-4">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">On hand</div>
            <div className="text-xl font-semibold">
              {Number(item.qty_on_hand).toLocaleString()} {item.unit}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              Avg unit cost
            </div>
            <div className="text-xl font-semibold">{moneyExact(item.unit_cost)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              Stock value
            </div>
            <div className="text-xl font-semibold">
              {moneyExact(Number(item.qty_on_hand) * Number(item.unit_cost))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              Reorder level
            </div>
            <div className="text-xl font-semibold">
              {Number(item.reorder_level).toLocaleString()} {item.unit}
            </div>
          </CardContent>
        </Card>
      </div>

      {levels && levels.length > 0 && (
        <Card className="mb-5">
          <CardContent className="p-4">
            <div className="mb-2 flex items-center justify-between">
              <div className="text-xs uppercase tracking-wide text-muted-foreground">
                Where this stock is
              </div>
              <Can perm="inventory:issue">
                <Button variant="outline" size="sm" onClick={() => setTransferring(item)}>
                  <ArrowsLeftRight /> Transfer
                </Button>
              </Can>
            </div>
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
              {levels.map((level) => (
                <div
                  key={level.location_id}
                  className="flex items-baseline justify-between rounded-md border px-3 py-2"
                >
                  <span className="text-sm">{level.location_name}</span>
                  <span className="text-sm font-semibold tabular-nums">
                    {Number(level.quantity).toLocaleString()} {item.unit}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {batches && batches.length > 0 && (
        <Card className="mb-5">
          <CardContent className="p-4">
            <div className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
              {item.tracking_mode === "serial" ? "Serial numbers" : "Batches"} in stock
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{item.tracking_mode === "serial" ? "Serial" : "Lot"}</TableHead>
                  <TableHead>Location</TableHead>
                  <TableHead>Received</TableHead>
                  <TableHead>Expiry</TableHead>
                  <TableHead className="text-right">Quantity</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {batches.map((batch) => (
                  <TableRow key={batch.id}>
                    <TableCell className="font-mono text-xs">
                      {batch.batch_number}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {batch.location_name}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {fmtDate(batch.received_date)}
                    </TableCell>
                    <TableCell className="text-sm">
                      {batch.expiry_date ? (
                        <span
                          className={
                            batch.is_expired
                              ? "font-medium text-destructive"
                              : batch.is_expiring_soon
                                ? "font-medium text-warning"
                                : "text-muted-foreground"
                          }
                        >
                          {fmtDate(batch.expiry_date)}
                          {batch.is_expired
                            ? " · expired"
                            : batch.is_expiring_soon
                              ? ` · ${batch.days_to_expiry}d left`
                              : ""}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {Number(batch.quantity).toLocaleString()} {item.unit}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="mt-2 text-xs text-muted-foreground">
              Issues consume the earliest expiry first.
            </p>
          </CardContent>
        </Card>
      )}

      <TransferDialog item={transferring} onClose={() => setTransferring(null)} />

      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Movement</TableHead>
              <TableHead>Location</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Date</TableHead>
              <TableHead className="text-right">Qty</TableHead>
              <TableHead className="text-right">Unit Cost</TableHead>
              <TableHead>Project</TableHead>
              <TableHead>Reference / Notes</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {movementsLoading && !movements && <TableSkeleton columns={8} rows={5} />}
            {!movementsLoading && !movements?.items.length && (
              <TableRow>
                <TableCell colSpan={8} className="py-10 text-center text-muted-foreground">
                  No movements yet.
                </TableCell>
              </TableRow>
            )}
            {movements?.items.map((m) => (
              <TableRow key={m.id}>
                <TableCell className="font-mono text-xs">{m.doc_number}</TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {m.location_name ?? "—"}
                </TableCell>
                <TableCell>
                  <MovementTypeBadge status={m.movement_type} />
                </TableCell>
                <TableCell className="text-sm">{fmtDate(m.movement_date)}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {Number(m.quantity) > 0 ? "+" : ""}
                  {Number(m.quantity).toLocaleString()}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {moneyExact(m.unit_cost)}
                </TableCell>
                <TableCell className="text-sm">
                  {m.project_id ? (
                    <EntityLink
                      to="/projects/$projectId"
                      params={{ projectId: m.project_id }}
                      className="text-sm font-normal"
                    >
                      {m.project_name ?? "Project"}
                    </EntityLink>
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell className="max-w-52 truncate text-sm text-muted-foreground">
                  {[m.reference, m.notes].filter(Boolean).join(" · ") || "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <PaginationBar
          page={movementsPage}
          pageSize={DEFAULT_PAGE_SIZE}
          total={movements?.total}
          onPageChange={setMovementsPage}
        />
      </div>
    </div>
  );
}
