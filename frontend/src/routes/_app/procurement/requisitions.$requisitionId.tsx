import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { FileText, Prohibit, ShoppingCart, Warning } from "@phosphor-icons/react";
import { useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { confirmDialog } from "@/components/ui/confirm";
import { EntityLink } from "@/components/ui/linked-row";
import { DetailSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ConvertToPoDialog } from "@/features/requisitions/ConvertToPoDialog";
import { errDetail } from "@/lib/api/errors";
import {
  getGetProjectQueryOptions,
  getGetPurchaseOrderQueryOptions,
  getGetRequisitionQueryOptions,
  getGetRfqQueryOptions,
  useCancelRequisition,
  useConvertRequisitionToRfq,
  useGetRequisition,
} from "@/lib/api/generated/endpoints";
import { fmtDate } from "@/lib/format";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/procurement/requisitions/$requisitionId")({
  component: RequisitionDetailPage,
  loader: ({ context: { queryClient }, params }) =>
    queryClient.ensureQueryData(getGetRequisitionQueryOptions(params.requisitionId)),
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

function RequisitionDetailPage() {
  const { requisitionId } = Route.useParams();
  const navigate = Route.useNavigate();
  const queryClient = useQueryClient();
  const { data: requisition } = useGetRequisition(requisitionId);
  const toRfq = useConvertRequisitionToRfq();
  const cancelMutation = useCancelRequisition();
  const [converting, setConverting] = useState(false);

  if (!requisition) return <DetailSkeleton />;

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["/api/v1/requisitions"] }),
      queryClient.invalidateQueries({ queryKey: ["/api/v1/dashboard"] }),
    ]);

  const convertToRfq = async () => {
    if (
      !(await confirmDialog({
        title: "Convert to RFQ",
        message: `Draft an RFQ from ${requisition.doc_number} with its ${requisition.item_count} line(s)?`,
      }))
    )
      return;
    try {
      const rfq = await toRfq.mutateAsync({ requisitionId });
      await refresh();
      toast.success(`${rfq.doc_number} drafted`);
      void navigate({ to: "/procurement/rfqs/$rfqId", params: { rfqId: rfq.id } });
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const cancel = async () => {
    if (
      !(await confirmDialog({
        title: "Cancel request",
        message: `Cancel ${requisition.doc_number}? Site will see it is no longer being actioned.`,
        tone: "danger",
      }))
    )
      return;
    try {
      await cancelMutation.mutateAsync({ requisitionId });
      await refresh();
      toast.success("Request cancelled");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const open = requisition.status === "open";
  const age = requisition.age_days ?? 0;

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Procurement", to: "/procurement" },
          { label: "Material Requests", to: "/procurement/requisitions" },
          { label: requisition.doc_number },
        ]}
      />

      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-semibold tracking-tight">
              {requisition.doc_number}
            </h1>
            <Badge
              variant={
                open ? (requisition.is_urgent ? "destructive" : "warning") : "outline"
              }
            >
              {requisition.status}
            </Badge>
            {open && requisition.is_urgent && (
              <span className="flex items-center gap-1 text-xs font-medium text-destructive">
                <Warning className="size-3.5" />
                waiting {age} day{age === 1 ? "" : "s"}
              </span>
            )}
          </div>
          <div className="mt-1 text-sm text-muted-foreground">
            Raised by {requisition.requested_by_name ?? "—"} on{" "}
            {fmtDate(requisition.created_at)}
          </div>
        </div>

        {open && (
          <div className="flex gap-2">
            <Can perm="requisition:action">
              <Button
                variant="outline"
                title="Draft an RFQ from this request"
                onClick={() => void convertToRfq()}
              >
                <FileText /> To RFQ
              </Button>
            </Can>
            <Can perm="requisition:create">
              <Button
                variant="ghost"
                size="icon"
                className="text-destructive"
                title="Cancel this request"
                onClick={() => void cancel()}
              >
                <Prohibit />
              </Button>
            </Can>
          </div>
        )}
      </div>

      <Card className="mb-4">
        <CardContent className="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-4">
          <Meta label="Project">
            <EntityLink
              to="/projects/$projectId"
              params={{ projectId: requisition.project_id }}
              prefetch={() => getGetProjectQueryOptions(requisition.project_id)}
            >
              {requisition.project_name ?? "—"}
            </EntityLink>
          </Meta>
          <Meta label="Needed by">
            {requisition.needed_by ? fmtDate(requisition.needed_by) : "not specified"}
          </Meta>
          <Meta label="Waiting">
            <span className={cn(open && requisition.is_urgent && "text-destructive")}>
              {open ? `${age} day${age === 1 ? "" : "s"}` : "actioned"}
            </span>
          </Meta>
          <Meta label="Became">
            {/* The whole point of the request is what it turned into */}
            {requisition.rfq_id ? (
              <EntityLink
                to="/procurement/rfqs/$rfqId"
                params={{ rfqId: requisition.rfq_id }}
                prefetch={() => getGetRfqQueryOptions(requisition.rfq_id as string)}
              >
                View the RFQ
              </EntityLink>
            ) : requisition.po_id ? (
              <EntityLink
                to="/procurement/pos/$poId"
                params={{ poId: requisition.po_id }}
                prefetch={() =>
                  getGetPurchaseOrderQueryOptions(requisition.po_id as string)
                }
              >
                View the purchase order
              </EntityLink>
            ) : (
              <span className="text-muted-foreground">nothing yet</span>
            )}
          </Meta>
          {requisition.notes && (
            <div className="sm:col-span-2 xl:col-span-4">
              <Meta label="Notes">{requisition.notes}</Meta>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle>Requested Items</CardTitle>
          {open && (
            <Can perm="requisition:action">
              <Button
                size="sm"
                title="Draft a purchase order from this request"
                onClick={() => setConverting(true)}
              >
                <ShoppingCart /> To Purchase Order
              </Button>
            </Can>
          )}
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Description</TableHead>
                <TableHead>Unit</TableHead>
                <TableHead className="text-right">Quantity</TableHead>
                <TableHead>BOQ Line</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(requisition.items ?? []).map((line) => (
                <TableRow key={line.id}>
                  <TableCell className="font-medium">{line.description}</TableCell>
                  <TableCell className="text-muted-foreground">{line.unit}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {Number(line.quantity).toLocaleString()}
                  </TableCell>
                  <TableCell>
                    {line.boq_item_id ? (
                      <EntityLink
                        to="/projects/$projectId/boq"
                        params={{ projectId: requisition.project_id }}
                      >
                        Linked to BOQ
                      </EntityLink>
                    ) : (
                      <span className="text-xs text-muted-foreground">
                        not linked, priced by hand
                      </span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <ConvertToPoDialog
        requisition={converting ? requisition : null}
        onOpenChange={(open) => setConverting(open)}
        onDone={async (poId) => {
          setConverting(false);
          await refresh();
          void navigate({ to: "/procurement/pos/$poId", params: { poId } });
        }}
      />
    </div>
  );
}
