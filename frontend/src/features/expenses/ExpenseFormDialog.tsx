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
import { useAuth } from "@/features/auth/hooks";
import {
  useCreateExpenseClaim,
  useGetBoq,
  useListProjects,
} from "@/lib/api/generated/endpoints";
import { addRow, optimistic, tempId } from "@/lib/api/optimistic";

const CATEGORIES = ["materials", "transport", "fuel", "accommodation", "meals", "tools", "other"];

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
  const { user } = useAuth();
  const { data: projects } = useListProjects({ page_size: 100 }, { query: { enabled: open } });
  // Optimistic create: the dialog closes instantly and a shimmering placeholder
  // row appears at the top of the list; it settles (or rolls back) when the
  // server answers.
  const createMutation = useCreateExpenseClaim({
    mutation: optimistic(queryClient, {
      prefixes: ["/api/v1/expenses"],
      successToast: "Expense claim submitted for approval",
      apply: (old, vars: { projectId: string; data: Record<string, unknown> }) => {
        const project = projects?.items.find((p) => p.id === vars.projectId);
        return addRow(() => ({
          id: tempId(),
          doc_number: "EXP-…",
          status: "pending",
          project_id: vars.projectId,
          project_code: project?.code,
          project_name: project?.name,
          claimant_name: user?.full_name,
          created_by: user?.id ?? null,
          approved_by: null,
          decided_at: null,
          rejection_reason: null,
          cost_entry_id: null,
          created_at: new Date().toISOString(),
          ...vars.data,
        }))(old);
      },
    }),
  });

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

  const save = () => {
    if (!projectId || !amount || !description.trim()) {
      toast.error("Project, amount and description are required");
      return;
    }
    // Fire-and-reconcile: close now, the optimistic handlers do the rest.
    onOpenChange(false);
    void createMutation
      .mutateAsync({
        projectId,
        data: {
          category: category as never,
          expense_date: expenseDate,
          amount,
          description,
          receipt_ref: receiptRef || null,
          boq_item_id: boqItemId || null,
        },
      })
      .catch(() => undefined); // error toast + rollback handled by the helper
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
            <Button onClick={save}>Submit claim</Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
