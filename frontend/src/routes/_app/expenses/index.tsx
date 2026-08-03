import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Check, Plus, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { PageHeader } from "@/components/layout/AppShell";
import { Can } from "@/components/layout/Can";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useAuthStore } from "@/features/auth/store";
import { usePermission } from "@/features/auth/hooks";
import { ExpenseFormDialog } from "@/features/expenses/ExpenseFormDialog";
import { ExpenseStatusBadge } from "@/features/expenses/StatusBadges";
import {
  useApproveExpenseClaim,
  useCancelExpenseClaim,
  useListExpenseClaims,
  useRejectExpenseClaim,
} from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";

const searchSchema = z.object({
  status: z.enum(["pending", "approved", "rejected", "cancelled"]).optional(),
  mine: z.boolean().optional(),
});

export const Route = createFileRoute("/_app/expenses/")({
  validateSearch: searchSchema,
  component: ExpensesPage,
});

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

function ExpensesPage() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  const queryClient = useQueryClient();
  const currentUser = useAuthStore((s) => s.user);
  const canApprove = usePermission("expense:approve");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const { data, isLoading } = useListExpenseClaims({
    status: search.status,
    mine: search.mine || undefined,
    page_size: 100,
  });
  const approveMutation = useApproveExpenseClaim();
  const rejectMutation = useRejectExpenseClaim();
  const cancelMutation = useCancelExpenseClaim();

  const approve = async (claimId: string) => {
    try {
      await approveMutation.mutateAsync({ claimId });
      await queryClient.invalidateQueries();
      toast.success("Claim approved — cost posted to the project budget");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const reject = async () => {
    if (!rejecting || !rejectReason.trim()) return;
    try {
      await rejectMutation.mutateAsync({
        claimId: rejecting,
        data: { reason: rejectReason },
      });
      await queryClient.invalidateQueries();
      toast.success("Claim rejected");
      setRejecting(null);
      setRejectReason("");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const cancel = async (claimId: string) => {
    if (!window.confirm("Cancel this claim?")) return;
    try {
      await cancelMutation.mutateAsync({ claimId });
      await queryClient.invalidateQueries();
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <div>
      <PageHeader
        title="Expenses"
        description="Expense claims and the approval queue"
        actions={
          <Can perm="expense:submit">
            <Button onClick={() => setDialogOpen(true)}>
              <Plus /> New claim
            </Button>
          </Can>
        }
      />

      <div className="mb-4 flex items-center gap-2">
        <Select
          className="w-44"
          value={search.status ?? ""}
          onChange={(e) =>
            void navigate({
              search: (prev) => ({
                ...prev,
                status: (e.target.value || undefined) as typeof search.status,
              }),
              replace: true,
            })
          }
        >
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="cancelled">Cancelled</option>
        </Select>
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={search.mine ?? false}
            onChange={(e) =>
              void navigate({
                search: (prev) => ({ ...prev, mine: e.target.checked || undefined }),
                replace: true,
              })
            }
          />
          My claims only
        </label>
      </div>

      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Claim</TableHead>
              <TableHead>Project</TableHead>
              <TableHead>Claimant</TableHead>
              <TableHead>Category</TableHead>
              <TableHead className="text-right">Amount</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-44" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                  Loading…
                </TableCell>
              </TableRow>
            )}
            {!isLoading && !data?.items.length && (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                  No claims match the filters.
                </TableCell>
              </TableRow>
            )}
            {data?.items.map((claim) => {
              const isOwn = claim.created_by === currentUser?.id;
              return (
                <TableRow key={claim.id}>
                  <TableCell>
                    <div className="font-mono text-xs text-muted-foreground">
                      {claim.doc_number}
                    </div>
                    <div className="max-w-56 truncate text-sm">{claim.description}</div>
                    <div className="text-xs text-muted-foreground">
                      {fmtDate(claim.expense_date)}
                      {claim.receipt_ref && <> · receipt {claim.receipt_ref}</>}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">{claim.project_code}</TableCell>
                  <TableCell className="text-sm">{claim.claimant_name ?? "—"}</TableCell>
                  <TableCell className="text-sm capitalize">{claim.category}</TableCell>
                  <TableCell className="text-right font-medium tabular-nums">
                    {moneyExact(claim.amount)}
                  </TableCell>
                  <TableCell>
                    <ExpenseStatusBadge status={claim.status ?? "pending"} />
                    {claim.status === "rejected" && claim.rejection_reason && (
                      <div className="mt-0.5 max-w-40 truncate text-xs text-muted-foreground">
                        {claim.rejection_reason}
                      </div>
                    )}
                  </TableCell>
                  <TableCell>
                    {claim.status === "pending" && (
                      <div className="flex justify-end gap-1.5">
                        {canApprove && (
                          <>
                            <Button
                              size="sm"
                              disabled={isOwn || approveMutation.isPending}
                              title={isOwn ? "You cannot approve your own claim" : undefined}
                              onClick={() => void approve(claim.id)}
                            >
                              <Check className="h-3.5 w-3.5" /> Approve
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={isOwn}
                              title={isOwn ? "You cannot decide your own claim" : undefined}
                              onClick={() => setRejecting(claim.id)}
                            >
                              <X className="h-3.5 w-3.5" /> Reject
                            </Button>
                          </>
                        )}
                        {isOwn && (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => void cancel(claim.id)}
                          >
                            Cancel
                          </Button>
                        )}
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <ExpenseFormDialog open={dialogOpen} onOpenChange={setDialogOpen} />

      <Dialog open={rejecting !== null} onOpenChange={(open) => !open && setRejecting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject claim</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Textarea
              rows={3}
              placeholder="Reason for rejection (required)…"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
            />
            <DialogFooter>
              <Button variant="outline" onClick={() => setRejecting(null)}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                disabled={!rejectReason.trim() || rejectMutation.isPending}
                onClick={() => void reject()}
              >
                Reject claim
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
