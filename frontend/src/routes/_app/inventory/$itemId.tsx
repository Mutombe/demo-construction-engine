import { Link, createFileRoute } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PageSkeleton } from "@/components/ui/skeleton";
import { makeBadge } from "@/features/procurement/StatusBadges";
import {
  useGetStockItem,
  useListStockMovements,
} from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";

export const Route = createFileRoute("/_app/inventory/$itemId")({
  component: StockItemDetailPage,
});

const MovementTypeBadge = makeBadge({
  goods_in: ["success", "Goods in"],
  issue: ["default", "Issue"],
  adjustment: ["secondary", "Adjustment"],
});

function StockItemDetailPage() {
  const { itemId } = Route.useParams();
  const { data: item } = useGetStockItem(itemId);
  const { data: movements } = useListStockMovements(itemId, { page_size: 100 });

  if (!item) {
    return <PageSkeleton rows={4} />;
  }

  return (
    <div>
      <Link
        to="/inventory"
        className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> Inventory
      </Link>
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
              <TableHead className="text-right">Unit cost</TableHead>
              <TableHead>Project</TableHead>
              <TableHead>Reference / notes</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!movements?.items.length && (
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
                <TableCell className="text-sm">{m.project_name ?? "—"}</TableCell>
                <TableCell className="max-w-52 truncate text-sm text-muted-foreground">
                  {[m.reference, m.notes].filter(Boolean).join(" · ") || "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
