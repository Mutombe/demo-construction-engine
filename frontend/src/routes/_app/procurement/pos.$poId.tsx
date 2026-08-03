import { useQueryClient } from "@tanstack/react-query";
import { Link, createFileRoute } from "@tanstack/react-router";
import { Ban, Download, PackageCheck, Send } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EntityLink } from "@/components/ui/linked-row";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PageSkeleton } from "@/components/ui/skeleton";
import { ReceivePoDialog } from "@/features/procurement/ReceivePoDialog";
import { downloadFile } from "@/lib/api/download";
import { PoStatusBadge } from "@/features/procurement/StatusBadges";
import {
  getGetPurchaseOrderQueryOptions,
  getGetSupplierActivityQueryOptions,
  useCancelPurchaseOrder,
  useGetPurchaseOrder,
  useIssuePurchaseOrder,
} from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";

export const Route = createFileRoute("/_app/procurement/pos/$poId")({
  component: PoDetailPage,
  loader: ({ context: { queryClient }, params }) =>
    queryClient.ensureQueryData(getGetPurchaseOrderQueryOptions(params.poId)),
});

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

function PoDetailPage() {
  const { poId } = Route.useParams();
  const queryClient = useQueryClient();
  const { data: po } = useGetPurchaseOrder(poId);
  const issueMutation = useIssuePurchaseOrder();
  const cancelMutation = useCancelPurchaseOrder();
  const [receiveOpen, setReceiveOpen] = useState(false);

  if (!po) {
    return <PageSkeleton rows={5} />;
  }
  const items = po.items ?? [];

  const act = async (
    fn: () => Promise<unknown>,
    confirmMsg: string,
    successMsg: string,
  ) => {
    if (!window.confirm(confirmMsg)) return;
    try {
      await fn();
      await queryClient.invalidateQueries();
      toast.success(successMsg);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <div>
      <Breadcrumbs
        items={[{ label: "Procurement", to: "/procurement" }, { label: po.doc_number }]}
      />
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-semibold tracking-tight">{po.doc_number}</h1>
            <PoStatusBadge status={po.status ?? "draft"} />
            {po.received_to && (
              <Badge variant="outline">
                {po.received_to === "store" ? "→ Store" : "→ Project"}
              </Badge>
            )}
            {po.ai_generated && <Badge variant="secondary">AI terms</Badge>}
          </div>
          <div className="mt-1 text-sm text-muted-foreground">
            <EntityLink
              to="/procurement/suppliers/$supplierId"
              params={{ supplierId: po.supplier_id }}
              prefetch={() => getGetSupplierActivityQueryOptions(po.supplier_id)}
              className="text-sm font-normal"
            >
              {po.supplier_name}
            </EntityLink>{" "}
            ·{" "}
            <EntityLink
              to="/projects/$projectId"
              params={{ projectId: po.project_id }}
              className="text-sm font-normal"
            >
              {po.project_code} {po.project_name}
            </EntityLink>{" "}
            · ordered {fmtDate(po.order_date)}
            {po.expected_delivery && <> · expected {fmtDate(po.expected_delivery)}</>}
            {po.received_date && <> · received {fmtDate(po.received_date)}</>}
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() =>
              void downloadFile(`/api/v1/purchase-orders/${poId}/pdf`, `${po.doc_number}.pdf`).catch(
                () => toast.error("Download failed"),
              )
            }
          >
            <Download /> PDF
          </Button>
          {po.status === "draft" && (
            <Can perm="po:approve">
              <Button
                disabled={issueMutation.isPending}
                onClick={() =>
                  void act(
                    () => issueMutation.mutateAsync({ poId }),
                    "Issue this purchase order to the supplier?",
                    "PO issued",
                  )
                }
              >
                <Send /> Issue
              </Button>
            </Can>
          )}
          {po.status === "issued" && (
            <Can perm="po:approve">
              <Button onClick={() => setReceiveOpen(true)}>
                <PackageCheck /> Receive
              </Button>
            </Can>
          )}
          {(po.status === "draft" || po.status === "issued") && (
            <Can perm="po:approve">
              <Button
                variant="outline"
                className="text-destructive"
                disabled={cancelMutation.isPending}
                onClick={() =>
                  void act(
                    () => cancelMutation.mutateAsync({ poId }),
                    "Cancel this purchase order?",
                    "PO cancelled",
                  )
                }
              >
                <Ban /> Cancel
              </Button>
            </Can>
          )}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Order lines</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Description</TableHead>
                  <TableHead className="text-right">Qty</TableHead>
                  <TableHead>Unit</TableHead>
                  <TableHead className="text-right">Unit price</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>{item.description}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {Number(item.quantity).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{item.unit ?? "—"}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {moneyExact(item.unit_price)}
                    </TableCell>
                    <TableCell className="text-right font-medium tabular-nums">
                      {moneyExact(item.amount)}
                    </TableCell>
                  </TableRow>
                ))}
                <TableRow>
                  <TableCell
                    colSpan={4}
                    className="text-right font-semibold uppercase text-muted-foreground"
                  >
                    Total
                  </TableCell>
                  <TableCell className="text-right text-base font-bold tabular-nums">
                    {moneyExact(po.total_amount)}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <div className="space-y-4">
          {po.terms && (
            <Card>
              <CardHeader>
                <CardTitle>Commercial terms</CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="whitespace-pre-wrap font-sans text-sm text-muted-foreground">
                  {po.terms}
                </pre>
              </CardContent>
            </Card>
          )}
          {po.notes && (
            <Card>
              <CardHeader>
                <CardTitle>Internal notes</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="whitespace-pre-wrap text-sm text-muted-foreground">{po.notes}</p>
              </CardContent>
            </Card>
          )}
          {po.status === "received" && (
            <Card>
              <CardContent className="p-4 text-sm text-muted-foreground">
                {po.received_to === "store" ? (
                  <>
                    ✅ Delivered {fmtDate(po.received_date)} into the store —{" "}
                    <Link to="/inventory" className="underline">
                      stock booked at PO prices
                    </Link>{" "}
                    with GRN reference <span className="font-mono">{po.doc_number}</span>. Project
                    cost posts when the stock is issued.
                  </>
                ) : (
                  <>
                    ✅ Delivered {fmtDate(po.received_date)} — {items.length} cost entr
                    {items.length === 1 ? "y" : "ies"} posted against the project budget with
                    reference <span className="font-mono">{po.doc_number}</span>.
                  </>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
      <ReceivePoDialog open={receiveOpen} onOpenChange={setReceiveOpen} po={po} />
    </div>
  );
}
