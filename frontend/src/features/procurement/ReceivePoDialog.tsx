import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "@/lib/toast";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useListStockItems, useReceivePurchaseOrder } from "@/lib/api/generated/endpoints";
import type { PoDetail, PoStoreLineMapping } from "@/lib/api/generated/model";
import { moneyExact } from "@/lib/format";

const NEW_ITEM = "__new__";

interface LineState {
  choice: string; // stock item id, NEW_ITEM, or ""
  newCode: string;
  newName: string;
}

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

export function ReceivePoDialog({
  open,
  onOpenChange,
  po,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  po: PoDetail;
}) {
  const queryClient = useQueryClient();
  const receiveMutation = useReceivePurchaseOrder();
  const { data: stock } = useListStockItems(
    { page_size: 200 },
    { query: { enabled: open } },
  );

  const items = po.items ?? [];
  const [destination, setDestination] = useState<"project" | "store">("project");
  const [lines, setLines] = useState<Record<string, LineState>>({});

  useEffect(() => {
    if (open) {
      setDestination("project");
      setLines(
        Object.fromEntries(
          items.map((item) => [item.id, { choice: "", newCode: "", newName: item.description }]),
        ),
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const setLine = (id: string, patch: Partial<LineState>) =>
    setLines((prev) => {
      const current = prev[id] ?? { choice: "", newCode: "", newName: "" };
      return { ...prev, [id]: { ...current, ...patch } };
    });

  const storeReady =
    destination === "project" ||
    items.every((item) => {
      const line = lines[item.id];
      if (!line?.choice) return false;
      return line.choice !== NEW_ITEM || (line.newCode.trim() && line.newName.trim());
    });

  const submit = async () => {
    try {
      const store_lines: PoStoreLineMapping[] | null =
        destination === "store"
          ? items.map((item) => {
              const line = lines[item.id] ?? { choice: "", newCode: "", newName: "" };
              return line.choice === NEW_ITEM
                ? {
                    po_item_id: item.id,
                    new_item: {
                      code: line.newCode.trim(),
                      name: line.newName.trim(),
                      unit: item.unit ?? "ea",
                    },
                  }
                : { po_item_id: item.id, stock_item_id: line.choice };
            })
          : null;
      await receiveMutation.mutateAsync({
        poId: po.id,
        data: { destination, store_lines },
      });
      await queryClient.invalidateQueries();
      toast.success(
        destination === "store"
          ? "PO received into the store — stock booked at PO prices"
          : "PO received — actuals posted to the project budget",
      );
      onOpenChange(false);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Receive {po.doc_number}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Where is this delivery going?</Label>
            <div className="grid grid-cols-2 gap-2">
              <label
                className={`flex cursor-pointer flex-col rounded-md border p-3 text-sm ${destination === "project" ? "border-primary bg-primary/5" : ""}`}
              >
                <span className="flex items-center gap-2 font-medium">
                  <input
                    type="radio"
                    checked={destination === "project"}
                    onChange={() => setDestination("project")}
                  />
                  Straight to project
                </span>
                <span className="mt-1 text-xs text-muted-foreground">
                  Posts {items.length} cost entr{items.length === 1 ? "y" : "ies"} totalling{" "}
                  {moneyExact(po.total_amount)} against the project budget now.
                </span>
              </label>
              <label
                className={`flex cursor-pointer flex-col rounded-md border p-3 text-sm ${destination === "store" ? "border-primary bg-primary/5" : ""}`}
              >
                <span className="flex items-center gap-2 font-medium">
                  <input
                    type="radio"
                    checked={destination === "store"}
                    onChange={() => setDestination("store")}
                  />
                  Into the store
                </span>
                <span className="mt-1 text-xs text-muted-foreground">
                  Books stock at PO prices (weighted average). Cost hits a project only when the
                  stock is issued.
                </span>
              </label>
            </div>
          </div>

          {destination === "store" && (
            <div className="space-y-2">
              <Label>Map each PO line to a stock item</Label>
              <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
                {items.map((item) => {
                  const line = lines[item.id];
                  return (
                    <div key={item.id} className="rounded-md border p-2.5">
                      <div className="mb-1.5 flex items-baseline justify-between gap-2 text-sm">
                        <span className="font-medium">{item.description}</span>
                        <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                          {Number(item.quantity).toLocaleString()} {item.unit ?? ""} @{" "}
                          {moneyExact(item.unit_price)}
                        </span>
                      </div>
                      <Select
                        value={line?.choice ?? ""}
                        onChange={(e) => setLine(item.id, { choice: e.target.value })}
                      >
                        <option value="">Select stock item…</option>
                        {stock?.items.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.code} — {s.name}
                          </option>
                        ))}
                        <option value={NEW_ITEM}>＋ Create new stock item</option>
                      </Select>
                      {line?.choice === NEW_ITEM && (
                        <div className="mt-2 grid grid-cols-3 gap-2">
                          <Input
                            placeholder="Code (e.g. CEM-425)"
                            value={line.newCode}
                            onChange={(e) => setLine(item.id, { newCode: e.target.value })}
                          />
                          <Input
                            className="col-span-2"
                            placeholder="Item name"
                            value={line.newName}
                            onChange={(e) => setLine(item.id, { newName: e.target.value })}
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              disabled={receiveMutation.isPending || !storeReady}
              onClick={() => void submit()}
            >
              {receiveMutation.isPending ? "Receiving…" : "Receive delivery"}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
