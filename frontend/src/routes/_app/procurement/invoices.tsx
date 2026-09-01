import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Check, Receipt, WarningCircle, X } from "@phosphor-icons/react";
import { useState } from "react";
import { PageHeader } from "@/components/layout/AppShell";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorState } from "@/components/ui/list-state";
import { TableSkeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/ui/stat-card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { errDetail } from "@/lib/api/errors";
import {
  useDecideSupplierInvoice,
  useGetMatchingReport,
  useListSupplierInvoices,
} from "@/lib/api/generated/endpoints";
import { fmtDate, money, moneyExact } from "@/lib/format";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/_app/procurement/invoices")({
  component: SupplierInvoices,
});

function SupplierInvoices() {
  const queryClient = useQueryClient();
  const invoicesQuery = useListSupplierInvoices({ status: "submitted" });
  const { data: invoices, isLoading } = invoicesQuery;
  const { data: mismatches } = useGetMatchingReport();
  const decide = useDecideSupplierInvoice();
  const [querying, setQuerying] = useState<string | null>(null);
  const [note, setNote] = useState("");

  const rows = invoices ?? [];
  const flagged = mismatches ?? [];
  const flaggedIds = new Set(flagged.map((row) => row.invoice_id));
  const claimed = rows.reduce((sum, row) => sum + Number(row.amount), 0);

  const act = async (invoiceId: string, accept: boolean, text?: string) => {
    try {
      await decide.mutateAsync({ invoiceId, data: { accept, note: text ?? null } });
      await queryClient.invalidateQueries();
      setQuerying(null);
      setNote("");
      toast.success(accept ? "Accepted" : "Sent back to the supplier");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <div>
      <PageHeader
        title="Supplier Invoices"
        description="Claims sent in through the supplier portal, waiting to be matched"
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <StatCard label="Waiting" value={rows.length} icon={<Receipt />} />
        <StatCard label="Claimed" value={money(claimed)} tone="brand" />
        <StatCard
          label="Not Matching"
          value={flagged.length}
          icon={<WarningCircle />}
          tone={flagged.length ? "negative" : "default"}
          sub="against the order"
        />
      </div>

      {flagged.length > 0 && (
        <Card className="mb-4">
          <CardHeader>
            <CardTitle className="text-base">Worth looking at first</CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              A claim that does not agree with the order it is against. Catching it here is the
              whole reason for taking invoices this way.
            </p>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Invoice</TableHead>
                  <TableHead>Order</TableHead>
                  <TableHead className="num">Ordered</TableHead>
                  <TableHead className="num">Claimed</TableHead>
                  <TableHead className="num">Difference</TableHead>
                  <TableHead>Issue</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {flagged.map((row) => (
                  <TableRow key={row.invoice_id}>
                    <TableCell className="font-medium">
                      {row.reference ?? row.doc_number}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {row.order_number ?? "—"}
                    </TableCell>
                    <TableCell className="num text-muted-foreground">
                      {row.ordered != null ? moneyExact(row.ordered) : "—"}
                    </TableCell>
                    <TableCell className="num">{moneyExact(row.amount)}</TableCell>
                    <TableCell className="num font-medium text-destructive">
                      {row.variance != null ? moneyExact(row.variance) : "—"}
                    </TableCell>
                    <TableCell>
                      <Badge variant="destructive">{row.issue}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Waiting on a decision</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {invoicesQuery.isError ? (
            <ErrorState
              error={invoicesQuery.error}
              onRetry={() => void invoicesQuery.refetch()}
            />
          ) : isLoading && !invoices ? (
            <TableSkeleton columns={5} />
          ) : rows.length ? (
            <Table maxHeight="55vh">
              <TableHeader>
                <TableRow>
                  <TableHead>Reference</TableHead>
                  <TableHead>Received</TableHead>
                  <TableHead className="num">Amount</TableHead>
                  <TableHead>Notes</TableHead>
                  <TableHead className="w-40" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell>
                      <div className="font-medium">{row.reference ?? row.doc_number}</div>
                      {flaggedIds.has(row.id) && (
                        <Badge variant="destructive" className="mt-1">
                          Does not match
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {fmtDate(row.invoice_date)}
                    </TableCell>
                    <TableCell className="num">{moneyExact(row.amount)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {row.notes ?? "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Can perm="procurement:write">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label="Query"
                            onClick={() => {
                              setQuerying(row.id);
                              setNote("");
                            }}
                          >
                            <X />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label="Accept"
                            onClick={() => void act(row.id, true)}
                          >
                            <Check />
                          </Button>
                        </div>
                      </Can>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <EmptyState
              icon={<Receipt />}
              title="Nothing waiting"
              hint="Invoices sent in through the supplier portal land here."
            />
          )}
        </CardContent>
      </Card>

      {querying && (
        <Card className="mt-4">
          <CardContent className="space-y-2 pt-4">
            <Label htmlFor="query-note">What is wrong with it</Label>
            <Input
              id="query-note"
              placeholder="Send the delivery note with it"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              The supplier sees this. A query with no reason comes back unchanged.
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setQuerying(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={!note.trim()}
                onClick={() => void act(querying, false, note)}
              >
                Send Back
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
