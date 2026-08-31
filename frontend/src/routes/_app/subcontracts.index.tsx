import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Handshake, HandCoins, ShieldWarning } from "@phosphor-icons/react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { StatCard } from "@/components/ui/stat-card";
import { TableSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useGetExpiring,
  useListAllSubcontracts,
  useRetentionRegister,
} from "@/lib/api/generated/endpoints";
import { fmtDate, money, moneyExact } from "@/lib/format";
import { cn } from "@/lib/utils";

type Tab = "packages" | "retention" | "compliance";

export const Route = createFileRoute("/_app/subcontracts/")({
  validateSearch: (search: Record<string, unknown>): { tab?: Tab } => ({
    tab: (["packages", "retention", "compliance"] as const).includes(search.tab as Tab)
      ? (search.tab as Tab)
      : undefined,
  }),
  component: SubcontractRegister,
});

const DOC_LABELS: Record<string, string> = {
  tax_clearance: "Tax Clearance",
  vat_registration: "VAT Registration",
  company_registration: "Company Registration",
  public_liability: "Public Liability",
  workmans_compensation: "Workman's Compensation",
  safety_certificate: "Safety Certificate",
  bank_confirmation: "Bank Confirmation",
  trade_licence: "Trade Licence",
  other: "Other",
};

const STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "outline"> = {
  awarded: "success",
  draft: "outline",
  completed: "outline",
  terminated: "destructive",
};

const TABS: { key: Tab; label: string }[] = [
  { key: "packages", label: "Packages" },
  { key: "retention", label: "Retention Held" },
  { key: "compliance", label: "Expiring Paperwork" },
];

function SubcontractRegister() {
  const { tab = "packages" } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const { data: packages, isLoading: loadingPackages } = useListAllSubcontracts({});
  const { data: retention, isLoading: loadingRetention } = useRetentionRegister();
  const { data: expiring, isLoading: loadingExpiring } = useGetExpiring({ days: 60 });

  const rows = packages ?? [];
  const live = rows.filter((row) => row.status === "awarded");
  const committed = rows.reduce((sum, row) => sum + Number(row.value), 0);
  const held = (retention ?? []).reduce(
    (sum, row) => sum + Number(row.retention_outstanding),
    0,
  );
  const lapsed = (expiring ?? []).filter((row) => row.state === "expired").length;

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-xl font-semibold tracking-tight">Subcontracts</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Work let out across every job, what is still being held back, and whose paperwork is
          about to stop them.
        </p>
      </div>

      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Packages" value={rows.length} icon={<Handshake />} sub="all jobs" />
        <StatCard label="Live" value={live.length} sub="awarded and running" />
        <StatCard label="Committed" value={money(committed)} tone="brand" />
        <StatCard
          label="Retention held"
          value={money(held)}
          icon={<HandCoins />}
          sub={`${(retention ?? []).length} packages`}
          tone={held > 0 ? "negative" : "default"}
        />
      </div>

      <div className="mb-4 border-b">
        <nav className="-mb-px flex gap-1">
          {TABS.map((entry) => (
            <button
              key={entry.key}
              type="button"
              onClick={() => void navigate({ search: { tab: entry.key } })}
              className={cn(
                "border-b-2 px-3.5 py-2 text-sm font-medium transition-colors",
                tab === entry.key
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {entry.label}
              {entry.key === "compliance" && lapsed > 0 && (
                <span className="ml-1.5 rounded-full bg-destructive/10 px-1.5 text-xs text-destructive">
                  {lapsed}
                </span>
              )}
            </button>
          ))}
        </nav>
      </div>

      {tab === "packages" && (
        <Card>
          <CardContent className="p-0">
            {loadingPackages && !packages ? (
              <TableSkeleton columns={7} />
            ) : rows.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Number</TableHead>
                    <TableHead>Package</TableHead>
                    <TableHead>Subcontractor</TableHead>
                    <TableHead className="text-right">Value</TableHead>
                    <TableHead className="text-right">Retention</TableHead>
                    <TableHead>Ends</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell className="font-mono text-xs">
                        <Link
                          to="/subcontracts/$subcontractId"
                          params={{ subcontractId: row.id }}
                          className="hover:underline"
                        >
                          {row.doc_number}
                        </Link>
                      </TableCell>
                      <TableCell className="font-medium">
                        <Link
                          to="/subcontracts/$subcontractId"
                          params={{ subcontractId: row.id }}
                          className="hover:underline"
                        >
                          {row.title}
                        </Link>
                      </TableCell>
                      <TableCell className="text-sm">{row.supplier_name ?? "—"}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {moneyExact(row.value)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {Number(row.retention_pct)}%
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {row.ends_on ? fmtDate(row.ends_on) : "—"}
                      </TableCell>
                      <TableCell>
                        <Badge variant={STATUS_VARIANT[row.status] ?? "outline"}>
                          {row.status}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <EmptyState
                icon={<Handshake />}
                title="Nothing let out yet"
                hint="Every package is created from a project's Subcontracts tab."
              />
            )}
          </CardContent>
        </Card>
      )}

      {tab === "retention" && (
        <Card>
          <CardContent className="p-0">
            <div className="border-b px-4 py-2.5 text-xs text-muted-foreground">
              Money withheld from subcontractors that has not been given back. It belongs to
              them, and nothing on a project screen shows it — so without this list it is only
              found when somebody rings up and asks.
            </div>
            {loadingRetention && !retention ? (
              <TableSkeleton columns={6} />
            ) : (retention ?? []).length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Number</TableHead>
                    <TableHead>Package</TableHead>
                    <TableHead>Subcontractor</TableHead>
                    <TableHead>Ends</TableHead>
                    <TableHead className="text-right">Certified</TableHead>
                    <TableHead className="text-right">Still held</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(retention ?? []).map((row) => (
                    <TableRow key={row.subcontract_id}>
                      <TableCell className="font-mono text-xs">
                        <Link
                          to="/subcontracts/$subcontractId"
                          params={{ subcontractId: row.subcontract_id }}
                          className="hover:underline"
                        >
                          {row.doc_number}
                        </Link>
                      </TableCell>
                      <TableCell className="font-medium">{row.title}</TableCell>
                      <TableCell className="text-sm">{row.supplier_name ?? "—"}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {row.ends_on ? fmtDate(row.ends_on) : "Not set"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {moneyExact(row.certified)}
                      </TableCell>
                      <TableCell className="text-right font-medium tabular-nums">
                        {moneyExact(row.retention_outstanding)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <EmptyState
                icon={<HandCoins />}
                title="Nothing is being held"
                hint="Either nothing has been certified, or all of it has been released."
              />
            )}
          </CardContent>
        </Card>
      )}

      {tab === "compliance" && (
        <Card>
          <CardContent className="p-0">
            <div className="border-b px-4 py-2.5 text-xs text-muted-foreground">
              Certificates lapsing in the next 60 days, across every vendor. Chased before it
              stops a job rather than after.
            </div>
            {loadingExpiring && !expiring ? (
              <TableSkeleton columns={5} />
            ) : (expiring ?? []).length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Vendor</TableHead>
                    <TableHead>Document</TableHead>
                    <TableHead>Reference</TableHead>
                    <TableHead>Expires</TableHead>
                    <TableHead>State</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(expiring ?? []).map((row, index) => (
                    <TableRow key={`${row.supplier_id}-${row.doc_type}-${index}`}>
                      <TableCell className="font-medium">
                        <Link
                          to="/procurement/suppliers/$supplierId"
                          params={{ supplierId: row.supplier_id }}
                          className="hover:underline"
                        >
                          {row.supplier_name}
                        </Link>
                      </TableCell>
                      <TableCell>{DOC_LABELS[row.doc_type] ?? row.doc_type}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {row.reference ?? "—"}
                      </TableCell>
                      <TableCell className="text-sm">{fmtDate(row.expires_on)}</TableCell>
                      <TableCell>
                        {row.state === "expired" ? (
                          <Badge variant="destructive">
                            Expired {Math.abs(row.days_to_expiry)} days ago
                          </Badge>
                        ) : (
                          <Badge variant="warning">
                            {row.days_to_expiry === 0
                              ? "Expires today"
                              : `${row.days_to_expiry} days left`}
                          </Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <EmptyState
                icon={<ShieldWarning />}
                title="Nothing lapsing"
                hint="Every vendor's paperwork runs past the next 60 days."
              />
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
