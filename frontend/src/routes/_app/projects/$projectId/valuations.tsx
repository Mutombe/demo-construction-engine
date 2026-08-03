import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Ban, CheckCircle2, Download, Pencil, Plus, Ruler, Send, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ClickableRow, RowActions } from "@/components/ui/linked-row";
import { StatRowSkeleton, TableSkeleton } from "@/components/ui/skeleton";
import { downloadFile } from "@/lib/api/download";
import { MeasurementSheetDialog } from "@/features/valuations/MeasurementSheetDialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ValuationFormDialog } from "@/features/valuations/ValuationFormDialog";
import { ValuationStatusBadge } from "@/features/valuations/StatusBadge";
import {
  getGetValuationQueryOptions,
  useCancelValuation,
  useDeleteValuation,
  useGetProject,
  useGetRevenueSummary,
  useIssueValuation,
  useListValuations,
  usePayValuation,
} from "@/lib/api/generated/endpoints";
import type { ValuationRead } from "@/lib/api/generated/model";
import { optimistic, patchRow, removeRow } from "@/lib/api/optimistic";
import { fmtDate, money, moneyExact } from "@/lib/format";

export const Route = createFileRoute("/_app/projects/$projectId/valuations")({
  component: ValuationsTab,
});

function SummaryCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
        <div className="mt-1 text-lg font-semibold tabular-nums">{value}</div>
        {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
      </CardContent>
    </Card>
  );
}

function ValuationsTab() {
  const { projectId } = Route.useParams();
  const queryClient = useQueryClient();
  const { data: project } = useGetProject(projectId);
  const { data: summary } = useGetRevenueSummary(projectId);
  const { data: valuations, isLoading: valuationsLoading } = useListValuations(projectId, {
    page_size: 50,
  });

  const listPrefix = `/api/v1/projects/${projectId}/valuations`;
  const statusOptions = (status: string, successToast: string) =>
    optimistic(queryClient, {
      prefixes: [listPrefix],
      invalidate: ["/api/v1/projects", "/api/v1/valuations"],
      successToast,
      apply: (old, vars: { valuationId: string }) =>
        patchRow(vars.valuationId, { status })(old),
    });
  // Status transitions apply in place instantly; rollback + toast on failure.
  const issueMutation = useIssueValuation({
    mutation: statusOptions("issued", "Valuation issued"),
  });
  const payMutation = usePayValuation({
    mutation: statusOptions("paid", "Payment recorded"),
  });
  const cancelMutation = useCancelValuation({
    mutation: statusOptions("cancelled", "Valuation cancelled"),
  });
  const deleteMutation = useDeleteValuation({
    mutation: optimistic(queryClient, {
      prefixes: [listPrefix],
      invalidate: ["/api/v1/projects", "/api/v1/valuations"],
      successToast: "Draft deleted",
      apply: (old, vars: { valuationId: string }) => removeRow(vars.valuationId)(old),
    }),
  });

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<ValuationRead | undefined>(undefined);
  const [measuring, setMeasuring] = useState<ValuationRead | null>(null);

  // Success/error toasts + rollback live in the mutation options now; the
  // legacy third argument is accepted and ignored.
  const act = (fn: () => Promise<unknown>, confirmMsg: string, _successMsg?: string) => {
    if (!window.confirm(confirmMsg)) return;
    void fn().catch(() => undefined);
  };

  const items = valuations?.items ?? [];
  const hasDraft = items.some((v) => v.status === "draft");

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="grid flex-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {!summary ? (
            <StatRowSkeleton count={4} />
          ) : (
            <>
              <SummaryCard
                label="Certified gross"
                value={money(summary.certified_gross)}
                sub={`of ${money(summary.contract_value)} contract`}
              />
              <SummaryCard
                label="Invoiced to date"
                value={money(summary.invoiced_to_date)}
                sub={`${summary.valuation_count ?? 0} valuation${(summary.valuation_count ?? 0) === 1 ? "" : "s"}`}
              />
              <SummaryCard
                label="Retention held"
                value={money(summary.retention_held)}
                sub={summary.retention_pct ? `${Number(summary.retention_pct)}% retention` : "no retention"}
              />
              <SummaryCard
                label="Outstanding"
                value={money(summary.outstanding)}
                sub={`${money(summary.paid_to_date)} paid`}
              />
            </>
          )}
        </div>
        <Can perm="valuation:write">
          <Button
            disabled={hasDraft}
            title={hasDraft ? "Issue or delete the existing draft first" : undefined}
            onClick={() => {
              setEditing(undefined);
              setFormOpen(true);
            }}
          >
            <Plus /> New valuation
          </Button>
        </Can>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>No.</TableHead>
                <TableHead>Document</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Period end</TableHead>
                <TableHead className="text-right">Gross</TableHead>
                <TableHead className="text-right">Retention</TableHead>
                <TableHead className="text-right">Previous</TableHead>
                <TableHead className="text-right">Net certified</TableHead>
                <TableHead>Issued / paid</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {valuationsLoading && !valuations && <TableSkeleton columns={10} rows={5} />}
              {!valuationsLoading && items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={10} className="py-10 text-center text-muted-foreground">
                    No valuations yet — create the first progress valuation to invoice the client.
                  </TableCell>
                </TableRow>
              )}
              {items.map((v) => (
                <ClickableRow
                  key={v.id}
                  to="/valuations/$valuationId"
                  params={{ valuationId: v.id }}
                  prefetch={() => getGetValuationQueryOptions(v.id)}
                >
                  <TableCell className="font-medium">V{v.valuation_number}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {v.doc_number}
                    {v.is_measured && (
                      <Badge variant="outline" className="ml-1.5 px-1.5 text-[10px]">
                        measured
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <ValuationStatusBadge status={v.status} />
                  </TableCell>
                  <TableCell>{fmtDate(v.period_end)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {moneyExact(v.gross_valuation)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {moneyExact(v.retention_amount)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {moneyExact(v.previous_certified)}
                  </TableCell>
                  <TableCell className="text-right font-semibold tabular-nums">
                    {moneyExact(v.net_certified)}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {v.issued_date && <>issued {fmtDate(v.issued_date)}</>}
                    {v.paid_date && <> · paid {fmtDate(v.paid_date)}</>}
                    {!v.issued_date && !v.paid_date && "—"}
                  </TableCell>
                  <RowActions>
                    <Can perm="valuation:write">
                      <div className="flex justify-end gap-1">
                        {v.status === "draft" && (
                          <>
                            <Button
                              variant="ghost"
                              size="icon"
                              title="Measurement sheet"
                              onClick={() => setMeasuring(v)}
                            >
                              <Ruler />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              title="Edit draft"
                              onClick={() => {
                                setEditing(v);
                                setFormOpen(true);
                              }}
                            >
                              <Pencil />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              title="Issue to client"
                              disabled={issueMutation.isPending}
                              onClick={() =>
                                void act(
                                  () =>
                                    issueMutation.mutateAsync({ valuationId: v.id, data: {} }),
                                  `Issue ${v.doc_number} to the client for ${moneyExact(v.net_certified)} net?`,
                                  "Valuation issued",
                                )
                              }
                            >
                              <Send />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="text-destructive"
                              title="Delete draft"
                              disabled={deleteMutation.isPending}
                              onClick={() =>
                                void act(
                                  () => deleteMutation.mutateAsync({ valuationId: v.id }),
                                  `Delete draft ${v.doc_number}?`,
                                  "Draft deleted",
                                )
                              }
                            >
                              <Trash2 />
                            </Button>
                          </>
                        )}
                        {(v.status === "issued" || v.status === "paid") && (
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Certificate PDF"
                            onClick={() =>
                              void downloadFile(
                                `/api/v1/valuations/${v.id}/certificate`,
                                `${v.doc_number}_certificate.pdf`,
                              ).catch(() => toast.error("Download failed"))
                            }
                          >
                            <Download />
                          </Button>
                        )}
                        {v.status === "issued" && (
                          <>
                            <Button
                              variant="ghost"
                              size="icon"
                              title="Mark paid"
                              disabled={payMutation.isPending}
                              onClick={() =>
                                void act(
                                  () => payMutation.mutateAsync({ valuationId: v.id, data: {} }),
                                  `Record full payment of ${moneyExact(v.net_certified)} for ${v.doc_number}?`,
                                  "Payment recorded",
                                )
                              }
                            >
                              <CheckCircle2 />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="text-destructive"
                              title="Cancel valuation"
                              disabled={cancelMutation.isPending}
                              onClick={() =>
                                void act(
                                  () => cancelMutation.mutateAsync({ valuationId: v.id }),
                                  `Cancel ${v.doc_number}? Only the latest certificate can be cancelled.`,
                                  "Valuation cancelled",
                                )
                              }
                            >
                              <Ban />
                            </Button>
                          </>
                        )}
                      </div>
                    </Can>
                  </RowActions>
                </ClickableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <ValuationFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        projectId={projectId}
        summary={summary}
        retentionPct={project?.retention_pct}
        valuation={editing}
      />
      <MeasurementSheetDialog
        valuationId={measuring?.id ?? null}
        onOpenChange={(open) => {
          if (!open) setMeasuring(null);
        }}
        retentionPct={project?.retention_pct}
        previousCertified={measuring?.previous_certified}
      />
    </div>
  );
}
