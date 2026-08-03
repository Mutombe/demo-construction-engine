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
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateExpenseClaim,
  useGetBoq,
  useListProjects,
} from "@/lib/api/generated/endpoints";

const CATEGORIES = ["materials", "transport", "fuel", "accommodation", "meals", "tools", "other"];

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

export function ExpenseFormDialog({
  open,
  onOpenChange,
  defaultProjectId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultProjectId?: string;
}) {
  const queryClient = useQueryClient();
  const { data: projects } = useListProjects({ page_size: 100 }, { query: { enabled: open } });
  const createMutation = useCreateExpenseClaim();

  const [projectId, setProjectId] = useState("");
  const [boqItemId, setBoqItemId] = useState("");
  const [category, setCategory] = useState("materials");
  const [expenseDate, setExpenseDate] = useState("");
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [receiptRef, setReceiptRef] = useState("");

  const { data: boq } = useGetBoq(projectId, { query: { enabled: open && !!projectId } });

  useEffect(() => {
    if (open) {
      setProjectId(defaultProjectId ?? "");
      setBoqItemId("");
      setCategory("materials");
      setExpenseDate(new Date().toISOString().slice(0, 10));
      setAmount("");
      setDescription("");
      setReceiptRef("");
    }
  }, [open, defaultProjectId]);

  const save = async () => {
    if (!projectId || !amount || !description.trim()) {
      toast.error("Project, amount and description are required");
      return;
    }
    try {
      await createMutation.mutateAsync({
        projectId,
        data: {
          category: category as never,
          expense_date: expenseDate,
          amount,
          description,
          receipt_ref: receiptRef || null,
          boq_item_id: boqItemId || null,
        },
      });
      await queryClient.invalidateQueries();
      toast.success("Expense claim submitted for approval");
      onOpenChange(false);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New expense claim</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Project</Label>
            <Select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">Select project…</option>
              {projects?.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code} — {p.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label>Category</Label>
              <Select value={category} onChange={(e) => setCategory(e.target.value)}>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Date</Label>
              <Input
                type="date"
                value={expenseDate}
                onChange={(e) => setExpenseDate(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Amount (USD)</Label>
              <Input
                type="number"
                step="0.01"
                min="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Description</Label>
            <Textarea
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Diesel for generator…"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Receipt reference</Label>
              <Input value={receiptRef} onChange={(e) => setReceiptRef(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>BOQ line (optional)</Label>
              <Select value={boqItemId} onChange={(e) => setBoqItemId(e.target.value)}>
                <option value="">Unallocated</option>
                {boq?.sections.flatMap((s) =>
                  (s.items ?? []).map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.item_code} — {item.description.slice(0, 40)}
                    </option>
                  )),
                )}
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button disabled={createMutation.isPending} onClick={() => void save()}>
              {createMutation.isPending ? "Submitting…" : "Submit claim"}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
