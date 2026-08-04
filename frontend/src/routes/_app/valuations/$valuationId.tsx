import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { CheckCircle, DownloadSimple, PaperPlaneTilt, Prohibit } from "@phosphor-icons/react";
import { toast } from "@/lib/toast";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { confirmDialog } from "@/components/ui/confirm";
import { EntityLink } from "@/components/ui/linked-row";
import { DetailSkeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/ui/stat-card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ValuationStatusBadge } from "@/features/valuations/StatusBadge";
import { downloadFile } from "@/lib/api/download";
import { errDetail } from "@/lib/api/errors";
import {
  getGetProjectQueryOptions,
  getGetValuationQueryOptions,
  useCancelValuation,
  useGetValuation,
  useIssueValuation,
  usePayValuation,
} from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";

export const Route = createFileRoute("/_app/valuations/$valuationId")({
  component: ValuationDetailPage,
  loader: ({ context: { queryClient }, params }) =>
    queryClient.ensureQueryData(getGetValuationQueryOptions(params.valuationId)),
});

function ValuationDetailPage() {
  const { valuationId } = Route.useParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { data: valuation } = useGetValuation(valuationId);
  const issueMutation = useIssueValuation();
  const payMutation = usePayValuation();
  const cancelMutation = useCancelValuation();

  if (!valuation) {
    return <DetailSkeleton />;
  }

  const act = async (
    fn: () => Promise<unknown>,
    confirmTitle: string,
    confirmMsg: string,
    successMsg: string,
    tone: "default" | "danger" = "default",
  ) => {
    if (!(await confirmDialog({ title: confirmTitle, message: confirmMsg, tone }))) return;
    try {
      await fn();
      await queryClient.invalidateQueries({ queryKey: ["/api/v1/valuations"] });
      await queryClient.invalidateQueries({ queryKey: ["/api/v1/projects"] });
      toast.success(successMsg);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const certified = valuation.status === "issued" || valuation.status === "paid";

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Projects", to: "/projects" },
          {
            label: valuation.project_code ?? "Project",
            to: "/projects/$projectId/valuations",
            params: { projectId: valuation.project_id },
          },
          { label: valuation.doc_number },
        ]}
      />
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-semibold tracking-tight">
              Valuation {valuation.valuation_number}
            </h1>
            <ValuationStatusBadge status={valuation.status} />
            {valuation.is_measured && <Badge variant="outline">Measured</Badge>}
          </div>
          <div className="mt-1 text-sm text-muted-foreground">
            <span className="font-mono text-xs">{valuation.doc_number}</span> ·{" "}
            <EntityLink
              to="/projects/$projectId/valuations"
              params={{ projectId: valuation.project_id }}
              prefetch={() => getGetProjectQueryOptions(valuation.project_id)}
              className="text-sm"
            >
              {valuation.project_code} · {valuation.project_name}
            </EntityLink>{" "}
            · period to {fmtDate(valuation.period_end)}
            {valuation.issued_date && <> · issued {fmtDate(valuation.issued_date)}</>}
            {valuation.paid_date && <> · paid {fmtDate(valuation.paid_date)}</>}
          </div>
        </div>
        <div className="flex gap-2">
          {certified && (
            <Button
              variant="outline"
              onClick={() =>
                void downloadFile(
                  `/api/v1/valuations/${valuationId}/certificate`,
                  `${valuation.doc_number}_certificate.pdf`,
                ).catch(() => toast.error("Download failed"))
              }
            >
              <DownloadSimple /> Certificate
            </Button>
          )}
          <Can perm="valuation:write">
            {valuation.status === "draft" && (
              <Button
                disabled={issueMutation.isPending}
                onClick={() =>
                  void act(
                    () => issueMutation.mutateAsync({ valuationId, data: {} }),
                    "Issue valuation",
                    `Issue ${valuation.doc_number} to the client for ${moneyExact(valuation.net_certified)} net?`,
                    "Valuation issued",
                  )
                }
              >
                <PaperPlaneTilt /> Issue
              </Button>
            )}
            {valuation.status === "issued" && (
              <>
                <Button
                  disabled={payMutation.isPending}
                  onClick={() =>
                    void act(
                      () => payMutation.mutateAsync({ valuationId, data: {} }),
                      "Record payment",
                      `Record full payment of ${moneyExact(valuation.net_certified)}?`,
                      "Payment recorded",
                    )
                  }
                >
                  <CheckCircle /> Mark Paid
                </Button>
                <Button
                  variant="outline"
                  className="text-destructive"
                  disabled={cancelMutation.isPending}
                  onClick={() =>
                    void act(
                      () => cancelMutation.mutateAsync({ valuationId }),
                      "Cancel valuation",
                      `Cancel ${valuation.doc_number}? Only the latest certificate can be cancelled.`,
                      "Valuation cancelled",
                      "danger",
                    ).then(() =>
                      navigate({
                        to: "/projects/$projectId/valuations",
                        params: { projectId: valuation.project_id },
                      }),
                    )
                  }
                >
                  <Prohibit /> Cancel
                </Button>
              </>
            )}
          </Can>
        </div>
      </div>

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Gross to date" value={moneyExact(valuation.gross_valuation)} />
        <StatCard label="Retention" value={`− ${moneyExact(valuation.retention_amount)}`} />
        <StatCard
          label="Previously certified"
          value={`− ${moneyExact(valuation.previous_certified)}`}
        />
        <StatCard
          label="Net this valuation"
          value={moneyExact(valuation.net_certified)}
          tone="brand"
        />
      </div>

      {(valuation.lines ?? []).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Measurement Sheet</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Item</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Unit</TableHead>
                  <TableHead className="text-right">BOQ Qty</TableHead>
                  <TableHead className="text-right">Qty to Date</TableHead>
                  <TableHead className="text-right">Rate</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(valuation.lines ?? []).map((line) => (
                  <TableRow key={line.id}>
                    <TableCell className="font-mono text-xs">
                      {valuation.project_id ? (
                        <EntityLink
                          to="/projects/$projectId/boq"
                          params={{ projectId: valuation.project_id }}
                          title="Open this line in the bill of quantities"
                        >
                          {line.item_code}
                        </EntityLink>
                      ) : (
                        line.item_code
                      )}
                    </TableCell>
                    <TableCell className="max-w-72 truncate" title={line.description}>
                      {line.description}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{line.unit}</TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {Number(line.boq_quantity).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {Number(line.qty_to_date).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {moneyExact(line.rate)}
                    </TableCell>
                    <TableCell className="text-right font-medium tabular-nums">
                      {moneyExact(line.amount)}
                    </TableCell>
                  </TableRow>
                ))}
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="text-right font-semibold uppercase text-muted-foreground"
                  >
                    Gross total
                  </TableCell>
                  <TableCell className="text-right text-base font-bold tabular-nums">
                    {moneyExact(valuation.gross_valuation)}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {valuation.notes && (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle>Notes</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="whitespace-pre-wrap text-sm text-muted-foreground">
              {valuation.notes}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
