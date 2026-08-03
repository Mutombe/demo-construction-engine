import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
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

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

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
  const createMutation = useCreateStockItem();
  const updateMutation = useUpdateStockItem();

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

  const save = async () => {
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
    try {
      if (item) {
        await updateMutation.mutateAsync({ itemId: item.id, data: payload });
        toast.success("Item updated");
      } else {
        await createMutation.mutateAsync({ data: payload });
        toast.success("Item created — record a goods-in to add stock");
      }
      await queryClient.invalidateQueries();
      onOpenChange(false);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const busy = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{item ? `Edit ${item.code}` : "New stock item"}</DialogTitle>
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
              <Label>Reorder level</Label>
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
            <Button disabled={busy} onClick={() => void save()}>
              {busy ? "Saving…" : item ? "Save changes" : "Create item"}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
