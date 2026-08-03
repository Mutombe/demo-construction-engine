import { Link } from "@tanstack/react-router";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PoStatusBadge, RfqStatusBadge } from "@/features/procurement/StatusBadges";
import { useListPurchaseOrders, useListRfqs } from "@/lib/api/generated/endpoints";
import { fmtDate, money } from "@/lib/format";

export function RfqList({ projectId }: { projectId: string }) {
  const { data, isLoading } = useListRfqs(projectId, { page_size: 50 });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Requests for Quotation</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {!isLoading && !data?.items.length && (
          <p className="text-sm text-muted-foreground">No RFQs yet for this project.</p>
        )}
        {data?.items.map((rfq) => (
          <Link
            key={rfq.id}
            to="/procurement/rfqs/$rfqId"
            params={{ rfqId: rfq.id }}
            className="flex items-center justify-between gap-3 rounded-md border p-3 transition-colors hover:bg-accent"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-muted-foreground">{rfq.doc_number}</span>
                <span className="truncate font-medium">{rfq.title}</span>
              </div>
              <div className="mt-0.5 text-xs text-muted-foreground">
                {rfq.item_count} line{rfq.item_count === 1 ? "" : "s"} · {rfq.quote_count} quote
                {rfq.quote_count === 1 ? "" : "s"}
                {rfq.due_date && <> · due {fmtDate(rfq.due_date)}</>}
              </div>
            </div>
            <RfqStatusBadge status={rfq.status ?? "draft"} />
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}

export function PoList({ projectId }: { projectId: string }) {
  const { data, isLoading } = useListPurchaseOrders(projectId, { page_size: 50 });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Purchase Orders</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {!isLoading && !data?.items.length && (
          <p className="text-sm text-muted-foreground">No purchase orders yet.</p>
        )}
        {data?.items.map((po) => (
          <Link
            key={po.id}
            to="/procurement/pos/$poId"
            params={{ poId: po.id }}
            className="flex items-center justify-between gap-3 rounded-md border p-3 transition-colors hover:bg-accent"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-muted-foreground">{po.doc_number}</span>
                <span className="truncate font-medium">{po.supplier_name}</span>
              </div>
              <div className="mt-0.5 text-xs text-muted-foreground">
                Ordered {fmtDate(po.order_date)} · {money(po.total_amount)}
              </div>
            </div>
            <PoStatusBadge status={po.status ?? "draft"} />
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}
