import { keepPreviousData } from "@tanstack/react-query";
import { Link, createFileRoute, redirect } from "@tanstack/react-router";
import { Bank, CheckCircle, Scales, Warning } from "@phosphor-icons/react";
import { z } from "zod";
import { PageHeader } from "@/components/layout/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { DEFAULT_PAGE_SIZE, PaginationBar } from "@/components/ui/pagination";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip } from "@/components/ui/tooltip";
import { useState } from "react";
import { Ageing } from "@/features/accounting/Ageing";
import { PaySupplierDialog } from "@/features/accounting/PaySupplierDialog";
import { useAuthStore } from "@/features/auth/store";
import { errDetail } from "@/lib/api/errors";
import {
  useGetBalanceSheet,
  useGetPayables,
  useGetReceivables,
  useGetIncomeStatement,
  useGetTrialBalance,
  useListAccounts,
  useListJournals,
  useListUnposted,
  usePostUnposted,
} from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

const searchSchema = z.object({
  tab: z
    .enum([
      "summary",
      "receivables",
      "payables",
      "trial-balance",
      "income",
      "balance-sheet",
      "journals",
      "accounts",
    ])
    .optional()
    .default("summary"),
});

export const Route = createFileRoute("/_app/accounting")({
  validateSearch: searchSchema,
  beforeLoad: () => {
    const role = useAuthStore.getState().user?.role;
    // The books show company-wide position, which most roles have no business
    // seeing. The API refuses them anyway; this avoids a page of 403s.
    if (role !== "admin" && role !== "project_manager") throw redirect({ to: "/" });
  },
  component: AccountingPage,
});

const TABS = [
  { key: "summary", label: "Summary" },
  { key: "receivables", label: "Owed to Us" },
  { key: "payables", label: "We Owe" },
  { key: "trial-balance", label: "Trial Balance" },
  { key: "income", label: "Income Statement" },
  { key: "balance-sheet", label: "Balance Sheet" },
  { key: "journals", label: "Journals" },
  { key: "accounts", label: "Chart of Accounts" },
] as const;

function AccountingPage() {
  const { tab } = Route.useSearch();
  const navigate = Route.useNavigate();

  return (
    <div>
      <PageHeader
        title="Accounting"
        description="The general ledger behind every cost, certificate and delivery"
      />

      <div className="mb-4 border-b">
        <nav className="-mb-px flex flex-wrap gap-1">
          {TABS.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => void navigate({ search: { tab: item.key } })}
              className={cn(
                "border-b-2 px-3.5 py-2 text-sm font-medium transition-colors",
                tab === item.key
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:border-border hover:text-foreground",
              )}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </div>

      {tab === "summary" && <Summary />}
      {tab === "receivables" && <Receivables />}
      {tab === "payables" && <Payables />}
      {tab === "trial-balance" && <TrialBalance />}
      {tab === "income" && <Income />}
      {tab === "balance-sheet" && <Sheet />}
      {tab === "journals" && <Journals />}
      {tab === "accounts" && <Accounts />}
    </div>
  );
}

/** The control that makes a posting failure visible instead of silent. */
function LedgerHealth() {
  const { data: unposted } = useListUnposted();
  const post = usePostUnposted();

  if (!unposted || unposted.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-success/30 bg-success/5 p-3 text-sm">
        <CheckCircle className="size-4 shrink-0 text-success" weight="fill" />
        Every cost has a journal behind it
      </div>
    );
  }

  const total = unposted.reduce((sum, entry) => sum + Number(entry.amount), 0);
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-warning/40 bg-warning/5 p-3 text-sm">
      <Warning className="size-4 shrink-0 text-warning" weight="fill" />
      <span className="flex-1">
        {unposted.length} {unposted.length === 1 ? "cost has" : "costs have"} no journal,
        totalling {moneyExact(total)}. The ledger is understated until they are posted.
      </span>
      <Button
        size="sm"
        disabled={post.isPending}
        onClick={async () => {
          try {
            const result = await post.mutateAsync();
            toast.success(`Posted ${result.posted}`);
          } catch (err) {
            toast.error(errDetail(err));
          }
        }}
      >
        Post Them
      </Button>
    </div>
  );
}

function Summary() {
  const { data: sheet } = useGetBalanceSheet({});
  const { data: income } = useGetIncomeStatement({});

  const cards = [
    { label: "Revenue this year", value: income?.revenue_total, tone: "text-success" },
    { label: "Cost of works", value: income?.expense_total, tone: "" },
    {
      label: "Result",
      value: income?.net_result,
      tone: Number(income?.net_result ?? 0) < 0 ? "text-destructive" : "text-success",
    },
    { label: "Owed by clients", value: findAmount(sheet?.assets, "1100"), tone: "" },
    { label: "Retention held", value: findAmount(sheet?.assets, "1200"), tone: "" },
    { label: "Owed to suppliers", value: findAmount(sheet?.liabilities, "2000"), tone: "" },
  ];

  return (
    <div className="space-y-4">
      <LedgerHealth />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((card) => (
          <Card key={card.label}>
            <CardContent className="p-4">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                {card.label}
              </p>
              <p className={cn("mt-1 text-xl font-semibold tabular-nums", card.tone)}>
                {moneyExact(card.value ?? 0)}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function findAmount(
  rows: { code: string; amount: string }[] | undefined,
  code: string,
): string {
  return rows?.find((row) => row.code === code)?.amount ?? "0";
}

function Receivables() {
  const { data } = useGetReceivables({});
  return (
    <Ageing
      data={data}
      emptyHint="Certificates appear here from the day they are issued until they are paid."
    />
  );
}

function Payables() {
  const { data } = useGetPayables({});
  const [paying, setPaying] = useState<{ id: string; name: string } | null>(null);
  return (
    <>
      <Ageing
        data={data}
        emptyHint="Orders appear here once they are received, until they are paid."
        onPay={(id, name) => setPaying({ id, name })}
      />
      <PaySupplierDialog
        supplierId={paying?.id ?? null}
        supplierName={paying?.name ?? ""}
        open={!!paying}
        onOpenChange={(open) => !open && setPaying(null)}
      />
    </>
  );
}

function TrialBalance() {
  const { data } = useGetTrialBalance({});
  if (!data) return <Skeleton />;

  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-20">Code</TableHead>
              <TableHead>Account</TableHead>
              <TableHead className="text-right">Debit</TableHead>
              <TableHead className="text-right">Credit</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="p-0">
                  <EmptyState
                    icon={<Scales />}
                    title="Nothing posted yet"
                    hint="Costs, certificates and deliveries write journals as they happen."
                  />
                </TableCell>
              </TableRow>
            )}
            {data.rows.map((row) => (
              <TableRow key={row.account_id}>
                <TableCell className="font-mono text-xs">{row.code}</TableCell>
                <TableCell>{row.name}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {Number(row.debit) ? moneyExact(row.debit) : "—"}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {Number(row.credit) ? moneyExact(row.credit) : "—"}
                </TableCell>
              </TableRow>
            ))}
            <TableRow className="border-t-2 font-semibold">
              <TableCell colSpan={2}>
                Totals
                {data.balanced ? (
                  <Badge variant="success" className="ml-2">
                    Balanced
                  </Badge>
                ) : (
                  <Tooltip content="Debits and credits disagree. Posting is broken and the books cannot be trusted until it is fixed.">
                    <Badge variant="destructive" className="ml-2">
                      Out of balance
                    </Badge>
                  </Tooltip>
                )}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {moneyExact(data.total_debit)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {moneyExact(data.total_credit)}
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function Income() {
  const { data } = useGetIncomeStatement({});
  if (!data) return <Skeleton />;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {fmtDate(data.start)} to {fmtDate(data.end)}
        </CardTitle>
      </CardHeader>
      <CardContent className="max-w-2xl space-y-5">
        <StatementBlock title="Revenue" rows={data.revenue} total={data.revenue_total} />
        <StatementBlock title="Cost of Works" rows={data.expenses} total={data.expense_total} />
        <div className="flex items-baseline justify-between border-t-2 pt-2">
          <span className="font-semibold">Result</span>
          <span
            className={cn(
              "text-lg font-semibold tabular-nums",
              Number(data.net_result) < 0 ? "text-destructive" : "text-success",
            )}
          >
            {moneyExact(data.net_result)}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

function Sheet() {
  const { data } = useGetBalanceSheet({});
  if (!data) return <Skeleton />;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">As at {fmtDate(data.as_at)}</CardTitle>
        {data.balanced ? (
          <Badge variant="success">Balanced</Badge>
        ) : (
          <Badge variant="destructive">Out of balance</Badge>
        )}
      </CardHeader>
      <CardContent className="max-w-2xl space-y-5">
        <StatementBlock title="Assets" rows={data.assets} total={data.asset_total} />
        <StatementBlock title="Liabilities" rows={data.liabilities} total={data.liability_total} />
        <StatementBlock title="Equity" rows={data.equity} total={data.equity_total} />
        <div className="flex items-baseline justify-between border-t pt-2 text-sm">
          <span className="text-muted-foreground">Result for the period</span>
          <span className="tabular-nums">{moneyExact(data.result_for_period)}</span>
        </div>
      </CardContent>
    </Card>
  );
}

function StatementBlock({
  title,
  rows,
  total,
}: {
  title: string;
  rows: { code: string; name: string; amount: string }[];
  total: string;
}) {
  return (
    <div>
      <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      <dl className="space-y-1">
        {rows.length === 0 && <p className="text-sm text-muted-foreground">Nothing yet</p>}
        {rows.map((row) => (
          <div key={row.code} className="flex items-baseline justify-between gap-4 text-sm">
            <dt className="truncate">
              <span className="mr-2 font-mono text-xs text-muted-foreground">{row.code}</span>
              {row.name}
            </dt>
            <dd className="shrink-0 tabular-nums">{moneyExact(row.amount)}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-1.5 flex items-baseline justify-between border-t pt-1.5 text-sm font-medium">
        <span>Total {title}</span>
        <span className="tabular-nums">{moneyExact(total)}</span>
      </div>
    </div>
  );
}

function Journals() {
  // The journal grows for the life of the company, so it has never been
  // something to fetch whole.
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const { data } = useListJournals(
    { page, page_size: pageSize },
    { query: { placeholderData: keepPreviousData } },
  );
  if (!data) return <Skeleton />;
  const rows = data.items;

  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Number</TableHead>
              <TableHead>Date</TableHead>
              <TableHead>Memo</TableHead>
              <TableHead>Raised by</TableHead>
              <TableHead className="text-right">Amount</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="p-0">
                  <EmptyState icon={<Bank />} title="No journals yet" />
                </TableCell>
              </TableRow>
            )}
            {rows.map((journal) => (
              <TableRow key={journal.id}>
                <TableCell className="font-mono text-xs">{journal.doc_number}</TableCell>
                <TableCell className="whitespace-nowrap text-sm">
                  {fmtDate(journal.journal_date)}
                </TableCell>
                <TableCell className="max-w-sm truncate text-sm">{journal.memo}</TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {journal.source.replace(/_/g, " ")}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {moneyExact(journal.total)}
                </TableCell>
                <TableCell>
                  <Badge
                    variant={
                      journal.status === "posted"
                        ? "success"
                        : journal.status === "reversed"
                          ? "outline"
                          : "secondary"
                    }
                  >
                    {journal.status}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <PaginationBar
          page={page}
          pageSize={pageSize}
          total={data.total}
          onPageChange={setPage}
          onPageSizeChange={(size: number) => {
            setPageSize(size);
            setPage(1);
          }}
        />
      </CardContent>
    </Card>
  );
}

function Accounts() {
  const { data } = useListAccounts({});
  if (!data) return <Skeleton />;

  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-20">Code</TableHead>
              <TableHead>Account</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Normally</TableHead>
              <TableHead className="text-right">Balance</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((account) => (
              <TableRow key={account.id}>
                <TableCell className="font-mono text-xs">{account.code}</TableCell>
                <TableCell>
                  <Link
                    to="/accounting"
                    search={{ tab: "journals" }}
                    className="underline-offset-2 hover:text-primary hover:underline"
                  >
                    {account.name}
                  </Link>
                  {account.description && (
                    <p className="text-xs text-muted-foreground">{account.description}</p>
                  )}
                </TableCell>
                <TableCell className="text-sm capitalize">{account.account_type}</TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {account.normal_balance}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {moneyExact(account.balance)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function Skeleton() {
  return <div className="h-64 animate-pulse rounded-lg border bg-muted/40" />;
}
