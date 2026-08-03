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
import { Textarea } from "@/components/ui/textarea";
import {
  useAdjustStock,
  useGoodsIn,
  useIssueStock,
  useListProjects,
} from "@/lib/api/generated/endpoints";
import type { StockItemRead } from "@/lib/api/generated/model";
import { moneyExact } from "@/lib/format";

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

export type MovementKind = "goods-in" | "issue" | "adjust";

export function MovementDialog({
  kind,
  item,
  onClose,
}: {
  kind: MovementKind | null;
  item: StockItemRead | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const open = kind !== null && item !== null;
  const { data: projects } = useListProjects({ page_size: 100 }, { query: { enabled: open } });
  const goodsInMutation = useGoodsIn();
  const issueMutation = useIssueStock();
  const adjustMutation = useAdjustStock();

  const [quantity, setQuantity] = useState("");
  const [unitCost, setUnitCost] = useState("");
  const [projectId, setProjectId] = useState("");
  const [reference, setReference] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (open) {
      setQuantity("");
      setUnitCost("");
      setProjectId("");
      setReference("");
      setNotes("");
    }
  }, [open, kind]);

  if (!open || !item) return null;

  const busy = goodsInMutation.isPending || issueMutation.isPending || adjustMutation.isPending;

  const submit = async () => {
    try {
      if (kind === "goods-in") {
        await goodsInMutation.mutateAsync({
          itemId: item.id,
          data: {
            quantity,
            unit_cost: unitCost || "0",
            reference: reference || null,
            notes: notes || null,
          },
        });
        toast.success("Goods received into store");
      } else if (kind === "issue") {
        if (!projectId) {
          toast.error("Select the project to charge");
          return;
        }
        await issueMutation.mutateAsync({
          itemId: item.id,
          data: { project_id: projectId, quantity, notes: notes || null },
        });
        toast.success("Stock issued — cost posted to the project budget");
      } else {
        if (!notes.trim()) {
          toast.error("Adjustments require a note");
          return;
        }
        await adjustMutation.mutateAsync({
          itemId: item.id,
          data: { quantity, notes },
        });
        toast.success("Stock adjusted");
      }
      await queryClient.invalidateQueries();
      onClose();
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const titles: Record<MovementKind, string> = {
    "goods-in": `Goods in — ${item.name}`,
    issue: `Issue to project — ${item.name}`,
    adjust: `Adjust stock — ${item.name}`,
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{titles[kind]}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            On hand: {Number(item.qty_on_hand).toLocaleString()} {item.unit} @{" "}
            {moneyExact(item.unit_cost)} avg
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>
                Quantity {kind === "adjust" && "(± signed)"} ({item.unit})
              </Label>
              <Input
                type="number"
                step="any"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
              />
            </div>
            {kind === "goods-in" && (
              <div className="space-y-1.5">
                <Label>Unit cost (USD)</Label>
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  value={unitCost}
                  onChange={(e) => setUnitCost(e.target.value)}
                />
              </div>
            )}
            {kind === "issue" && (
              <div className="space-y-1.5">
                <Label>Charge to project</Label>
                <Select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                  <option value="">Select project…</option>
                  {projects?.items.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.code} — {p.name}
                    </option>
                  ))}
                </Select>
              </div>
            )}
          </div>
          {kind === "goods-in" && (
            <div className="space-y-1.5">
              <Label>Reference (PO / delivery note)</Label>
              <Input
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                placeholder="PO-2026-001"
              />
            </div>
          )}
          <div className="space-y-1.5">
            <Label>Notes{kind === "adjust" && " (required)"}</Label>
            <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button disabled={busy || !quantity} onClick={() => void submit()}>
              {busy ? "Saving…" : "Confirm"}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
