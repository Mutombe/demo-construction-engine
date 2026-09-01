import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle, Warning } from "@phosphor-icons/react";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { fmtDate, moneyExact } from "@/lib/format";

export const Route = createFileRoute("/supplier/$token")({ component: SupplierPortalPage });

interface Overview {
  supplier_name: string;
  company_name: string;
  is_compliant: boolean;
  missing_documents: string[];
  orders: {
    id: string;
    doc_number: string;
    order_date: string | null;
    status: string;
    total_amount: string;
  }[];
  invoices: {
    id: string;
    doc_number: string;
    reference: string | null;
    invoice_date: string;
    amount: string;
    status: string;
    variance: string;
    note: string | null;
  }[];
}

/** Hand-written like the other portals: the visitor holds an opaque link in
 *  the URL, not a staff token, so none of the generated client applies. */
async function portalFetch<T>(token: string, path = "", init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/v1/supplier-portal/${token}${path}`, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (!res.ok) {
    let detail = "Something went wrong";
    try {
      detail = (await res.json())?.error?.detail ?? detail;
    } catch {
      // non-JSON error body
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const DOC_LABELS: Record<string, string> = {
  tax_clearance: "tax clearance",
  vat_registration: "VAT registration",
  company_registration: "company registration",
  public_liability: "public liability cover",
  workmans_compensation: "workman's compensation",
  safety_certificate: "safety certificate",
  bank_confirmation: "bank confirmation",
  trade_licence: "trade licence",
};

function SupplierPortalPage() {
  const { token } = Route.useParams();
  const { data, isLoading, error } = useQuery({
    queryKey: ["supplier-portal", token],
    queryFn: () => portalFetch<Overview>(token),
    retry: false,
  });

  if (isLoading) {
    return <Shell><p className="text-sm text-muted-foreground">Loading…</p></Shell>;
  }
  if (error || !data) {
    return (
      <Shell>
        <Card>
          <CardContent className="py-8 text-center">
            <Warning className="mx-auto mb-2 h-6 w-6 text-muted-foreground" />
            <p className="font-medium">This link is not valid</p>
            <p className="mt-1 text-sm text-muted-foreground">
              It may have expired or been withdrawn. Ask your contact for a new one.
            </p>
          </CardContent>
        </Card>
      </Shell>
    );
  }

  return (
    <Shell>
      <div className="mb-5">
        <h1 className="text-xl font-semibold tracking-tight">{data.supplier_name}</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Your account with {data.company_name}
        </p>
      </div>

      {!data.is_compliant && data.missing_documents.length > 0 && (
        <div className="mb-4 flex items-start gap-2 rounded-md border border-warning/40 bg-warning/5 px-3 py-2.5 text-sm">
          <Warning weight="fill" className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <div>
            <p className="font-medium text-warning">Paperwork we do not have in date</p>
            <p className="mt-0.5 text-muted-foreground">
              We need a current{" "}
              {data.missing_documents
                .map((d) => DOC_LABELS[d] ?? d.replace(/_/g, " "))
                .join(" and ")}
              . Send it to your contact and new work can be placed with you again.
            </p>
          </div>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Your orders</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {data.orders.length ? (
              <Table maxHeight="45vh">
                <TableHeader>
                  <TableRow>
                    <TableHead>Order</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead className="num">Value</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.orders.map((order) => (
                    <TableRow key={order.id}>
                      <TableCell className="font-mono text-xs">{order.doc_number}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {order.order_date ? fmtDate(order.order_date) : "—"}
                      </TableCell>
                      <TableCell className="num">{moneyExact(order.total_amount)}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{order.status.replace(/_/g, " ")}</Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="px-4 py-6 text-center text-sm text-muted-foreground">
                No orders on your account yet.
              </p>
            )}
          </CardContent>
        </Card>

        <SubmitInvoice token={token} orders={data.orders} />
      </div>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-base">Invoices you have sent</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {data.invoices.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Your reference</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead className="num">Amount</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.invoices.map((invoice) => (
                  <TableRow key={invoice.id}>
                    <TableCell>
                      <div className="font-medium">{invoice.reference ?? invoice.doc_number}</div>
                      {invoice.note && (
                        <div className="text-xs text-muted-foreground">{invoice.note}</div>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {fmtDate(invoice.invoice_date)}
                    </TableCell>
                    <TableCell className="num">{moneyExact(invoice.amount)}</TableCell>
                    <TableCell>
                      {invoice.status === "accepted" ? (
                        <Badge variant="success">Accepted</Badge>
                      ) : invoice.status === "queried" ? (
                        <Badge variant="destructive">Queried</Badge>
                      ) : (
                        <Badge variant="warning">With us</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="px-4 py-6 text-center text-sm text-muted-foreground">
              Nothing submitted yet.
            </p>
          )}
        </CardContent>
      </Card>
    </Shell>
  );
}

function SubmitInvoice({
  token,
  orders,
}: {
  token: string;
  orders: Overview["orders"];
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    purchase_order_id: "",
    reference: "",
    amount: "",
    notes: "",
  });
  const [sent, setSent] = useState(false);

  const submit = useMutation({
    mutationFn: () =>
      portalFetch(token, "/invoices", {
        method: "POST",
        body: JSON.stringify({
          purchase_order_id: form.purchase_order_id || null,
          reference: form.reference || null,
          amount: form.amount,
          notes: form.notes || null,
        }),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["supplier-portal", token] });
      setForm({ purchase_order_id: "", reference: "", amount: "", notes: "" });
      setSent(true);
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Send us an invoice</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {sent && (
          <div className="flex items-center gap-2 rounded-md border border-success/30 bg-success/5 px-3 py-2 text-sm text-success">
            <CheckCircle weight="fill" className="h-4 w-4 shrink-0" />
            Received. It will show below once somebody has looked at it.
          </div>
        )}

        <div className="space-y-1.5">
          <Label htmlFor="po">Against which order</Label>
          <Select
            id="po"
            value={form.purchase_order_id}
            onChange={(e) => setForm({ ...form, purchase_order_id: e.target.value })}
          >
            <option value="">Not against an order</option>
            {orders.map((order) => (
              <option key={order.id} value={order.id}>
                {order.doc_number} — {moneyExact(order.total_amount)}
              </option>
            ))}
          </Select>
          <p className="text-xs text-muted-foreground">
            Naming the order is what gets it paid quickly. Without one somebody has to work out
            what it is for.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="ref">Your invoice number</Label>
            <Input
              id="ref"
              value={form.reference}
              onChange={(e) => setForm({ ...form, reference: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="amt">Amount</Label>
            <Input
              id="amt"
              inputMode="decimal"
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="note">Anything we should know</Label>
          <Textarea
            id="note"
            rows={2}
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
          />
        </div>

        {submit.isError && (
          <p className="text-sm text-destructive">{(submit.error as Error).message}</p>
        )}

        <Button
          className="w-full"
          disabled={!form.amount || submit.isPending}
          onClick={() => {
            setSent(false);
            submit.mutate();
          }}
        >
          Send Invoice
        </Button>
      </CardContent>
    </Card>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-secondary/40 p-4">
      <div className="mx-auto max-w-4xl py-6">
        <img
          src="/company-logo.png"
          alt=""
          className="mb-6 h-8 w-auto dark:brightness-0 dark:invert"
        />
        {children}
      </div>
    </div>
  );
}
