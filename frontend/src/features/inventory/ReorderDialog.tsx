import { useQueryClient } from "@tanstack/react-query";
import { Warning } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { CardListSkeleton } from "@/components/ui/skeleton";
import { errDetail } from "@/lib/api/errors";
import {
  useCreateReorderPos,
  useGetReorderSuggestions,
  useListProjects,
} from "@/lib/api/generated/endpoints";
import { moneyExact } from "@/lib/format";
import { toast } from "@/lib/toast";

/** Turns the low-stock list into draft purchase orders, grouped by whichever
 *  supplier last delivered each item at the price they last charged. */
export function ReorderDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const { data: suggestions, isLoading } = useGetReorderSuggestions({
    query: { enabled: open },
  });
  const { data: projects } = useListProjects({ page_size: 100 });
  const createMutation = useCreateReorderPos();

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [projectId, setProjectId] = useState("");
  const [expected, setExpected] = useState("");

  useEffect(() => {
    if (open && suggestions) {
      // Pre-select everything we know how to buy
      setSelected(
        new Set(
          suggestions.items.filter((s) => s.supplier_id).map((s) => s.stock_item_id),
        ),
      );
    }
  }, [open, suggestions]);

  useEffect(() => {
    if (open) {
      setProjectId((prev) => prev || projects?.items[0]?.id || "");
      setExpected("");
    }
  }, [open, projects]);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const items = suggestions?.items ?? [];
  const chosen = items.filter((s) => selected.has(s.stock_item_id));
  const chosenTotal = chosen.reduce((sum, s) => sum + Number(s.estimated_cost), 0);
  const supplierCount = new Set(chosen.map((s) => s.supplier_id).filter(Boolean)).size;

  const raise = async () => {
    if (!projectId || chosen.length === 0) {
      toast.error("Pick a project and at least one item");
      return;
    }
    try {
      const result = await createMutation.mutateAsync({
        data: {
          project_id: projectId,
          stock_item_ids: chosen.map((s) => s.stock_item_id),
          expected_delivery: expected || null,
        },
      });
      await queryClient.invalidateQueries({ queryKey: ["/api/v1/stock-items"] });
      await queryClient.invalidateQueries({ queryKey: ["/api/v1/dashboard"] });
      if (result.po_numbers.length > 0) {
        toast.success(
          `Drafted ${result.po_numbers.join(", ")}. Review prices, then issue`,
        );
      }
      if (result.skipped_items.length > 0) {
        toast.error(
          `No known supplier for ${result.skipped_items.join(", ")}. Order those by hand`,
        );
      }
      onOpenChange(false);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] max-w-3xl flex-col">
        <DialogHeader>
          <DialogTitle>Reorder Low Stock</DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground">
          Quantities top each item back up to twice its reorder level, priced from the last
          delivery. One draft order per supplier, and nothing is sent until you issue it.
        </p>

        <div className="min-h-0 flex-1 overflow-y-auto rounded-md border">
          {isLoading ? (
            <div className="p-4">
              <CardListSkeleton count={4} />
            </div>
          ) : items.length === 0 ? (
            <EmptyState
              icon={<Warning />}
              title="Nothing is below its reorder level"
              hint="Stock levels are healthy. Nothing to reorder right now."
            />
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-muted text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="w-8 px-3 py-2" />
                  <th className="px-3 py-2 text-left font-medium">Item</th>
                  <th className="px-2 py-2 text-right font-medium">On Hand</th>
                  <th className="px-2 py-2 text-right font-medium">Order</th>
                  <th className="px-3 py-2 text-left font-medium">Supplier</th>
                  <th className="px-3 py-2 text-right font-medium">Est. Cost</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr
                    key={row.stock_item_id}
                    className="border-t transition-colors hover:bg-muted/30"
                  >
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        checked={selected.has(row.stock_item_id)}
                        disabled={!row.supplier_id}
                        onChange={() => toggle(row.stock_item_id)}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <div className="font-medium">{row.name}</div>
                      <div className="font-mono text-xs text-muted-foreground">{row.code}</div>
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums text-muted-foreground">
                      {Number(row.qty_on_hand).toLocaleString()} / {Number(row.reorder_level).toLocaleString()}
                    </td>
                    <td className="px-2 py-2 text-right font-medium tabular-nums">
                      {Number(row.suggested_quantity).toLocaleString()} {row.unit}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {row.supplier_name ? (
                        <>
                          {row.supplier_name}
                          <div className="text-muted-foreground">
                            {moneyExact(row.last_unit_cost)} on {row.last_po_number}
                          </div>
                        </>
                      ) : (
                        <span className="text-warning">Never purchased, order by hand</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {moneyExact(row.estimated_cost)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {items.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Charge to Project</Label>
              <Select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                {projects?.items.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.code} · {p.name}
                  </option>
                ))}
              </Select>
              <p className="text-xs text-muted-foreground">
                Received into the store, so cost only hits a project when issued.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label>Expected Delivery</Label>
              <Input
                type="date"
                value={expected}
                onChange={(e) => setExpected(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Sets the date these orders are measured late against.
              </p>
            </div>
          </div>
        )}

        <DialogFooter>
          <div className="mr-auto text-sm text-muted-foreground">
            {chosen.length} item{chosen.length === 1 ? "" : "s"} · {supplierCount} order
            {supplierCount === 1 ? "" : "s"} ·{" "}
            <span className="font-medium text-foreground">{moneyExact(chosenTotal)}</span>
          </div>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={createMutation.isPending || chosen.length === 0}
            onClick={() => void raise()}
          >
            {createMutation.isPending ? "Drafting…" : "Draft Purchase Orders"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
