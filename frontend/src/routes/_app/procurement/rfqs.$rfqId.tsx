import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { FileText, PaperPlaneTilt, Plus, ShoppingCart } from "@phosphor-icons/react";
import { useState } from "react";
import { toast } from "@/lib/toast";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { confirmDialog } from "@/components/ui/confirm";
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
import { PoFromQuoteDialog } from "@/features/procurement/PoFromQuoteDialog";
import { QuoteCompare } from "@/features/procurement/QuoteCompare";
import { QuoteExtractDialog } from "@/features/procurement/QuoteExtractDialog";
import { QuoteStatusBadge, RfqStatusBadge } from "@/features/procurement/StatusBadges";
import {
  getGetRfqQueryOptions,
  getGetSupplierActivityQueryOptions,
  useGetRfq,
  useIssueRfq,
  useListQuotes,
} from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";

export const Route = createFileRoute("/_app/procurement/rfqs/$rfqId")({
  component: RfqDetailPage,
  loader: ({ context: { queryClient }, params }) =>
    queryClient.ensureQueryData(getGetRfqQueryOptions(params.rfqId)),
});

function RfqDetailPage() {
  const { rfqId } = Route.useParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { data: rfq } = useGetRfq(rfqId);
  const { data: quotes } = useListQuotes(rfqId);
  const issueMutation = useIssueRfq();
  const [quoteDialogOpen, setQuoteDialogOpen] = useState(false);
  const [poQuoteId, setPoQuoteId] = useState<string | null>(null);

  if (!rfq) {
    return <PageSkeleton rows={5} />;
  }

  const issue = async () => {
    if (
      !(await confirmDialog({
        title: "Issue RFQ",
        message: "Issue this RFQ? Lines become read-only once issued.",
      }))
    )
      return;
    try {
      await issueMutation.mutateAsync({ rfqId });
      await queryClient.invalidateQueries();
      toast.success("RFQ issued");
    } catch {
      toast.error("Could not issue RFQ");
    }
  };

  const acceptedQuote = quotes?.find((q) => q.status === "accepted");

  return (
    <div>
      <Breadcrumbs
        items={[{ label: "Procurement", to: "/procurement" }, { label: rfq.doc_number }]}
      />
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-semibold tracking-tight">{rfq.title}</h1>
            <RfqStatusBadge status={rfq.status ?? "draft"} />
            {rfq.ai_generated && <Badge variant="secondary">AI drafted</Badge>}
          </div>
          <div className="mt-1 text-sm text-muted-foreground">
            {rfq.doc_number} ·{" "}
            <EntityLink
              to="/projects/$projectId/procurement"
              params={{ projectId: rfq.project_id }}
              className="text-sm font-normal"
            >
              {rfq.project_code} {rfq.project_name}
            </EntityLink>
            {rfq.due_date && <> · quotes due {fmtDate(rfq.due_date)}</>}
          </div>
        </div>
        <div className="flex gap-2">
          {rfq.status === "draft" && (
            <Can perm="procurement:write">
              <Button onClick={() => void issue()} disabled={issueMutation.isPending}>
                <PaperPlaneTilt /> Issue RFQ
              </Button>
            </Can>
          )}
          {rfq.status !== "draft" && (
            <Can perm="procurement:write">
              <Button onClick={() => setQuoteDialogOpen(true)}>
                <Plus /> Record Quote
              </Button>
            </Can>
          )}
          {acceptedQuote && (
            <Can perm="procurement:write">
              <Button variant="outline" onClick={() => setPoQuoteId(acceptedQuote.id)}>
                <ShoppingCart /> Create PO
              </Button>
            </Can>
          )}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Schedule of Items</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Description</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                    <TableHead>Unit</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(rfq.items ?? []).map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>{item.description}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {Number(item.quantity).toLocaleString()}
                      </TableCell>
                      <TableCell className="text-muted-foreground">{item.unit}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {rfq.body && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileText className="h-4 w-4" /> RFQ Document
                </CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="whitespace-pre-wrap font-sans text-sm text-muted-foreground">
                  {rfq.body}
                </pre>
              </CardContent>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Quotes ({quotes?.length ?? 0})</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {!quotes?.length && (
                <p className="text-sm text-muted-foreground">
                  {rfq.status === "draft"
                    ? "Issue the RFQ, then record supplier quotes here."
                    : "No quotes recorded yet."}
                </p>
              )}
              {quotes?.map((quote) => (
                <div key={quote.id} className="rounded-md border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <EntityLink
                        to="/procurement/suppliers/$supplierId"
                        params={{ supplierId: quote.supplier_id }}
                        prefetch={() => getGetSupplierActivityQueryOptions(quote.supplier_id)}
                      >
                        {quote.supplier_name}
                      </EntityLink>
                      <QuoteStatusBadge status={quote.status ?? "received"} />
                      {quote.ai_extracted && <Badge variant="secondary">AI extracted</Badge>}
                    </div>
                    <span className="font-semibold tabular-nums">
                      {moneyExact(quote.total_amount)}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {quote.coverage_pct}% coverage · received {fmtDate(quote.received_date)}
                    {quote.valid_until && <> · valid until {fmtDate(quote.valid_until)}</>}
                    {quote.payment_terms && <> · {quote.payment_terms}</>}
                  </div>
                  {quote.status === "accepted" && (
                    <div className="mt-2">
                      <Can perm="procurement:write">
                        <Button size="sm" variant="outline" onClick={() => setPoQuoteId(quote.id)}>
                          <ShoppingCart className="h-3.5 w-3.5" /> Create Purchase Order
                        </Button>
                      </Can>
                    </div>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>

          {(quotes?.length ?? 0) >= 2 && <QuoteCompare rfq={rfq} />}
        </div>
      </div>

      <QuoteExtractDialog open={quoteDialogOpen} onOpenChange={setQuoteDialogOpen} rfq={rfq} />
      {poQuoteId && (
        <PoFromQuoteDialog
          open={poQuoteId !== null}
          onOpenChange={(open) => !open && setPoQuoteId(null)}
          quoteId={poQuoteId}
          projectId={rfq.project_id}
          onCreated={(poId) =>
            void navigate({ to: "/procurement/pos/$poId", params: { poId } })
          }
        />
      )}
    </div>
  );
}
