import { keepPreviousData } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
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
import { makeBadge } from "@/features/procurement/StatusBadges";
import {
  getGetStockItemQueryOptions,
  useGetStockItem,
  useListStockMovements,
} from "@/lib/api/generated/endpoints";
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
});

function StockItemDetailPage() {
  const { itemId } = Route.useParams();
  const { data: item } = useGetStockItem(itemId);
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

      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Movement</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Date</TableHead>
              <TableHead className="text-right">Qty</TableHead>
              <TableHead className="text-right">Unit Cost</TableHead>
              <TableHead>Project</TableHead>
              <TableHead>Reference / Notes</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {movementsLoading && !movements && <TableSkeleton columns={7} rows={5} />}
            {!movementsLoading && !movements?.items.length && (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                  No movements yet.
                </TableCell>
              </TableRow>
            )}
            {movements?.items.map((m) => (
              <TableRow key={m.id}>
                <TableCell className="font-mono text-xs">{m.doc_number}</TableCell>
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
