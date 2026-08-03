import { useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
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
import {
  useAddWorkerPayItem,
  useCreateWorker,
  useDeleteWorkerPayItem,
  useUpdateWorker,
} from "@/lib/api/generated/endpoints";
import type { WorkerRead } from "@/lib/api/generated/model";
import { addRow, optimistic, patchRow, tempId } from "@/lib/api/optimistic";
import { moneyExact } from "@/lib/format";

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

export function WorkerFormDialog({
  open,
  onOpenChange,
  worker,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  worker?: WorkerRead | null;
}) {
  const queryClient = useQueryClient();
  const createMutation = useCreateWorker({
    mutation: optimistic(queryClient, {
      prefixes: ["/api/v1/workers"],
      successToast: "Worker added to the register",
      apply: (old, vars: { data: Record<string, unknown> }) =>
        addRow(() => ({
          id: tempId(),
          is_active: true,
          pay_items: [],
          created_at: new Date().toISOString(),
          ...vars.data,
        }))(old),
    }),
  });
  const updateMutation = useUpdateWorker({
    mutation: optimistic(queryClient, {
      prefixes: ["/api/v1/workers"],
      successToast: "Worker updated",
      apply: (old, vars: { workerId: string; data: Record<string, unknown> }) =>
        patchRow(vars.workerId, vars.data)(old),
    }),
  });
  const addItemMutation = useAddWorkerPayItem();
  const deleteItemMutation = useDeleteWorkerPayItem();

  const [fullName, setFullName] = useState("");
  const [trade, setTrade] = useState("");
  const [payBasis, setPayBasis] = useState<"daily" | "hourly">("daily");
  const [rate, setRate] = useState("");
  const [phone, setPhone] = useState("");
  const [nationalId, setNationalId] = useState("");
  const [active, setActive] = useState(true);
  // pay-item mini-form
  const [itemKind, setItemKind] = useState<"allowance" | "deduction">("allowance");
  const [itemLabel, setItemLabel] = useState("");
  const [itemAmount, setItemAmount] = useState("");

  useEffect(() => {
    if (open) {
      setFullName(worker?.full_name ?? "");
      setTrade(worker?.trade ?? "");
      setPayBasis((worker?.pay_basis as "daily" | "hourly") ?? "daily");
      setRate(worker?.rate ?? "");
      setPhone(worker?.phone ?? "");
      setNationalId(worker?.national_id ?? "");
      setActive(worker?.is_active ?? true);
      setItemLabel("");
      setItemAmount("");
    }
  }, [open, worker]);

  const save = async () => {
    if (!fullName.trim() || !trade.trim() || !rate) {
      toast.error("Name, trade and rate are required");
      return;
    }
    const payload = {
      full_name: fullName.trim(),
      trade: trade.trim(),
      pay_basis: payBasis,
      rate,
      phone: phone || null,
      national_id: nationalId || null,
    };
    // Optimistic: close now; the register updates instantly and rolls back on error.
    onOpenChange(false);
    const action = worker
      ? updateMutation.mutateAsync({
          workerId: worker.id,
          data: { ...payload, is_active: active },
        })
      : createMutation.mutateAsync({ data: payload });
    void action.catch(() => undefined);
  };

  const addItem = async () => {
    if (!worker || !itemLabel.trim() || !itemAmount) return;
    try {
      await addItemMutation.mutateAsync({
        workerId: worker.id,
        data: { kind: itemKind, label: itemLabel.trim(), amount: itemAmount },
      });
      await queryClient.invalidateQueries();
      setItemLabel("");
      setItemAmount("");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const pending = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{worker ? worker.full_name : "New worker"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Full name</Label>
              <Input value={fullName} onChange={(e) => setFullName(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Trade</Label>
              <Input
                value={trade}
                onChange={(e) => setTrade(e.target.value)}
                placeholder="Bricklayer"
              />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label>Pay basis</Label>
              <Select
                value={payBasis}
                onChange={(e) => setPayBasis(e.target.value as "daily" | "hourly")}
              >
                <option value="daily">Per day</option>
                <option value="hourly">Per hour</option>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Rate (USD)</Label>
              <Input
                type="number"
                step="0.01"
                min="0.01"
                className="text-right tabular-nums"
                value={rate}
                onChange={(e) => setRate(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Phone</Label>
              <Input value={phone} onChange={(e) => setPhone(e.target.value)} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>National ID</Label>
              <Input value={nationalId} onChange={(e) => setNationalId(e.target.value)} />
            </div>
            {worker && (
              <div className="space-y-1.5">
                <Label>Status</Label>
                <Select
                  value={active ? "active" : "inactive"}
                  onChange={(e) => setActive(e.target.value === "active")}
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive (off payroll)</option>
                </Select>
              </div>
            )}
          </div>

          {worker && (
            <div className="space-y-2 rounded-md border p-3">
              <Label>Recurring allowances &amp; deductions (per pay run)</Label>
              {(worker.pay_items ?? []).length === 0 && (
                <p className="text-xs text-muted-foreground">None yet.</p>
              )}
              {(worker.pay_items ?? []).map((item) => (
                <div key={item.id} className="flex items-center gap-2 text-sm">
                  <Badge variant={item.kind === "allowance" ? "success" : "warning"}>
                    {item.kind}
                  </Badge>
                  <span className="flex-1 truncate">{item.label}</span>
                  <span className="tabular-nums">{moneyExact(item.amount)}</span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-destructive"
                    onClick={() =>
                      void deleteItemMutation
                        .mutateAsync({ itemId: item.id })
                        .then(() => queryClient.invalidateQueries())
                        .catch((err) => toast.error(errDetail(err)))
                    }
                  >
                    <Trash2 />
                  </Button>
                </div>
              ))}
              <div className="flex items-end gap-2 pt-1">
                <Select
                  className="w-32"
                  value={itemKind}
                  onChange={(e) => setItemKind(e.target.value as "allowance" | "deduction")}
                >
                  <option value="allowance">Allowance</option>
                  <option value="deduction">Deduction</option>
                </Select>
                <Input
                  placeholder="Label (Transport…)"
                  value={itemLabel}
                  onChange={(e) => setItemLabel(e.target.value)}
                />
                <Input
                  type="number"
                  step="0.01"
                  className="w-24 text-right"
                  placeholder="0.00"
                  value={itemAmount}
                  onChange={(e) => setItemAmount(e.target.value)}
                />
                <Button
                  variant="outline"
                  size="icon"
                  disabled={addItemMutation.isPending}
                  onClick={() => void addItem()}
                >
                  <Plus />
                </Button>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button disabled={pending} onClick={() => void save()}>
              {pending ? "Saving…" : worker ? "Save changes" : "Add worker"}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
