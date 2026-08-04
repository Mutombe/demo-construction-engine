import { keepPreviousData } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { ArrowLineDown, ArrowLineUp, Barcode, DownloadSimple, MagnifyingGlass, PencilSimple, Plus, ShoppingCart, Wrench } from "@phosphor-icons/react";
import { useState } from "react";
import { toast } from "@/lib/toast";
import { z } from "zod";
import { PageHeader } from "@/components/layout/AppShell";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { ClickableRow, RowActions } from "@/components/ui/linked-row";
import { DEFAULT_PAGE_SIZE, PaginationBar } from "@/components/ui/pagination";
import { TableSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { usePermission } from "@/features/auth/hooks";
import { BarcodeScannerDialog } from "@/features/inventory/BarcodeScannerDialog";
import { InventoryTabs } from "@/features/inventory/InventoryTabs";
import { ReorderDialog } from "@/features/inventory/ReorderDialog";
import { MovementDialog, type MovementKind } from "@/features/inventory/MovementDialogs";
import { StockItemFormDialog } from "@/features/inventory/StockItemFormDialog";
import { downloadFile } from "@/lib/api/download";
import {
  getGetStockItemQueryOptions,
  getStockItemByBarcode,
  useListStockItems,
  useListStockLocations,
} from "@/lib/api/generated/endpoints";
import type { StockItemRead } from "@/lib/api/generated/model";
import { moneyExact } from "@/lib/format";

const searchSchema = z.object({
  page: z.number().int().min(1).optional().default(1),
});

export const Route = createFileRoute("/_app/inventory/")({
  validateSearch: searchSchema,
  component: InventoryPage,
});

function InventoryPage() {
  const { page } = Route.useSearch();
  const navigate = Route.useNavigate();
  const [search, setSearch] = useState("");
  const [lowOnly, setLowOnly] = useState(false);
  const [itemDialog, setItemDialog] = useState(false);
  const [editing, setEditing] = useState<StockItemRead | null>(null);
  const [movement, setMovement] = useState<{ kind: MovementKind; item: StockItemRead } | null>(
    null,
  );
  const canWrite = usePermission("inventory:write");
  const canIssue = usePermission("inventory:issue");
  const [scanOpen, setScanOpen] = useState(false);
  const [reorderOpen, setReorderOpen] = useState(false);
  const [locationId, setLocationId] = useState("");
  const { data: locations } = useListStockLocations({ active_only: true });

  const onScanned = async (code: string) => {
    try {
      const item = await getStockItemByBarcode(code);
      setScanOpen(false);
      void navigate({ to: "/inventory/$itemId", params: { itemId: item.id } });
    } catch {
      toast.error(`No stock item carries barcode ${code}`);
    }
  };

  const { data, isLoading } = useListStockItems(
    {
      search: search || undefined,
      low_stock_only: lowOnly || undefined,
      location_id: locationId || undefined,
      page,
      page_size: DEFAULT_PAGE_SIZE,
    },
    { query: { placeholderData: keepPreviousData } },
  );

  const totalValue = data?.items.reduce(
    (sum, item) => sum + Number(item.qty_on_hand) * Number(item.unit_cost),
    0,
  );

  return (
    <div>
      <PageHeader
        title="Inventory"
        description={
          data
            ? // Stock value is computed from the visible rows, so only show it while
              // everything fits on one page — otherwise it would be page-scoped.
              data.total <= DEFAULT_PAGE_SIZE
              ? `${data.total} item${data.total === 1 ? "" : "s"} · stock value ${moneyExact(totalValue ?? 0)}`
              : `${data.total} items`
            : undefined
        }
        actions={
          <>
            <Button
              variant="outline"
              onClick={() =>
                void downloadFile(
                  `/api/v1/reports/stock-valuation?format=xlsx${lowOnly ? "&low_stock_only=true" : ""}`,
                  "stock_valuation.xlsx",
                ).catch(() => toast.error("Export failed"))
              }
            >
              <DownloadSimple /> Export
            </Button>
            <Can perm="inventory:write">
              <Button variant="outline" onClick={() => setReorderOpen(true)}>
                <ShoppingCart /> Reorder
              </Button>
              <Button
                onClick={() => {
                  setEditing(null);
                  setItemDialog(true);
                }}
              >
                <Plus /> New Item
              </Button>
            </Can>
          </>
        }
      />

      <InventoryTabs />

      <div className="mb-4 flex items-center gap-3">
        <div className="relative w-72">
          <MagnifyingGlass className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search code, name or category…"
            className="pl-8"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              void navigate({ search: { page: 1 }, replace: true });
            }}
          />
        </div>
        <Button variant="outline" onClick={() => setScanOpen(true)}>
          <Barcode /> Scan
        </Button>
        <Select
          className="w-52"
          value={locationId}
          onChange={(e) => {
            setLocationId(e.target.value);
            void navigate({ search: { page: 1 }, replace: true });
          }}
        >
          <option value="">All locations</option>
          {locations?.map((loc) => (
            <option key={loc.id} value={loc.id}>
              {loc.name}
            </option>
          ))}
        </Select>
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={lowOnly}
            onChange={(e) => {
              setLowOnly(e.target.checked);
              void navigate({ search: { page: 1 }, replace: true });
            }}
          />
          Low stock only
        </label>
      </div>

      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Item</TableHead>
              <TableHead>Category</TableHead>
              <TableHead className="text-right">On Hand</TableHead>
              <TableHead className="text-right">Avg Cost</TableHead>
              <TableHead className="text-right">Value</TableHead>
              <TableHead className="w-56" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && !data && <TableSkeleton columns={6} />}
            {!isLoading && !data?.items.length && (
              <TableRow>
                <TableCell colSpan={6} className="py-10 text-center text-muted-foreground">
                  No stock items yet.
                </TableCell>
              </TableRow>
            )}
            {data?.items.map((item, rowIndex) => (
              <ClickableRow
                index={rowIndex}
                key={item.id}
                to="/inventory/$itemId"
                params={{ itemId: item.id }}
                prefetch={() => getGetStockItemQueryOptions(item.id)}
              >
                <TableCell>
                  <span className="font-medium">{item.name}</span>
                  <div className="font-mono text-xs text-muted-foreground">{item.code}</div>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {item.category ?? "—"}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {Number(item.qty_on_hand).toLocaleString()} {item.unit}
                  {item.low_stock && (
                    <Badge variant="warning" className="ml-1.5">
                      Low
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {moneyExact(item.unit_cost)}
                </TableCell>
                <TableCell className="text-right font-medium tabular-nums">
                  {moneyExact(Number(item.qty_on_hand) * Number(item.unit_cost))}
                </TableCell>
                <RowActions>
                  <div className="flex justify-end gap-1">
                    {canWrite && (
                      <>
                        <Button
                          variant="outline"
                          size="sm"
                          title="Goods in"
                          onClick={() => setMovement({ kind: "goods-in", item })}
                        >
                          <ArrowLineDown className="h-3.5 w-3.5" /> In
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          title="Adjust"
                          onClick={() => setMovement({ kind: "adjust", item })}
                        >
                          <Wrench className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => {
                            setEditing(item);
                            setItemDialog(true);
                          }}
                        >
                          <PencilSimple className="h-3.5 w-3.5" />
                        </Button>
                      </>
                    )}
                    {canIssue && (
                      <Button
                        size="sm"
                        title="Issue to project"
                        onClick={() => setMovement({ kind: "issue", item })}
                      >
                        <ArrowLineUp className="h-3.5 w-3.5" /> Issue
                      </Button>
                    )}
                  </div>
                </RowActions>
              </ClickableRow>
            ))}
          </TableBody>
        </Table>
        <PaginationBar
          page={page}
          pageSize={DEFAULT_PAGE_SIZE}
          total={data?.total}
          onPageChange={(p) =>
            void navigate({ search: (prev) => ({ ...prev, page: p }), replace: true })
          }
        />
      </div>

      <BarcodeScannerDialog
        open={scanOpen}
        onOpenChange={setScanOpen}
        onDetected={(code) => void onScanned(code)}
        title="Find Item by Barcode"
        hint="Scanning opens the matching stock item."
      />
      <ReorderDialog open={reorderOpen} onOpenChange={setReorderOpen} />
      <StockItemFormDialog open={itemDialog} onOpenChange={setItemDialog} item={editing} />
      <MovementDialog
        kind={movement?.kind ?? null}
        item={movement?.item ?? null}
        onClose={() => setMovement(null)}
      />
    </div>
  );
}
