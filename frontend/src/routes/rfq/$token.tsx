import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle, HardHat, Warning } from "@phosphor-icons/react";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { fmtDate, money } from "@/lib/format";

export const Route = createFileRoute("/rfq/$token")({ component: SupplierRfqPage });

/** Hand-written like the client portal: the visitor holds an opaque link, not
 *  a staff JWT, so none of the generated client applies. */
async function portalFetch<T>(token: string, path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/v1/rfq-portal${path}`, {
    ...init,
    headers: {
      "X-Rfq-Token": token,
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
    },
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
  return (await res.json()) as T;
}

interface RfqItem {
  id: string;
  description: string;
  unit: string;
  quantity: string;
}

interface SupplierRfqView {
  doc_number: string;
  title: string;
  body: string | null;
  due_date: string | null;
  buyer_name: string;
  supplier_name: string;
  already_responded: boolean;
  items: RfqItem[];
}

function SupplierRfqPage() {
  const { token } = Route.useParams();
  const [prices, setPrices] = useState<Record<string, string>>({});
  const [terms, setTerms] = useState({ payment_terms: "", delivery_terms: "", notes: "" });
  const [validUntil, setValidUntil] = useState("");
  const [sent, setSent] = useState<{ total_amount: string } | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["supplier-rfq", token],
    queryFn: () => portalFetch<SupplierRfqView>(token, "/rfq"),
    retry: false,
  });

  const submit = useMutation({
    mutationFn: () =>
      portalFetch<{ total_amount: string }>(token, "/quote", {
        method: "POST",
        body: JSON.stringify({
          items: Object.entries(prices)
            .filter(([, value]) => value.trim() !== "")
            .map(([rfq_item_id, unit_price]) => ({ rfq_item_id, unit_price })),
          valid_until: validUntil || null,
          payment_terms: terms.payment_terms || null,
          delivery_terms: terms.delivery_terms || null,
          notes: terms.notes || null,
        }),
      }),
    onSuccess: setSent,
  });

  if (isLoading) {
    return <Shell><p className="text-sm text-muted-foreground">Loading…</p></Shell>;
  }

  if (error || !data) {
    return (
      <Shell>
        <div className="flex flex-col items-center gap-2 py-10 text-center">
          <Warning className="size-7 text-warning" />
          <h1 className="text-lg font-semibold">This link is not valid</h1>
          <p className="max-w-sm text-sm text-muted-foreground">
            {(error as Error)?.message ??
              "It may have expired or been withdrawn. Ask your contact for a new one."}
          </p>
        </div>
      </Shell>
    );
  }

  if (sent || data.already_responded) {
    return (
      <Shell>
        <div className="flex flex-col items-center gap-2 py-10 text-center">
          <CheckCircle className="size-8 text-success" weight="fill" />
          <h1 className="text-lg font-semibold">Quote received</h1>
          <p className="text-sm text-muted-foreground">
            {sent
              ? `Thank you. ${data.buyer_name} has your quote for ${money(sent.total_amount)}.`
              : `A quote has already been submitted for ${data.doc_number}.`}
          </p>
        </div>
      </Shell>
    );
  }

  const total = data.items.reduce((sum, item) => {
    const price = Number(prices[item.id] ?? 0);
    return sum + (Number.isFinite(price) ? price * Number(item.quantity) : 0);
  }, 0);
  const anyPriced = Object.values(prices).some((value) => value.trim() !== "");

  return (
    <Shell>
      <div className="mb-5">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">
          Request for quotation · {data.doc_number}
        </p>
        <h1 className="mt-1 text-xl font-semibold tracking-tight">{data.title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {data.buyer_name} is inviting {data.supplier_name} to price the items below
          {data.due_date && <> · replies by {fmtDate(data.due_date)}</>}
        </p>
      </div>

      {data.body && (
        <Card className="mb-4">
          <CardContent className="whitespace-pre-wrap pt-5 text-sm leading-relaxed">
            {data.body}
          </CardContent>
        </Card>
      )}

      <Card className="mb-4">
        <CardHeader>
          <CardTitle className="text-base">Your prices</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {data.items.map((item) => {
            const price = Number(prices[item.id] ?? 0);
            const line = Number.isFinite(price) ? price * Number(item.quantity) : 0;
            return (
              <div
                key={item.id}
                className="flex flex-wrap items-end gap-3 border-b pb-3 last:border-0 last:pb-0"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{item.description}</p>
                  <p className="text-xs text-muted-foreground">
                    {Number(item.quantity)} {item.unit}
                  </p>
                </div>
                <div className="w-32 space-y-1">
                  <Label htmlFor={`p-${item.id}`} className="text-xs">
                    Price per {item.unit}
                  </Label>
                  <Input
                    id={`p-${item.id}`}
                    inputMode="decimal"
                    placeholder="0.00"
                    value={prices[item.id] ?? ""}
                    onChange={(e) =>
                      setPrices((prev) => ({ ...prev, [item.id]: e.target.value }))
                    }
                  />
                </div>
                <div className="w-28 text-right text-sm tabular-nums">
                  {line > 0 ? money(line) : "—"}
                </div>
              </div>
            );
          })}
          <div className="flex items-baseline justify-between border-t pt-3">
            <span className="text-sm font-medium">Total</span>
            <span className="text-lg font-semibold tabular-nums">{money(total)}</span>
          </div>
          <p className="text-xs text-muted-foreground">
            Leave a line blank if you are not quoting for it.
          </p>
        </CardContent>
      </Card>

      <Card className="mb-4">
        <CardHeader>
          <CardTitle className="text-base">Terms</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="valid">Quote valid until</Label>
            <Input
              id="valid"
              type="date"
              value={validUntil}
              onChange={(e) => setValidUntil(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pay">Payment terms</Label>
            <Input
              id="pay"
              placeholder="30 days from invoice"
              value={terms.payment_terms}
              onChange={(e) => setTerms({ ...terms, payment_terms: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="deliver">Delivery</Label>
            <Input
              id="deliver"
              placeholder="5 working days to site"
              value={terms.delivery_terms}
              onChange={(e) => setTerms({ ...terms, delivery_terms: e.target.value })}
            />
          </div>
          <div className="space-y-1.5 sm:col-span-3">
            <Label htmlFor="notes">Anything else</Label>
            <Textarea
              id="notes"
              rows={2}
              value={terms.notes}
              onChange={(e) => setTerms({ ...terms, notes: e.target.value })}
            />
          </div>
        </CardContent>
      </Card>

      {submit.isError && (
        <p className="mb-3 text-sm text-destructive">{(submit.error as Error).message}</p>
      )}

      <Button
        className="w-full"
        disabled={!anyPriced || submit.isPending}
        onClick={() => submit.mutate()}
      >
        {submit.isPending ? "Sending…" : "Submit Quote"}
      </Button>
      <p className="mt-2 text-center text-xs text-muted-foreground">
        You can only submit once, so check your prices before sending.
      </p>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-secondary/40 py-8">
      <div className="mx-auto max-w-2xl px-4">
        <div className="mb-6 flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <HardHat className="h-5 w-5" />
          </div>
          <span className="text-sm font-semibold">Request for Quotation</span>
        </div>
        {children}
      </div>
    </div>
  );
}
