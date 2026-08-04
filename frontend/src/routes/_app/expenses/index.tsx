import { keepPreviousData, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Check, Plus, X } from "@phosphor-icons/react";
import { useState } from "react";
import { z } from "zod";
import { PageHeader } from "@/components/layout/AppShell";
import { Can } from "@/components/layout/Can";
import { Button } from "@/components/ui/button";
import { confirmDialog } from "@/components/ui/confirm";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ClickableRow, EntityLink, RowActions } from "@/components/ui/linked-row";
import { DEFAULT_PAGE_SIZE, PaginationBar } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
import { TableSkeleton } from "@/components/ui/skeleton";
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
  getGetExpenseClaimQueryOptions,
  useApproveExpenseClaim,
  useCancelExpenseClaim,
  useListExpenseClaims,
  useRejectExpenseClaim,
} from "@/lib/api/generated/endpoints";
import { isOptimistic, optimistic, patchRow } from "@/lib/api/optimistic";
import { fmtDate, moneyExact } from "@/lib/format";

const searchSchema = z.object({
  status: z.enum(["pending", "approved", "rejected", "cancelled"]).optional(),
  mine: z.boolean().optional(),
  page: z.number().int().min(1).optional().default(1),
});

export const Route = createFileRoute("/_app/expenses/")({
  validateSearch: searchSchema,
  component: ExpensesPage,
});

function ExpensesPage() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  const queryClient = useQueryClient();
  const currentUser = useAuthStore((s) => s.user);
  const canApprove = usePermission("expense:approve");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const { data, isLoading } = useListExpenseClaims(
    {
      status: search.status,
      mine: search.mine || undefined,
      page: search.page,
      page_size: DEFAULT_PAGE_SIZE,
    },
    { query: { placeholderData: keepPreviousData } },
  );
  // Decisions apply in place instantly and roll back with a toast on failure.
  const approveMutation = useApproveExpenseClaim({
    mutation: optimistic(queryClient, {
      prefixes: ["/api/v1/expenses"],
      invalidate: ["/api/v1/expenses", "/api/v1/projects", "/api/v1/dashboard"],
      successToast: "Claim approved. Cost posted to the project budget",
      apply: (old, vars: { claimId: string }) =>
        patchRow(vars.claimId, { status: "approved" })(old),
    }),
  });
  const rejectMutation = useRejectExpenseClaim({
    mutation: optimistic(queryClient, {
      prefixes: ["/api/v1/expenses"],
      successToast: "Claim rejected",
      apply: (old, vars: { claimId: string }) =>
        patchRow(vars.claimId, { status: "rejected" })(old),
    }),
  });
  const cancelMutation = useCancelExpenseClaim({
    mutation: optimistic(queryClient, {
      prefixes: ["/api/v1/expenses"],
      successToast: "Claim cancelled",
      apply: (old, vars: { claimId: string }) =>
        patchRow(vars.claimId, { status: "cancelled" })(old),
    }),
  });

  const approve = (claimId: string) => {
    void approveMutation.mutateAsync({ claimId }).catch(() => undefined);
  };

  const reject = () => {
    if (!rejecting || !rejectReason.trim()) return;
    setRejecting(null);
    setRejectReason("");
    void rejectMutation
      .mutateAsync({ claimId: rejecting, data: { reason: rejectReason } })
      .catch(() => undefined);
  };

  const cancel = async (claimId: string) => {
    if (
      !(await confirmDialog({
        title: "Cancel claim",
        message: "Cancel this claim?",
        tone: "danger",
      }))
    )
      return;
    void cancelMutation.mutateAsync({ claimId }).catch(() => undefined);
  };

  return (
    <div>
      <PageHeader
        title="Expenses"
        description="Expense claims and the approval queue"
        actions={
          <Can perm="expense:submit">
            <Button onClick={() => setDialogOpen(true)}>
              <Plus /> New Claim
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
                page: 1, // filters reset paging
              }),
              replace: true,
            })
          }
        >
          <option value="">All Statuses</option>
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
                search: (prev) => ({ ...prev, mine: e.target.checked || undefined, page: 1 }),
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
            {isLoading && !data && <TableSkeleton columns={7} />}
            {!isLoading && !data?.items.length && (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                  No claims match the filters.
                </TableCell>
              </TableRow>
            )}
            {data?.items.map((claim) => {
              const isOwn = claim.created_by === currentUser?.id;
              const ghost = isOptimistic(claim);
              return (
                <ClickableRow
                  key={claim.id}
                  to="/expenses/$claimId"
                  params={{ claimId: claim.id }}
                  prefetch={() => getGetExpenseClaimQueryOptions(claim.id)}
                  disabled={ghost}
                  className={ghost ? "row-creating" : undefined}
                >
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
                  <TableCell className="text-sm">
                    <EntityLink
                      to="/projects/$projectId"
                      params={{ projectId: claim.project_id }}
                      className="font-mono text-xs font-normal"
                    >
                      {claim.project_code}
                    </EntityLink>
                  </TableCell>
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
                  <RowActions>
                    {ghost && (
                      <span className="text-xs italic text-muted-foreground">Creating…</span>
                    )}
                    {!ghost && claim.status === "pending" && (
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
                  </RowActions>
                </ClickableRow>
              );
            })}
          </TableBody>
        </Table>
        <PaginationBar
          page={search.page}
          pageSize={DEFAULT_PAGE_SIZE}
          total={data?.total}
          onPageChange={(page) =>
            void navigate({ search: (prev) => ({ ...prev, page }), replace: true })
          }
        />
      </div>

      <ExpenseFormDialog open={dialogOpen} onOpenChange={setDialogOpen} />

      <Dialog open={rejecting !== null} onOpenChange={(open) => !open && setRejecting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject Claim</DialogTitle>
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
                Reject Claim
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
