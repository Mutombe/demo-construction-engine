import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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
import { errDetail } from "@/lib/api/errors";
import { useCreatePayment, useListOpenOrders } from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";
import { toast } from "@/lib/toast";

export function PaySupplierDialog({
  supplierId,
  supplierName,
  open,
  onOpenChange,
}: {
  supplierId: string | null;
  supplierName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const { data: orders } = useListOpenOrders(supplierId ?? "", {
    query: { enabled: open && !!supplierId },
  });
  const pay = useCreatePayment();
  const [amounts, setAmounts] = useState<Record<string, string>>({});
  const [method, setMethod] = useState("Bank transfer");
  const [reference, setReference] = useState("");

  const allocated = Object.values(amounts).reduce(
    (sum, value) => sum + (Number(value) || 0),
    0,
  );

  const submit = async () => {
    const allocations = Object.entries(amounts)
      .filter(([, value]) => Number(value) > 0)
      .map(([purchase_order_id, value]) => ({
        purchase_order_id,
        amount: String(Number(value).toFixed(2)),
      }));
    if (allocations.length === 0) return;
    try {
      await pay.mutateAsync({
        data: {
          supplier_id: supplierId as string,
          amount: allocated.toFixed(2),
          method: method || null,
          reference: reference || null,
          allocations,
        },
      });
      toast.success(`Paid ${moneyExact(allocated)} to ${supplierName}`);
      setAmounts({});
      setReference("");
      await queryClient.invalidateQueries();
      onOpenChange(false);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Pay {supplierName}</DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground">
          Allocate against the orders being settled. The payment debits what was owed and
          credits the bank, so the books move with it.
        </p>

        <div className="max-h-72 space-y-2 overflow-y-auto">
          {orders?.length === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Nothing outstanding for this supplier
            </p>
          )}
          {orders?.map((order) => (
            <div key={order.id} className="flex items-center gap-3 rounded-md border p-2.5">
              <div className="min-w-0 flex-1">
                <p className="font-mono text-xs">{order.doc_number}</p>
                <p className="text-xs text-muted-foreground">
                  received {order.received_date ? fmtDate(order.received_date) : "—"} ·{" "}
                  {moneyExact(order.outstanding)} outstanding
                </p>
              </div>
              <Input
                className="w-32"
                inputMode="decimal"
                placeholder="0.00"
                value={amounts[order.id] ?? ""}
                onChange={(e) => setAmounts({ ...amounts, [order.id]: e.target.value })}
              />
              <Button
                variant="ghost"
                size="sm"
                title="Settle this order in full"
                onClick={() =>
                  setAmounts({ ...amounts, [order.id]: String(order.outstanding) })
                }
              >
                All
              </Button>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="method">Method</Label>
            <Input id="method" value={method} onChange={(e) => setMethod(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ref">Reference</Label>
            <Input
              id="ref"
              placeholder="Transfer or cheque number"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
            />
          </div>
        </div>

        <div className="flex items-baseline justify-between border-t pt-3">
          <span className="text-sm font-medium">Payment total</span>
          <span className="text-lg font-semibold tabular-nums">{moneyExact(allocated)}</span>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={allocated <= 0 || pay.isPending} onClick={() => void submit()}>
            {pay.isPending ? "Recording…" : "Record Payment"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
