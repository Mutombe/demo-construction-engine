import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { CheckCircle, HandCoins, WarningCircle } from "@phosphor-icons/react";
import { useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorState } from "@/components/ui/list-state";
import { PageSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { CommentThread } from "@/features/comments/CommentThread";
import {
  BackCharges,
  PaymentCertificate,
  Variations,
} from "@/features/subcontracts/Commercials";
import { errDetail } from "@/lib/api/errors";
import {
  useAwardSubcontract,
  useCertifyMilestone,
  useGetSubcontract,
  useRejectMilestone,
  useReleaseRetention,
  useSubmitMilestone,
} from "@/lib/api/generated/endpoints";
import type { MilestoneRead } from "@/lib/api/generated/model";
import { fmtDate, moneyExact } from "@/lib/format";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/_app/subcontracts/$subcontractId")({
  component: SubcontractDetail,
});

const STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "outline"> = {
  awarded: "success",
  draft: "outline",
  completed: "outline",
  terminated: "destructive",
};

function SubcontractDetail() {
  const { subcontractId } = Route.useParams();
  const queryClient = useQueryClient();
  const contractQuery = useGetSubcontract(subcontractId);
  const { data: contract } = contractQuery;
  const award = useAwardSubcontract();
  const submit = useSubmitMilestone();
  const certify = useCertifyMilestone();
  const reject = useRejectMilestone();

  const [rejecting, setRejecting] = useState<MilestoneRead | null>(null);
  const [reason, setReason] = useState("");
  const [releaseOpen, setReleaseOpen] = useState(false);

  if (contractQuery.isError) {
    return (
      <ErrorState
        error={contractQuery.error}
        onRetry={() => void contractQuery.refetch()}
      />
    );
  }
  if (!contract) return <PageSkeleton rows={5} />;

  const run = async (fn: () => Promise<unknown>, done: string) => {
    try {
      await fn();
      await queryClient.invalidateQueries();
      toast.success(done);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const milestones = contract.milestones ?? [];
  const certifiedCount = milestones.filter((m) => m.status === "certified").length;

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Subcontracts", to: "/subcontracts" },
          { label: contract.doc_number },
        ]}
      />

      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-semibold tracking-tight">{contract.title}</h1>
            <Badge variant={STATUS_VARIANT[contract.status] ?? "outline"}>
              {contract.status}
            </Badge>
          </div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span className="font-mono">{contract.doc_number}</span>
            <Link
              to="/procurement/suppliers/$supplierId"
              params={{ supplierId: contract.supplier_id }}
              className="hover:text-foreground hover:underline"
            >
              {contract.supplier_name}
            </Link>
            <Link
              to="/projects/$projectId"
              params={{ projectId: contract.project_id }}
              className="hover:text-foreground hover:underline"
            >
              {contract.project_name}
            </Link>
            {contract.ends_on && <span>Ends {fmtDate(contract.ends_on)}</span>}
          </div>
        </div>
        <div className="flex gap-2">
          {contract.status === "draft" && (
            <Can perm="procurement:write">
              <Button
                onClick={() => void run(() => award.mutateAsync({ subcontractId }), "Awarded")}
              >
                Award Package
              </Button>
            </Can>
          )}
          {Number(contract.retention_outstanding) > 0 && (
            <Can perm="project:write">
              <Button variant="outline" onClick={() => setReleaseOpen(true)}>
                <HandCoins /> Release Retention
              </Button>
            </Can>
          )}
        </div>
      </div>

      {contract.vendor_compliant === false && (
        <div className="mb-4 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          <WarningCircle weight="fill" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            This subcontractor's mandatory paperwork is not in date. Nothing further can be
            awarded to them until it is put right —{" "}
            <Link
              to="/procurement/suppliers/$supplierId"
              params={{ supplierId: contract.supplier_id }}
              className="underline"
            >
              see what is missing
            </Link>
            .
          </span>
        </div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Figure label="Package value" value={moneyExact(contract.value)} />
        <Figure
          label="Certified"
          value={moneyExact(contract.certified)}
          hint={`${certifiedCount} of ${milestones.length} stages`}
        />
        <Figure
          label="Retention held"
          value={moneyExact(contract.retention_outstanding)}
          hint={
            Number(contract.retention_released) > 0
              ? `${moneyExact(contract.retention_released)} released`
              : `${Number(contract.retention_pct)}% of each stage`
          }
        />
        <Figure label="Net payable" value={moneyExact(contract.net_payable)} />
        <Figure label="Left to do" value={moneyExact(contract.remaining)} />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Stages</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Stage</TableHead>
                    <TableHead>Due</TableHead>
                    <TableHead className="text-right">Priced at</TableHead>
                    <TableHead className="text-right">Certified</TableHead>
                    <TableHead className="text-right">Held</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="w-36" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {milestones.map((milestone) => (
                    <TableRow key={milestone.id}>
                      <TableCell className="font-medium">{milestone.name}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {milestone.due_date ? fmtDate(milestone.due_date) : "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {moneyExact(milestone.value)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {milestone.certified_amount ? moneyExact(milestone.certified_amount) : "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {milestone.retention_held ? moneyExact(milestone.retention_held) : "—"}
                      </TableCell>
                      <TableCell>
                        <MilestoneBadge milestone={milestone} />
                      </TableCell>
                      <TableCell className="text-right">
                        {contract.status === "awarded" && milestone.status !== "certified" && (
                          <>
                            {milestone.status !== "submitted" ? (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() =>
                                  void run(
                                    () => submit.mutateAsync({ milestoneId: milestone.id }),
                                    "Sent for certification",
                                  )
                                }
                              >
                                Claim
                              </Button>
                            ) : (
                              <Can perm="project:write">
                                <div className="flex justify-end gap-1.5">
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => {
                                      setRejecting(milestone);
                                      setReason("");
                                    }}
                                  >
                                    Reject
                                  </Button>
                                  <Button
                                    size="sm"
                                    onClick={() =>
                                      void run(
                                        () =>
                                          certify.mutateAsync({
                                            milestoneId: milestone.id,
                                            data: {},
                                          }),
                                        "Certified",
                                      )
                                    }
                                  >
                                    Certify
                                  </Button>
                                </div>
                              </Can>
                            )}
                          </>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {rejecting && (
            <Card>
              <CardContent className="space-y-2 pt-4">
                <Label htmlFor="reject-reason">Why {rejecting.name} is going back</Label>
                <Textarea
                  id="reject-reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="What has to be put right before this stage can be signed off"
                />
                <div className="flex justify-end gap-2">
                  <Button variant="outline" size="sm" onClick={() => setRejecting(null)}>
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    disabled={!reason.trim()}
                    onClick={() =>
                      void run(async () => {
                        await reject.mutateAsync({
                          milestoneId: rejecting.id,
                          data: { reason },
                        });
                        setRejecting(null);
                      }, "Sent back")
                    }
                  >
                    Send Back
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          <Variations subcontractId={subcontractId} />

          <BackCharges subcontractId={subcontractId} />

          {contract.scope && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Scope</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="whitespace-pre-wrap text-sm">{contract.scope}</p>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Discussion</CardTitle>
            </CardHeader>
            <CardContent>
              <CommentThread entityType="subcontract" entityId={subcontractId} />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <PaymentCertificate subcontractId={subcontractId} />

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Retention</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-baseline justify-between">
                <span className="text-muted-foreground">Withheld to date</span>
                <span className="font-medium tabular-nums">
                  {moneyExact(contract.retention_held)}
                </span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-muted-foreground">Released</span>
                <span className="font-medium tabular-nums">
                  {moneyExact(contract.retention_released)}
                </span>
              </div>
              <div className="flex items-baseline justify-between border-t pt-2">
                <span className="text-muted-foreground">Still held</span>
                <span className="font-semibold tabular-nums">
                  {moneyExact(contract.retention_outstanding)}
                </span>
              </div>

              {(contract.releases ?? []).length > 0 ? (
                <div className="space-y-1.5 border-t pt-2">
                  {(contract.releases ?? []).map((release) => (
                    <div key={release.id} className="text-xs">
                      <div className="flex justify-between gap-2">
                        <span>{fmtDate(release.released_on)}</span>
                        <span className="tabular-nums">{moneyExact(release.amount)}</span>
                      </div>
                      {release.reason && (
                        <div className="text-muted-foreground">{release.reason}</div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="border-t pt-2 text-xs text-muted-foreground">
                  Nothing released yet. This is the subcontractor's money being held, not ours.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Terms</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row label="Retention" value={`${Number(contract.retention_pct)}%`} />
              <Row
                label="Starts"
                value={contract.starts_on ? fmtDate(contract.starts_on) : "Not set"}
              />
              <Row
                label="Ends"
                value={contract.ends_on ? fmtDate(contract.ends_on) : "Not set"}
              />
              <Row
                label="Awarded"
                value={
                  contract.awarded_at
                    ? fmtDate(contract.awarded_at.slice(0, 10))
                    : "Not yet awarded"
                }
              />
              <div className="flex items-start gap-2 border-t pt-2">
                {contract.vendor_compliant ? (
                  <>
                    <CheckCircle weight="fill" className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                    <span className="text-xs text-muted-foreground">
                      Vendor paperwork in date.
                    </span>
                  </>
                ) : (
                  <>
                    <WarningCircle
                      weight="fill"
                      className="mt-0.5 h-4 w-4 shrink-0 text-destructive"
                    />
                    <span className="text-xs text-destructive">Vendor paperwork has lapsed.</span>
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      <ReleaseDialog
        subcontractId={subcontractId}
        outstanding={String(contract.retention_outstanding)}
        open={releaseOpen}
        onOpenChange={setReleaseOpen}
      />
    </div>
  );
}

function ReleaseDialog({
  subcontractId,
  outstanding,
  open,
  onOpenChange,
}: {
  subcontractId: string;
  outstanding: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const release = useReleaseRetention();
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");

  const submit = async () => {
    try {
      await release.mutateAsync({
        subcontractId,
        data: { amount: amount || null, reason: reason || null },
      });
      await queryClient.invalidateQueries();
      setAmount("");
      setReason("");
      onOpenChange(false);
      toast.success("Retention released");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Release retention</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="release-amount">Amount</Label>
            <Input
              id="release-amount"
              inputMode="decimal"
              placeholder={`All of it — ${moneyExact(outstanding)}`}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Leave blank to release everything still held. Retention usually goes back in two
              parts, so a partial release is normal.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="release-reason">Reason</Label>
            <Input
              id="release-reason"
              placeholder="Practical completion"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
          <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
            This moves money the subcontractor is owed out of retention and into payables. It is
            not a cost — that was taken when the stage was certified — so the job's figures do not
            move.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={release.isPending} onClick={() => void submit()}>
            Release
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function MilestoneBadge({ milestone }: { milestone: MilestoneRead }) {
  switch (milestone.status) {
    case "certified":
      return <Badge variant="success">Certified {fmtDate(milestone.certified_on ?? null)}</Badge>;
    case "submitted":
      return <Badge variant="warning">Awaiting sign-off</Badge>;
    case "rejected":
      return <Badge variant="destructive">Sent back</Badge>;
    default:
      return <Badge variant="outline">Not started</Badge>;
  }
}

function Figure({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-md border p-3">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-lg font-semibold tabular-nums">{value}</div>
      {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className="truncate text-right font-medium">{value}</span>
    </div>
  );
}
