import { keepPreviousData } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Bank } from "@phosphor-icons/react";
import { useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/list-state";
import { DEFAULT_PAGE_SIZE, PaginationBar } from "@/components/ui/pagination";
import { TableSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useGetAccountLedger } from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";

export const Route = createFileRoute("/_app/accounting/accounts/$accountId")({
  component: AccountLedger,
});

/** Everything that has moved through one account.
 *
 *  The running balance is the reason this is a page rather than a filter: it
 *  only means anything read in order, and it is the first thing anybody asks
 *  for when a total looks wrong. */
function AccountLedger() {
  const { accountId } = Route.useParams();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const query = useGetAccountLedger(
    accountId,
    { page, page_size: pageSize },
    { query: { placeholderData: keepPreviousData } },
  );

  const rows = query.data?.items ?? [];
  const closing = rows.length ? rows[rows.length - 1]?.balance_after : null;

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Accounting", to: "/accounting", search: { tab: "accounts" } },
          { label: "Account ledger" },
        ]}
      />

      <div className="mb-5">
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <Bank /> Account ledger
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Every movement through this account, oldest first.
          {closing != null && (
            <>
              {" · "}balance carried {moneyExact(closing)}
            </>
          )}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Movements</CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Oldest first, because a running balance read backwards is not a running
            balance.
          </p>
        </CardHeader>
        <CardContent className="p-0">
          {query.isError ? (
            <ErrorState error={query.error} onRetry={() => void query.refetch()} />
          ) : query.isLoading && !query.data ? (
            <TableSkeleton columns={6} />
          ) : rows.length ? (
            <Table maxHeight="60vh">
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Journal</TableHead>
                  <TableHead>Narration</TableHead>
                  <TableHead className="num">Debit</TableHead>
                  <TableHead className="num">Credit</TableHead>
                  <TableHead className="num">Balance</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row, index) => (
                  <TableRow key={`${row.journal_id}-${index}`}>
                    <TableCell className="whitespace-nowrap text-sm">
                      {fmtDate(row.entry_date)}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {row.journal_id ? (
                        <Link
                          to="/accounting/journals/$journalId"
                          params={{ journalId: row.journal_id }}
                          className="hover:underline"
                        >
                          {row.doc_number}
                        </Link>
                      ) : (
                        row.doc_number
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {row.description ?? "—"}
                    </TableCell>
                    <TableCell className="num">
                      {Number(row.debit ?? 0) ? moneyExact(row.debit) : "—"}
                    </TableCell>
                    <TableCell className="num">
                      {Number(row.credit ?? 0) ? moneyExact(row.credit) : "—"}
                    </TableCell>
                    <TableCell className="num font-medium">
                      {moneyExact(row.balance_after)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <EmptyState
              icon={<Bank />}
              title="Nothing has moved through this account"
              hint="It exists on the chart, but nothing has been posted to it yet."
            />
          )}
          <PaginationBar
            page={page}
            pageSize={pageSize}
            total={query.data?.total}
            onPageChange={setPage}
            onPageSizeChange={(size) => {
              setPageSize(size);
              setPage(1);
            }}
          />
        </CardContent>
      </Card>
    </div>
  );
}
