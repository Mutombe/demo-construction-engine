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
import { useCreateStockItem, useUpdateStockItem } from "@/lib/api/generated/endpoints";
import type { StockItemRead } from "@/lib/api/generated/model";
import { addRow, optimistic, patchRow, tempId } from "@/lib/api/optimistic";

export function StockItemFormDialog({
  open,
  onOpenChange,
  item,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  item?: StockItemRead | null;
}) {
  const queryClient = useQueryClient();
  const createMutation = useCreateStockItem({
    mutation: optimistic(queryClient, {
      prefixes: ["/api/v1/stock-items"],
      successToast: "Item created — record a goods-in to add stock",
      apply: (old, vars: { data: Record<string, unknown> }) =>
        addRow(() => ({
          id: tempId(),
          qty_on_hand: "0",
          unit_cost: "0",
          low_stock: false,
          is_active: true,
          created_at: new Date().toISOString(),
          ...vars.data,
        }))(old),
    }),
  });
  const updateMutation = useUpdateStockItem({
    mutation: optimistic(queryClient, {
      prefixes: ["/api/v1/stock-items"],
      successToast: "Item updated",
      apply: (old, vars: { itemId: string; data: Record<string, unknown> }) =>
        patchRow(vars.itemId, vars.data)(old),
    }),
  });

  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [unit, setUnit] = useState("");
  const [reorderLevel, setReorderLevel] = useState("0");

  useEffect(() => {
    if (open) {
      setCode(item?.code ?? "");
      setName(item?.name ?? "");
      setCategory(item?.category ?? "");
      setUnit(item?.unit ?? "");
      setReorderLevel(String(item?.reorder_level ?? "0"));
    }
  }, [open, item]);

  const save = () => {
    if (!code.trim() || !name.trim() || !unit.trim()) {
      toast.error("Code, name and unit are required");
      return;
    }
    const payload = {
      code,
      name,
      category: category || null,
      unit,
      reorder_level: reorderLevel || "0",
    };
    // Optimistic: close now; row appears/patches instantly, rolls back on error.
    onOpenChange(false);
    const action = item
      ? updateMutation.mutateAsync({ itemId: item.id, data: payload })
      : createMutation.mutateAsync({ data: payload });
    void action.catch(() => undefined);
  };


  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{item ? `Edit ${item.code}` : "New Stock Item"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label>Code</Label>
              <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="CEM-425" />
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label>Name</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label>Category</Label>
              <Input
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="cement"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Unit</Label>
              <Input value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="bag" />
            </div>
            <div className="space-y-1.5">
              <Label>Reorder Level</Label>
              <Input
                type="number"
                step="any"
                min="0"
                value={reorderLevel}
                onChange={(e) => setReorderLevel(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={save}>
              {item ? "Save Changes" : "Create Item"}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
