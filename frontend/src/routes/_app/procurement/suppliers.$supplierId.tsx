import { createFileRoute } from "@tanstack/react-router";
import { EnvelopeSimple, FileText, PencilSimple, Phone, ShoppingCart, Tag } from "@phosphor-icons/react";
import { useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ClickableRow } from "@/components/ui/linked-row";
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
import { PoStatusBadge, QuoteStatusBadge } from "@/features/procurement/StatusBadges";
import { SupplierPortalPanel } from "@/features/procurement/SupplierPortalPanel";
import { SupplierRatingCard } from "@/features/procurement/SupplierRating";
import { VendorCompliance } from "@/features/subcontracts/VendorCompliance";
import { SupplierFormDialog } from "@/features/procurement/SupplierFormDialog";
import {
  getGetPurchaseOrderQueryOptions,
  getGetRfqQueryOptions,
  getGetSupplierActivityQueryOptions,
  useGetSupplierActivity,
} from "@/lib/api/generated/endpoints";
import type { SupplierScorecard } from "@/lib/api/generated/model";
import { fmtDate, money, moneyExact } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/procurement/suppliers/$supplierId")({
  component: SupplierDetailPage,
  loader: ({ context: { queryClient }, params }) =>
    queryClient.ensureQueryData(getGetSupplierActivityQueryOptions(params.supplierId)),
});

function Metric({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "good" | "bad";
}) {
  return (
    <div className="rounded-md border p-3">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div
        className={cn(
          "mt-0.5 text-lg font-semibold tabular-nums",
          tone === "good" && "text-success",
          tone === "bad" && "text-destructive",
        )}
      >
        {value}
      </div>
      {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}

/** Performance the supplier has actually delivered, not what they promised.
 *  Metrics with no history read "—" rather than a misleading zero. */
function Scorecard({ scorecard }: { scorecard: SupplierScorecard }) {
  const onTime = scorecard.on_time_pct;
  const variance = scorecard.avg_price_variance_pct;

  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle>Scorecard</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="On-time delivery"
          value={onTime === null || onTime === undefined ? "—" : `${Number(onTime)}%`}
          hint={
            scorecard.delivered_count > 0
              ? `${scorecard.on_time_count} of ${scorecard.delivered_count} deliveries`
              : "no deliveries with a due date yet"
          }
          tone={
            onTime === null || onTime === undefined
              ? "default"
              : Number(onTime) >= 80
                ? "good"
                : "bad"
          }
        />
        <Metric
          label="Average delay"
          value={
            scorecard.avg_delay_days === null || scorecard.avg_delay_days === undefined
              ? "—"
              : `${Number(scorecard.avg_delay_days)} days`
          }
          hint="across late deliveries only"
          tone={Number(scorecard.avg_delay_days ?? 0) > 0 ? "bad" : "default"}
        />
        <Metric
          label="Quote response"
          value={
            scorecard.avg_quote_response_days === null ||
            scorecard.avg_quote_response_days === undefined
              ? "—"
              : `${Number(scorecard.avg_quote_response_days)} days`
          }
          hint={`${scorecard.quoted_rfq_count} quote${scorecard.quoted_rfq_count === 1 ? "" : "s"} returned`}
        />
        <Metric
          label="Price vs quote"
          value={
            variance === null || variance === undefined
              ? "—"
              : `${Number(variance) > 0 ? "+" : ""}${Number(variance)}%`
          }
          hint={
            scorecard.priced_line_count > 0
              ? `${scorecard.priced_line_count} ordered line${scorecard.priced_line_count === 1 ? "" : "s"}`
              : "no quote-backed orders yet"
          }
          tone={Number(variance ?? 0) > 0 ? "bad" : "default"}
        />
        {scorecard.open_overdue_count > 0 && (
          <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm sm:col-span-2 xl:col-span-4">
            <span className="font-medium text-destructive">
              {scorecard.open_overdue_count} outstanding order
              {scorecard.open_overdue_count === 1 ? "" : "s"} past the promised date
            </span>{" "}
            <span className="text-muted-foreground">Chase before ordering again.</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function SupplierDetailPage() {
  const { supplierId } = Route.useParams();
  const { data: activity } = useGetSupplierActivity(supplierId);
  const [editOpen, setEditOpen] = useState(false);

  if (!activity) {
    return <DetailSkeleton />;
  }
  const { supplier, purchase_orders, quotes, totals } = activity;

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Procurement", to: "/procurement" },
          { label: "Suppliers", to: "/procurement/suppliers" },
          { label: supplier.name },
        ]}
      />
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-semibold tracking-tight">{supplier.name}</h1>
            {supplier.is_active ? (
              <Badge variant="success">Active</Badge>
            ) : (
              <Badge variant="outline">Inactive</Badge>
            )}
          </div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
            {supplier.contact_name && <span>{supplier.contact_name}</span>}
            {supplier.email && (
              <a
                href={`mailto:${supplier.email}`}
                className="inline-flex items-center gap-1 hover:text-foreground"
              >
                <EnvelopeSimple className="h-3.5 w-3.5" /> {supplier.email}
              </a>
            )}
            {supplier.phone && (
              <span className="inline-flex items-center gap-1">
                <Phone className="h-3.5 w-3.5" /> {supplier.phone}
              </span>
            )}
            {supplier.categories && (
              <span className="inline-flex items-center gap-1">
                <Tag className="h-3.5 w-3.5" /> {supplier.categories}
              </span>
            )}
          </div>
        </div>
        <Can perm="procurement:write">
          <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
            <PencilSimple /> Edit
          </Button>
        </Can>
      </div>

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <StatCard
          label="Purchase orders"
          value={totals.po_count}
          icon={<ShoppingCart />}
          sub="all time"
        />
        <StatCard label="PO value" value={money(totals.po_value)} tone="brand" />
        <StatCard label="Quotes received" value={totals.quote_count} icon={<FileText />} />
      </div>

      <div className="mb-4">
        <SupplierRatingCard supplierId={supplierId} />
      </div>

      <Scorecard scorecard={activity.scorecard} />

      <div className="mb-4 grid gap-4 xl:grid-cols-2">
        <VendorCompliance supplierId={supplierId} />
        <SupplierPortalPanel supplierId={supplierId} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Purchase Orders</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>PO</TableHead>
                  <TableHead>Project</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Ordered</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {purchase_orders.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="p-0">
                      <EmptyState
                        icon={<ShoppingCart />}
                        title="No purchase orders yet"
                        hint="POs raised against this supplier will appear here."
                      />
                    </TableCell>
                  </TableRow>
                )}
                {purchase_orders.map((po, rowIndex) => (
                  <ClickableRow
                    index={rowIndex}
                    key={po.id}
                    to="/procurement/pos/$poId"
                    params={{ poId: po.id }}
                    prefetch={() => getGetPurchaseOrderQueryOptions(po.id)}
                  >
                    <TableCell className="font-mono text-xs">{po.doc_number}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {po.project_code ?? "—"}
                    </TableCell>
                    <TableCell>
                      <PoStatusBadge status={po.status} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {fmtDate(po.order_date)}
                    </TableCell>
                    <TableCell className="text-right font-medium tabular-nums">
                      {moneyExact(po.total_amount)}
                    </TableCell>
                  </ClickableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Quotes</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>RFQ</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Received</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {quotes.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="p-0">
                      <EmptyState
                        icon={<FileText />}
                        title="No quotes yet"
                        hint="Quotes this supplier submits against RFQs will appear here."
                      />
                    </TableCell>
                  </TableRow>
                )}
                {quotes.map((quote, rowIndex) => (
                  <ClickableRow
                    index={rowIndex}
                    key={quote.id}
                    to="/procurement/rfqs/$rfqId"
                    params={{ rfqId: quote.rfq_id }}
                    prefetch={() => getGetRfqQueryOptions(quote.rfq_id)}
                  >
                    <TableCell className="font-mono text-xs">
                      {quote.rfq_doc_number ?? "—"}
                    </TableCell>
                    <TableCell className="max-w-40 truncate">{quote.rfq_title ?? "—"}</TableCell>
                    <TableCell>
                      <QuoteStatusBadge status={quote.status} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {fmtDate(quote.received_date)}
                    </TableCell>
                    <TableCell className="text-right font-medium tabular-nums">
                      {moneyExact(quote.total_amount)}
                    </TableCell>
                  </ClickableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      <SupplierFormDialog open={editOpen} onOpenChange={setEditOpen} supplier={supplier} />
    </div>
  );
}
