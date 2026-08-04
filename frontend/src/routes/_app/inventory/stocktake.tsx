import { keepPreviousData, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { CheckCircle, ClipboardText, Prohibit } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/layout/AppShell";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { confirmDialog } from "@/components/ui/confirm";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { DEFAULT_PAGE_SIZE, PaginationBar } from "@/components/ui/pagination";
import { CardListSkeleton, TableSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { InventoryTabs } from "@/features/inventory/InventoryTabs";
import { errDetail } from "@/lib/api/errors";
import {
  useApproveStocktake,
  useCancelStocktake,
  useCreateStocktake,
  useGetStocktake,
  useListStocktakes,
  useSetStocktakeCounts,
} from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/inventory/stocktake")({
  component: StocktakePage,
});

function StocktakePage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const { data, isLoading } = useListStocktakes(
    { page, page_size: DEFAULT_PAGE_SIZE },
    { query: { placeholderData: keepPreviousData } },
  );
  const createMutation = useCreateStocktake();
  const [category, setCategory] = useState("");

  const open = data?.items.find((s) => s.status === "counting");

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["/api/v1/stocktakes"] });

  const start = async () => {
    try {
      await createMutation.mutateAsync({
        data: { category: category || null, stock_item_ids: [] },
      });
      await refresh();
      toast.success("Count started — expected quantities snapshotted");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <div>
      <PageHeader
        title="Inventory"
        description="Count the shelves, review the variance, then post the corrections in one approval"
        actions={
          !open && (
            <Can perm="inventory:write">
              <div className="flex items-center gap-2">
                <Input
                  className="w-44"
                  placeholder="Category (optional)"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                />
                <Button disabled={createMutation.isPending} onClick={() => void start()}>
                  <ClipboardText /> Start Count
                </Button>
              </div>
            </Can>
          )
        }
      />

      <InventoryTabs />

      {open ? (
        <CountSheet stocktakeId={open.id} onChanged={refresh} />
      ) : (
        <div className="mb-4 rounded-lg border">
          <EmptyState
            icon={<ClipboardText />}
            title="No count in progress"
            hint="Start a count to snapshot today's expected quantities. Counting against a snapshot keeps the variance honest even if stock moves mid-count."
          />
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>History</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Document</TableHead>
                <TableHead>Count Date</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Lines</TableHead>
                <TableHead className="text-right">Counted</TableHead>
                <TableHead className="text-right">Variance</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && !data && <TableSkeleton columns={6} rows={4} />}
              {!isLoading && !data?.items.length && (
                <TableRow>
                  <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                    No stocktakes yet.
                  </TableCell>
                </TableRow>
              )}
              {data?.items.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="font-mono text-xs">{row.doc_number}</TableCell>
                  <TableCell>{fmtDate(row.count_date)}</TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        row.status === "approved"
                          ? "success"
                          : row.status === "counting"
                            ? "warning"
                            : "outline"
                      }
                    >
                      {row.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{row.line_count}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.counted_count}</TableCell>
                  <TableCell
                    className={cn(
                      "text-right tabular-nums",
                      Number(row.variance_value) < 0 && "text-destructive",
                      Number(row.variance_value) > 0 && "text-success",
                    )}
                  >
                    {moneyExact(row.variance_value)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <PaginationBar
            page={page}
            pageSize={DEFAULT_PAGE_SIZE}
            total={data?.total}
            onPageChange={setPage}
          />
        </CardContent>
      </Card>
    </div>
  );
}

function CountSheet({
  stocktakeId,
  onChanged,
}: {
  stocktakeId: string;
  onChanged: () => Promise<unknown>;
}) {
  const queryClient = useQueryClient();
  const { data: stocktake } = useGetStocktake(stocktakeId);
  const saveCounts = useSetStocktakeCounts();
  const approve = useApproveStocktake();
  const cancel = useCancelStocktake();
  const [counts, setCounts] = useState<Record<string, string>>({});

  useEffect(() => {
    if (stocktake) {
      const initial: Record<string, string> = {};
      for (const line of stocktake.lines ?? []) {
        if (line.counted_quantity !== null && line.counted_quantity !== undefined) {
          initial[line.stock_item_id] = String(line.counted_quantity);
        }
      }
      setCounts(initial);
    }
  }, [stocktake]);

  if (!stocktake) return <CardListSkeleton count={4} />;

  const entered = Object.entries(counts).filter(([, v]) => v !== "");
  const varianceValue = (stocktake.lines ?? []).reduce((sum, line) => {
    const raw = counts[line.stock_item_id];
    if (raw === undefined || raw === "") return sum;
    return sum + (Number(raw) - Number(line.expected_quantity)) * Number(line.unit_cost);
  }, 0);

  const save = async () => {
    try {
      await saveCounts.mutateAsync({
        stocktakeId,
        data: {
          lines: entered.map(([stock_item_id, counted_quantity]) => ({
            stock_item_id,
            counted_quantity,
          })),
        },
      });
      await queryClient.invalidateQueries({ queryKey: ["/api/v1/stocktakes"] });
      toast.success("Counts saved");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const post = async () => {
    if (
      !(await confirmDialog({
        title: "Approve stocktake",
        message: `Post ${entered.length} counted line(s) as stock adjustments? This changes quantities on hand.`,
      }))
    )
      return;
    try {
      await approve.mutateAsync({ stocktakeId });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["/api/v1/stocktakes"] }),
        queryClient.invalidateQueries({ queryKey: ["/api/v1/stock-items"] }),
        onChanged(),
      ]);
      toast.success("Stocktake approved — adjustments posted");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const abandon = async () => {
    if (
      !(await confirmDialog({
        title: "Cancel count",
        message: "Discard this count? Nothing will be adjusted.",
        tone: "danger",
      }))
    )
      return;
    try {
      await cancel.mutateAsync({ stocktakeId });
      await onChanged();
      toast.success("Count cancelled");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Card className="mb-4">
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>
          {stocktake.doc_number}
          <span className="ml-2 text-sm font-normal text-muted-foreground">
            {entered.length} of {stocktake.line_count} counted
          </span>
        </CardTitle>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "text-sm font-medium tabular-nums",
              varianceValue < 0 && "text-destructive",
              varianceValue > 0 && "text-success",
            )}
          >
            {moneyExact(varianceValue)} variance
          </span>
          <Can perm="inventory:issue">
            <Button variant="outline" size="sm" disabled={saveCounts.isPending} onClick={() => void save()}>
              Save Counts
            </Button>
          </Can>
          <Can perm="inventory:write">
            <Button size="sm" disabled={approve.isPending || entered.length === 0} onClick={() => void post()}>
              <CheckCircle /> Approve
            </Button>
            <Button variant="ghost" size="icon" className="text-destructive" title="Cancel count" onClick={() => void abandon()}>
              <Prohibit />
            </Button>
          </Can>
        </div>
      </CardHeader>
      <CardContent className="max-h-[50vh] overflow-y-auto p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Item</TableHead>
              <TableHead className="text-right">Expected</TableHead>
              <TableHead className="w-32 text-right">Counted</TableHead>
              <TableHead className="text-right">Variance</TableHead>
              <TableHead className="text-right">Value</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(stocktake.lines ?? []).map((line) => {
              const raw = counts[line.stock_item_id] ?? "";
              const counted = raw === "" ? null : Number(raw);
              const variance = counted === null ? null : counted - Number(line.expected_quantity);
              return (
                <TableRow key={line.id}>
                  <TableCell>
                    <div className="font-medium">{line.name}</div>
                    <div className="font-mono text-xs text-muted-foreground">{line.code}</div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {Number(line.expected_quantity).toLocaleString()} {line.unit}
                  </TableCell>
                  <TableCell>
                    <Input
                      type="number"
                      step="0.001"
                      min="0"
                      className="h-8 text-right tabular-nums"
                      placeholder="—"
                      value={raw}
                      onChange={(e) =>
                        setCounts((prev) => ({
                          ...prev,
                          [line.stock_item_id]: e.target.value,
                        }))
                      }
                    />
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right tabular-nums",
                      variance !== null && variance < 0 && "text-destructive",
                      variance !== null && variance > 0 && "text-success",
                    )}
                  >
                    {variance === null ? "—" : variance.toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {variance === null
                      ? "—"
                      : moneyExact(variance * Number(line.unit_cost))}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
