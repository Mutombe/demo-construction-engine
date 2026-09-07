import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Check, Receipt, WarningCircle, X } from "@phosphor-icons/react";
import { useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorState } from "@/components/ui/list-state";
import { PageSkeleton } from "@/components/ui/skeleton";
import { errDetail } from "@/lib/api/errors";
import {
  useDecideSupplierInvoice,
  useGetSupplierInvoice,
} from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/_app/procurement/invoices/$invoiceId")({
  component: SupplierInvoiceDetail,
});

/** One supplier's claim, on its own page.
 *
 *  The variance against the order is the whole reason these are taken in
 *  through a portal rather than by email, so it is stated plainly rather than
 *  left for somebody to work out. */
function SupplierInvoiceDetail() {
  const { invoiceId } = Route.useParams();
  const queryClient = useQueryClient();
  const query = useGetSupplierInvoice(invoiceId);
  const decide = useDecideSupplierInvoice();
  const [note, setNote] = useState("");
  const [querying, setQuerying] = useState(false);

  const invoice = query.data;
  if (query.isError) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  }
  if (!invoice) return <PageSkeleton rows={3} />;

  const variance = Number(invoice.variance ?? 0);
  const waiting = invoice.status === "submitted";

  const act = async (accept: boolean, text?: string) => {
    try {
      await decide.mutateAsync({ invoiceId, data: { accept, note: text ?? null } });
      await queryClient.invalidateQueries();
      setQuerying(false);
      setNote("");
      toast.success(accept ? "Accepted" : "Sent back to the supplier");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Supplier Invoices", to: "/procurement/invoices" },
          { label: invoice.reference ?? invoice.doc_number },
        ]}
      />

      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight">
              {invoice.reference ?? invoice.doc_number}
            </h1>
            {invoice.status === "accepted" ? (
              <Badge variant="success">Accepted</Badge>
            ) : invoice.status === "queried" ? (
              <Badge variant="destructive">Queried</Badge>
            ) : (
              <Badge variant="warning">Waiting</Badge>
            )}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            <span className="font-mono">{invoice.doc_number}</span> · received{" "}
            {fmtDate(invoice.invoice_date)}
          </p>
        </div>
        {waiting && (
          <Can perm="procurement:write">
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setQuerying(true)}>
                <X /> Query
              </Button>
              <Button onClick={() => void act(true)}>
                <Check /> Accept
              </Button>
            </div>
          </Can>
        )}
      </div>

      {Math.abs(variance) > 1 && (
        <div className="mb-4 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          <WarningCircle weight="fill" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            This claim is {moneyExact(Math.abs(variance))}{" "}
            {variance > 0 ? "more" : "less"} than the order it is against. Worth settling
            before it is paid rather than after.
          </span>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Receipt /> The claim
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row label="Their reference" value={invoice.reference ?? "Not given"} />
              <Row label="Dated" value={fmtDate(invoice.invoice_date)} />
              <Row label="Amount claimed" value={moneyExact(invoice.amount)} />
              <Row
                label="Against order"
                value={invoice.purchase_order_id ? "Yes" : "No order given"}
              />
              {invoice.purchase_order_id && (
                <div className="border-t pt-2">
                  <Link
                    to="/procurement/pos/$poId"
                    params={{ poId: invoice.purchase_order_id }}
                    className="text-sm hover:underline"
                  >
                    Open the purchase order
                  </Link>
                </div>
              )}
            </CardContent>
          </Card>

          {invoice.notes && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">What they said</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="whitespace-pre-wrap text-sm">{invoice.notes}</p>
              </CardContent>
            </Card>
          )}

          {querying && (
            <Card>
              <CardContent className="space-y-2 pt-4">
                <Label htmlFor="query-note">What is wrong with it</Label>
                <Input
                  id="query-note"
                  placeholder="Send the signed delivery note with it"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  The supplier sees this on their own page. A query with no reason comes
                  back unchanged.
                </p>
                <div className="flex justify-end gap-2">
                  <Button variant="outline" size="sm" onClick={() => setQuerying(false)}>
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    disabled={!note.trim()}
                    onClick={() => void act(false, note)}
                  >
                    Send Back
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {invoice.decision_note && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">What we told them</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="whitespace-pre-wrap text-sm">{invoice.decision_note}</p>
              </CardContent>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Matching</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row label="Claimed" value={moneyExact(invoice.amount)} />
              <Row
                label="Difference"
                value={
                  invoice.purchase_order_id
                    ? `${variance > 0 ? "+" : ""}${moneyExact(variance)}`
                    : "Nothing to match"
                }
              />
              <p className="border-t pt-2 text-xs text-muted-foreground">
                Accepting records their reference against the order so a payment can be
                matched to it. It posts nothing — the payable was created when the goods
                were received, and booking this too would owe them twice for one delivery.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Supplier</CardTitle>
            </CardHeader>
            <CardContent>
              <Link
                to="/procurement/suppliers/$supplierId"
                params={{ supplierId: invoice.supplier_id }}
                className="text-sm hover:underline"
              >
                Open the supplier
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
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
