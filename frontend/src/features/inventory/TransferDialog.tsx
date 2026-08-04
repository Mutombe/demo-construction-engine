import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
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
import { Textarea } from "@/components/ui/textarea";
import { errDetail } from "@/lib/api/errors";
import {
  useCreateStockTransfer,
  useGetStockItemLevels,
  useListStockLocations,
} from "@/lib/api/generated/endpoints";
import type { StockItemRead } from "@/lib/api/generated/model";
import { moneyExact } from "@/lib/format";
import { toast } from "@/lib/toast";

/** Move material between our own stores. No cost is incurred — a transfer
 *  relocates stock, and cost only reaches a project when it is issued. */
export function TransferDialog({
  item,
  onClose,
}: {
  item: StockItemRead | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { data: locations } = useListStockLocations({ active_only: true });
  const { data: levels } = useGetStockItemLevels(item?.id ?? "", {
    query: { enabled: !!item } as { enabled: boolean },
  });
  const createTransfer = useCreateStockTransfer();

  const [fromId, setFromId] = useState("");
  const [toId, setToId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (item) {
      setQuantity("");
      setNotes("");
      // Default the source to wherever the most stock actually is
      const richest = [...(levels ?? [])].sort(
        (a, b) => Number(b.quantity) - Number(a.quantity),
      )[0];
      setFromId(richest?.location_id ?? "");
    }
  }, [item, levels]);

  const held = new Map(
    (levels ?? []).map((l) => [l.location_id, Number(l.quantity)]),
  );
  const available = held.get(fromId) ?? 0;
  const overdrawn = Number(quantity) > available;

  const submit = async () => {
    if (!item || !fromId || !toId) {
      toast.error("Pick where the stock is moving from and to");
      return;
    }
    try {
      const result = await createTransfer.mutateAsync({
        data: {
          stock_item_id: item.id,
          from_location_id: fromId,
          to_location_id: toId,
          quantity,
          notes: notes || null,
        },
      });
      await queryClient.invalidateQueries({ queryKey: ["/api/v1/stock-items"] });
      await queryClient.invalidateQueries({ queryKey: ["/api/v1/stock-transfers"] });
      await queryClient.invalidateQueries({ queryKey: ["/api/v1/stock-locations"] });
      toast.success(`${result.doc_number} — ${result.quantity} ${item.unit} moved`);
      onClose();
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={!!item} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Transfer {item?.name}</DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground">
          Moves material between stores. Nothing is spent — cost reaches a project only
          when the stock is issued.
        </p>

        <div className="space-y-4">
          <div className="grid grid-cols-[1fr_auto_1fr] items-end gap-2">
            <div className="space-y-1.5">
              <Label>From</Label>
              <Select value={fromId} onChange={(e) => setFromId(e.target.value)}>
                <option value="">Select…</option>
                {locations?.map((loc) => (
                  <option key={loc.id} value={loc.id}>
                    {loc.name} ({held.get(loc.id) ?? 0})
                  </option>
                ))}
              </Select>
            </div>
            <ArrowRight className="mb-2.5 size-4 text-muted-foreground" />
            <div className="space-y-1.5">
              <Label>To</Label>
              <Select value={toId} onChange={(e) => setToId(e.target.value)}>
                <option value="">Select…</option>
                {locations
                  ?.filter((loc) => loc.id !== fromId)
                  .map((loc) => (
                    <option key={loc.id} value={loc.id}>
                      {loc.name}
                    </option>
                  ))}
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Quantity</Label>
            <Input
              type="number"
              min="0"
              step="0.001"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              placeholder={`Up to ${available} ${item?.unit ?? ""}`}
            />
            {fromId && (
              <p
                className={
                  overdrawn ? "text-xs font-medium text-destructive" : "text-xs text-muted-foreground"
                }
              >
                {overdrawn
                  ? `Only ${available} ${item?.unit} at that location`
                  : `${available} ${item?.unit} available there${
                      item ? ` · ${moneyExact(Number(quantity || 0) * Number(item.unit_cost))}` : ""
                    }`}
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label>Notes</Label>
            <Textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Why it is moving"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={
              createTransfer.isPending || overdrawn || !fromId || !toId || !Number(quantity)
            }
            onClick={() => void submit()}
          >
            {createTransfer.isPending ? "Moving…" : "Transfer Stock"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
