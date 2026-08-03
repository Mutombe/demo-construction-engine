import { useQueryClient } from "@tanstack/react-query";
import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import {
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Download,
  RefreshCcw,
  Trash2,
} from "lucide-react";
import { Fragment, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { PageSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { downloadFile } from "@/lib/api/download";
import {
  useApprovePayRun,
  useDeletePayRun,
  useGetPayRun,
  useRegeneratePayRun,
} from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";

export const Route = createFileRoute("/_app/payroll/runs/$runId")({
  component: PayRunDetailPage,
});

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

function PayRunDetailPage() {
  const { runId } = Route.useParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { data: run, isLoading } = useGetPayRun(runId);
  const approveMutation = useApprovePayRun();
  const regenerateMutation = useRegeneratePayRun();
  const deleteMutation = useDeletePayRun();
  const [expanded, setExpanded] = useState<string | null>(null);

  if (isLoading || !run) {
    return <PageSkeleton rows={6} />;
  }
  const isDraft = run.status === "draft";

  const approve = async () => {
    if (
      !window.confirm(
        `Approve ${run.doc_number}? This posts labour costs of ` +
          `${moneyExact(run.gross_total)} to the project ledgers and locks the timesheets.`,
      )
    )
      return;
    try {
      await approveMutation.mutateAsync({ payRunId: runId });
      await queryClient.invalidateQueries();
      toast.success("Pay run approved — labour costs posted");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const regenerate = async () => {
    try {
      await regenerateMutation.mutateAsync({ payRunId: runId });
      await queryClient.invalidateQueries();
      toast.success("Draft rebuilt from current timesheets");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const remove = async () => {
    if (!window.confirm(`Delete draft ${run.doc_number}?`)) return;
    try {
      await deleteMutation.mutateAsync({ payRunId: runId });
      await queryClient.invalidateQueries();
      toast.success("Draft deleted");
      await navigate({ to: "/payroll" });
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <div>
      <Link
        to="/payroll"
        className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> Payroll
      </Link>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-semibold tracking-tight">{run.doc_number}</h1>
            {run.status === "approved" ? (
              <Badge variant="success">Approved</Badge>
            ) : (
              <Badge variant="secondary">Draft</Badge>
            )}
          </div>
          <div className="mt-1 text-sm text-muted-foreground">
            {fmtDate(run.period_start)} → {fmtDate(run.period_end)} · {run.line_count} worker
            {run.line_count === 1 ? "" : "s"}
            {run.approved_at && <> · approved {fmtDate(run.approved_at.slice(0, 10))}</>}
          </div>
        </div>
        <div className="flex gap-2">
          {isDraft ? (
            <>
              <Button
                variant="outline"
                disabled={regenerateMutation.isPending}
                onClick={() => void regenerate()}
              >
                <RefreshCcw /> Regenerate
              </Button>
              <Button
                variant="outline"
                className="text-destructive"
                disabled={deleteMutation.isPending}
                onClick={() => void remove()}
              >
                <Trash2 /> Delete
              </Button>
              <Button disabled={approveMutation.isPending} onClick={() => void approve()}>
                <CheckCircle2 /> Approve &amp; post costs
              </Button>
            </>
          ) : (
            <Button
              variant="outline"
              onClick={() =>
                void downloadFile(
                  `/api/v1/pay-runs/${runId}/payslips`,
                  `${run.doc_number}_payslips.pdf`,
                ).catch(() => toast.error("Download failed"))
              }
            >
              <Download /> All payslips (PDF)
            </Button>
          )}
        </div>
      </div>

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Base + overtime" value={moneyExact(Number(run.base_total) + Number(run.overtime_total))} sub={`${moneyExact(run.overtime_total)} overtime`} />
        <StatCard label="Allowances" value={moneyExact(run.allowance_total)} />
        <StatCard label="Gross employer cost" value={moneyExact(run.gross_total)} tone="brand" sub="posted to project ledgers" />
        <StatCard label="Net payable" value={moneyExact(run.net_total)} sub={`${moneyExact(run.deduction_total)} deductions`} />
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Worker</TableHead>
                <TableHead>Basis</TableHead>
                <TableHead className="text-right">Qty</TableHead>
                <TableHead className="text-right">Base</TableHead>
                <TableHead className="text-right">OT</TableHead>
                <TableHead className="text-right">Allow.</TableHead>
                <TableHead className="text-right">Deduct.</TableHead>
                <TableHead className="text-right">Gross</TableHead>
                <TableHead className="text-right">Net</TableHead>
                {!isDraft && <TableHead className="w-12" />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {(run.lines ?? []).map((line) => {
                const open = expanded === line.id;
                return (
                  <Fragment key={line.id}>
                    <TableRow
                      className="cursor-pointer transition-colors"
                      onClick={() => setExpanded(open ? null : line.id)}
                    >
                      <TableCell className="text-muted-foreground">
                        {open ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="font-medium">{line.worker_name}</div>
                        <div className="text-xs text-muted-foreground">{line.trade}</div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {line.pay_basis === "hourly" ? "hrs" : "days"} @ {moneyExact(line.rate)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {Number(line.quantity)}
                        {Number(line.overtime_quantity) > 0 && (
                          <span className="text-xs text-muted-foreground">
                            {" "}
                            +{Number(line.overtime_quantity)} OT
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {moneyExact(line.base_pay)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {Number(line.overtime_pay) ? moneyExact(line.overtime_pay) : "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {Number(line.allowance_total) ? moneyExact(line.allowance_total) : "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {Number(line.deduction_total) ? moneyExact(line.deduction_total) : "—"}
                      </TableCell>
                      <TableCell className="text-right font-medium tabular-nums">
                        {moneyExact(line.gross_pay)}
                      </TableCell>
                      <TableCell className="text-right font-semibold tabular-nums">
                        {moneyExact(line.net_pay)}
                      </TableCell>
                      {!isDraft && (
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Payslip PDF"
                            onClick={(e) => {
                              e.stopPropagation();
                              void downloadFile(
                                `/api/v1/pay-runs/${runId}/lines/${line.id}/payslip`,
                                `payslip.pdf`,
                              ).catch(() => toast.error("Download failed"));
                            }}
                          >
                            <Download />
                          </Button>
                        </TableCell>
                      )}
                    </TableRow>
                    {open && (
                      <TableRow className="bg-muted/30 hover:bg-muted/30">
                        <TableCell />
                        <TableCell colSpan={isDraft ? 9 : 10} className="py-2">
                          <div className="flex flex-wrap gap-x-8 gap-y-1 text-xs">
                            <div>
                              <span className="font-medium uppercase text-muted-foreground">
                                Cost allocation:
                              </span>{" "}
                              {(line.project_allocation ?? []).map((a) => (
                                <span key={a.project_id} className="mr-3 tabular-nums">
                                  <span className="font-mono">{a.project_code}</span>{" "}
                                  {moneyExact(a.amount)}
                                </span>
                              ))}
                            </div>
                            {(line.pay_items ?? []).length > 0 && (
                              <div>
                                <span className="font-medium uppercase text-muted-foreground">
                                  Items:
                                </span>{" "}
                                {(line.pay_items ?? []).map((item, i) => (
                                  <span key={i} className="mr-3">
                                    {item.label} {item.kind === "deduction" ? "−" : "+"}
                                    {moneyExact(item.amount)}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
