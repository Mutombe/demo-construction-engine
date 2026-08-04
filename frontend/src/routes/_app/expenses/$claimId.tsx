import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Check, Prohibit, RadioButton, X } from "@phosphor-icons/react";
import { useState } from "react";
import { toast } from "@/lib/toast";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Can } from "@/components/layout/Can";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EntityLink } from "@/components/ui/linked-row";
import { DetailSkeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/features/auth/hooks";
import { ExpenseStatusBadge } from "@/features/expenses/StatusBadges";
import { errDetail } from "@/lib/api/errors";
import {
  getGetExpenseClaimQueryOptions,
  getGetProjectQueryOptions,
  useApproveExpenseClaim,
  useCancelExpenseClaim,
  useGetExpenseClaim,
  useRejectExpenseClaim,
} from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";

export const Route = createFileRoute("/_app/expenses/$claimId")({
  component: ExpenseClaimDetailPage,
  loader: ({ context: { queryClient }, params }) =>
    queryClient.ensureQueryData(getGetExpenseClaimQueryOptions(params.claimId)),
});

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-0.5 text-sm">{children}</div>
    </div>
  );
}

function ExpenseClaimDetailPage() {
  const { claimId } = Route.useParams();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const { data: claim } = useGetExpenseClaim(claimId);
  const approveMutation = useApproveExpenseClaim();
  const rejectMutation = useRejectExpenseClaim();
  const cancelMutation = useCancelExpenseClaim();
  const [rejectReason, setRejectReason] = useState("");
  const [rejecting, setRejecting] = useState(false);

  if (!claim) {
    return <DetailSkeleton />;
  }

  const act = async (fn: () => Promise<unknown>, successMsg: string) => {
    try {
      await fn();
      await queryClient.invalidateQueries({ queryKey: ["/api/v1/expenses"] });
      await queryClient.invalidateQueries({ queryKey: [`/api/v1/expenses/${claimId}`] });
      toast.success(successMsg);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const isOwn = claim.created_by === user?.id;
  const pending = claim.status === "pending";

  return (
    <div>
      <Breadcrumbs
        items={[{ label: "Expenses", to: "/expenses" }, { label: claim.doc_number }]}
      />
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-semibold tracking-tight">{claim.doc_number}</h1>
            <ExpenseStatusBadge status={claim.status} />
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{claim.description}</p>
        </div>
        <div className="flex gap-2">
          {pending && !isOwn && (
            <Can perm="expense:approve">
              <Button
                disabled={approveMutation.isPending}
                onClick={() =>
                  void act(
                    () => approveMutation.mutateAsync({ claimId }),
                    "Claim approved and posted to the project ledger",
                  )
                }
              >
                <Check /> Approve
              </Button>
              <Button variant="outline" onClick={() => setRejecting((v) => !v)}>
                <X /> Reject
              </Button>
            </Can>
          )}
          {pending && isOwn && (
            <Button
              variant="outline"
              className="text-destructive"
              disabled={cancelMutation.isPending}
              onClick={() =>
                void act(() => cancelMutation.mutateAsync({ claimId }), "Claim cancelled")
              }
            >
              <Prohibit /> Cancel Claim
            </Button>
          )}
        </div>
      </div>

      {rejecting && pending && (
        <Card className="mb-4 border-destructive/40">
          <CardContent className="flex items-end gap-2 p-3">
            <div className="flex-1">
              <Textarea
                rows={2}
                autoFocus
                placeholder="Why is this claim being rejected?"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
              />
            </div>
            <Button
              variant="destructive"
              disabled={rejectMutation.isPending || !rejectReason.trim()}
              onClick={() =>
                void act(
                  () =>
                    rejectMutation.mutateAsync({ claimId, data: { reason: rejectReason } }),
                  "Claim rejected",
                ).then(() => setRejecting(false))
              }
            >
              Confirm Reject
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Claim Details</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <Meta label="Amount">
              <span className="text-base font-semibold tabular-nums">
                {moneyExact(claim.amount)}
              </span>
            </Meta>
            <Meta label="Category">
              <span className="capitalize">{claim.category}</span>
            </Meta>
            <Meta label="Expense date">{fmtDate(claim.expense_date)}</Meta>
            <Meta label="Project">
              <EntityLink
                to="/projects/$projectId"
                params={{ projectId: claim.project_id }}
                prefetch={() => getGetProjectQueryOptions(claim.project_id)}
              >
                {claim.project_code} · {claim.project_name}
              </EntityLink>
            </Meta>
            <Meta label="Claimant">{claim.claimant_name ?? "—"}</Meta>
            <Meta label="Receipt reference">{claim.receipt_ref ?? "—"}</Meta>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Timeline</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex items-start gap-2">
              <RadioButton className="mt-0.5 h-4 w-4 text-primary" />
              <div>
                <div className="font-medium">Submitted</div>
                <div className="text-xs text-muted-foreground">
                  {fmtDate(claim.created_at.slice(0, 10))} by {claim.claimant_name ?? "—"}
                </div>
              </div>
            </div>
            {claim.decided_at && (
              <div className="flex items-start gap-2">
                {claim.status === "approved" ? (
                  <Check className="mt-0.5 h-4 w-4 text-success" />
                ) : (
                  <X className="mt-0.5 h-4 w-4 text-destructive" />
                )}
                <div>
                  <div className="font-medium capitalize">{claim.status}</div>
                  <div className="text-xs text-muted-foreground">
                    {fmtDate(claim.decided_at.slice(0, 10))}
                    {claim.approver_name && <> by {claim.approver_name}</>}
                  </div>
                  {claim.rejection_reason && (
                    <div className="mt-1 rounded bg-destructive/10 px-2 py-1 text-xs text-destructive">
                      {claim.rejection_reason}
                    </div>
                  )}
                </div>
              </div>
            )}
            {claim.status === "approved" && claim.cost_entry_id && (
              <p className="rounded-md border bg-muted/40 p-2 text-xs text-muted-foreground">
                Posted to the project cost ledger with reference{" "}
                <span className="font-mono">{claim.doc_number}</span>, see it in the{" "}
                <EntityLink
                  to="/projects/$projectId/boq"
                  params={{ projectId: claim.project_id }}
                  className="text-xs"
                >
                  project BOQ &amp; costs
                </EntityLink>
                .
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
