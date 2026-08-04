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
import { Select } from "@/components/ui/select";
import { errDetail } from "@/lib/api/errors";
import {
  useConvertRequisitionToPo,
  useListSuppliers,
} from "@/lib/api/generated/endpoints";
import type { RequisitionRead } from "@/lib/api/generated/model";
import { toast } from "@/lib/toast";

/** Shared by the request queue and the request detail page so both offer the
 *  same conversion, with the same guarantees, from wherever you happen to be. */
export function ConvertToPoDialog({
  requisition,
  onOpenChange,
  onDone,
}: {
  requisition: RequisitionRead | null;
  onOpenChange: (open: boolean) => void;
  onDone: (poId: string) => Promise<void>;
}) {
  const { data: suppliers } = useListSuppliers({ page_size: 100, active_only: true });
  const convertMutation = useConvertRequisitionToPo();
  const [supplierId, setSupplierId] = useState("");
  const [expected, setExpected] = useState("");
  const [loadedFor, setLoadedFor] = useState<string | null>(null);

  if (requisition && loadedFor !== requisition.id) {
    setSupplierId(suppliers?.items[0]?.id ?? "");
    setExpected(requisition.needed_by ?? "");
    setLoadedFor(requisition.id);
  }

  const convert = async () => {
    if (!requisition || !supplierId) {
      toast.error("Pick a supplier");
      return;
    }
    try {
      const po = await convertMutation.mutateAsync({
        requisitionId: requisition.id,
        data: { supplier_id: supplierId, expected_delivery: expected || null },
      });
      toast.success(`${po.doc_number} drafted — check prices, then issue`);
      await onDone(po.id);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={!!requisition} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Convert {requisition?.doc_number} to a Purchase Order</DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground">
          Lines are priced from what this supplier last charged for the same BOQ item. The
          order is created as a draft — review the prices before issuing it.
        </p>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Supplier</Label>
            <Select value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
              {suppliers?.items.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Expected Delivery</Label>
            <Input
              type="date"
              value={expected}
              onChange={(e) => setExpected(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={convertMutation.isPending} onClick={() => void convert()}>
            {convertMutation.isPending ? "Creating…" : "Create Draft PO"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
