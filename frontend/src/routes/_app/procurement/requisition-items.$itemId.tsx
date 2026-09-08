import { createFileRoute, Link } from "@tanstack/react-router";
import { Package, ShoppingCart, Warning } from "@phosphor-icons/react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { useGetRequisitionLine } from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";

export const Route = createFileRoute("/_app/procurement/requisition-items/$itemId")({
  component: RequisitionLineDetail,
});

/** One requested line, and what became of it.
 *
 *  This is where a shortage on site turns into buying. Somebody asks for forty
 *  bags of cement; weeks later there is an enquiry, an order and a delivery,
 *  and until now nothing tied those together from the request end. */
function RequisitionLineDetail() {
  const { itemId } = Route.useParams();
  const query = useGetRequisitionLine(itemId);
  const line = query.data;

  if (query.isError) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  }
  if (!line) return <PageSkeleton rows={3} />;

  const orders = line.orders ?? [];
  const enquiries = line.enquiries ?? [];
  const over = Number(line.over_ordered ?? 0);
  const ordered = Number(line.ordered_quantity ?? 0);
  const asked = Number(line.quantity);

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Material Requests", to: "/procurement/requisitions" },
          {
            label: line.doc_number,
            to: "/procurement/requisitions/$requisitionId",
            params: { requisitionId: line.requisition_id },
          },
          { label: line.description },
        ]}
      />

      <div className="mb-5">
        <h1 className="text-xl font-semibold tracking-tight">{line.description}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {Number(line.quantity).toLocaleString()} {line.unit} requested on{" "}
          <Link
            to="/procurement/requisitions/$requisitionId"
            params={{ requisitionId: line.requisition_id }}
            className="hover:text-foreground hover:underline"
          >
            {line.doc_number}
          </Link>
          {line.needed_by && <> · needed by {fmtDate(line.needed_by)}</>}
        </p>
      </div>

      {over > 0 && (
        <div className="mb-4 flex items-start gap-2 rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-sm">
          <Warning weight="fill" className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <span className="text-muted-foreground">
            {ordered.toLocaleString()} {line.unit} have been ordered against a request for{" "}
            {asked.toLocaleString()} — {over.toLocaleString()} more than was asked for.
          </span>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <ShoppingCart /> Orders raised for it
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {orders.length ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Order</TableHead>
                      <TableHead>Supplier</TableHead>
                      <TableHead className="num">Quantity</TableHead>
                      <TableHead className="num">Price</TableHead>
                      <TableHead>Delivery</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {orders.map((order) => (
                      <TableRow key={order.purchase_order_id}>
                        <TableCell className="font-mono text-xs">
                          <Link
                            to="/procurement/pos/$poId"
                            params={{ poId: order.purchase_order_id }}
                            className="hover:underline"
                          >
                            {order.doc_number}
                          </Link>
                          <div className="mt-0.5">
                            <Badge variant="outline">{order.status}</Badge>
                          </div>
                        </TableCell>
                        <TableCell className="text-sm">
                          <Link
                            to="/procurement/suppliers/$supplierId"
                            params={{ supplierId: order.supplier_id }}
                            className="hover:underline"
                          >
                            {order.supplier_name ?? "Supplier"}
                          </Link>
                        </TableCell>
                        <TableCell className="num">
                          {Number(order.quantity).toLocaleString()}
                        </TableCell>
                        <TableCell className="num">
                          {moneyExact(order.unit_price)}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {order.received_date
                            ? `delivered ${fmtDate(order.received_date)}`
                            : order.expected_delivery
                              ? `due ${fmtDate(order.expected_delivery)}`
                              : "no date"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <p className="px-4 py-6 text-center text-sm text-muted-foreground">
                  Nothing has been ordered for this yet.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Enquiries that went out</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {enquiries.length ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Enquiry</TableHead>
                      <TableHead>Title</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {enquiries.map((rfq) => (
                      <TableRow key={rfq.rfq_id}>
                        <TableCell className="font-mono text-xs">
                          <Link
                            to="/procurement/rfqs/$rfqId"
                            params={{ rfqId: rfq.rfq_id }}
                            className="hover:underline"
                          >
                            {rfq.doc_number}
                          </Link>
                        </TableCell>
                        <TableCell className="text-sm">{rfq.title}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{rfq.status}</Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <p className="px-4 py-6 text-center text-sm text-muted-foreground">
                  Nobody has been asked to price this.
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">What was asked for</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row
                label="Quantity"
                value={`${Number(line.quantity).toLocaleString()} ${line.unit}`}
              />
              <Row
                label="Ordered so far"
                value={
                  ordered ? `${ordered.toLocaleString()} ${line.unit}` : "Nothing yet"
                }
              />
              <Row label="On the request" value={line.doc_number} />
              <Row label="Request status" value={line.requisition_status} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Package /> The same thing elsewhere
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {line.stock_item_id ? (
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-muted-foreground">In the store</span>
                  <Link
                    to="/inventory/$itemId"
                    params={{ itemId: line.stock_item_id }}
                    className="text-right font-medium hover:underline"
                  >
                    {line.stock_code}
                    {line.stock_on_hand != null && (
                      <span className="ml-1 text-muted-foreground">
                        ({Number(line.stock_on_hand).toLocaleString()} held)
                      </span>
                    )}
                  </Link>
                </div>
              ) : (
                <p className="text-muted-foreground">
                  Nothing in the store goes by this name.
                </p>
              )}

              {line.boq_item_id && line.project_id && (
                <div className="border-t pt-2">
                  <Link
                    to="/projects/$projectId/boq"
                    params={{ projectId: line.project_id }}
                    className="text-sm hover:underline"
                  >
                    Priced from the bill: {line.boq_description}
                  </Link>
                </div>
              )}

              {line.matched_by === "description" && (
                <p className="border-t pt-2 text-xs text-muted-foreground">
                  Nothing on this line was linked to the bill or the store when it was
                  written, so the orders and enquiries above were found by matching the
                  wording. Treat them as a likeness rather than a recorded connection.
                </p>
              )}
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
      <span className="truncate text-right font-medium capitalize">{value}</span>
    </div>
  );
}
