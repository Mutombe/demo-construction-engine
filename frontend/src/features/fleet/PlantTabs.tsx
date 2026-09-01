import { keepPreviousData, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Coins, ShieldWarning, TrendDown, Warning } from "@phosphor-icons/react";
import { useState } from "react";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DEFAULT_PAGE_SIZE, PaginationBar } from "@/components/ui/pagination";
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
import { Tooltip } from "@/components/ui/tooltip";
import { errDetail } from "@/lib/api/errors";
import {
  useGetAssetRegister,
  useGetAvailability,
  useGetExpiringCertificates,
  useGetRecovery,
  useGetSettings,
  useRunDepreciation,
  useRunRecharge,
} from "@/lib/api/generated/endpoints";
import { fmtDate, money, moneyExact } from "@/lib/format";
import { toast } from "@/lib/toast";

const CERT_LABELS: Record<string, string> = {
  insurance: "Insurance",
  roadworthiness: "Roadworthiness",
  thorough_examination: "Thorough Examination",
  fitness: "Fitness",
  calibration: "Calibration",
  operator_licence: "Operator Licence",
  other: "Other",
};

/** First of the month, since every run is a month. */
function thisMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
}

function monthsAgo(count: number) {
  const now = new Date();
  now.setMonth(now.getMonth() - count);
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
}

// --- The asset register ------------------------------------------------------

export function Assets() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const query = useGetAssetRegister(
    { page, page_size: pageSize },
    { query: { placeholderData: keepPreviousData } },
  );
  const { data, isLoading } = query;
  const rows = data?.items ?? [];

  const carried = rows.reduce((sum, row) => sum + Number(row.net_book_value ?? 0), 0);
  const unpriced = rows.filter((row) => row.purchase_cost == null).length;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard label="Machines" value={data?.total ?? 0} sub="on the register" />
        <StatCard label="Carried At" value={money(carried)} tone="brand" sub="this page" />
        <StatCard
          label="No Cost Entered"
          value={unpriced}
          sub={unpriced ? "cannot be depreciated" : "all priced"}
          tone={unpriced ? "negative" : "default"}
        />
      </div>

      <DepreciationRunner />

      <Card>
        <CardContent className="p-0">
          {query.isError ? (
            <ErrorState error={query.error} onRetry={() => void query.refetch()} />
          ) : isLoading && !data ? (
            <TableSkeleton columns={7} />
          ) : rows.length ? (
            <Table maxHeight="60vh">
              <TableHeader>
                <TableRow>
                  <TableHead>Machine</TableHead>
                  <TableHead>Bought</TableHead>
                  <TableHead className="num">Cost</TableHead>
                  <TableHead className="num">Residual</TableHead>
                  <TableHead className="num">Life</TableHead>
                  <TableHead className="num">Written off</TableHead>
                  <TableHead className="num">Book value</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.equipment_id}>
                    <TableCell>
                      <Link
                        to="/fleet/$equipmentId"
                        params={{ equipmentId: row.equipment_id }}
                        className="font-medium hover:underline"
                      >
                        {row.code}
                      </Link>
                      <div className="text-xs text-muted-foreground">{row.name}</div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {row.purchase_date ? fmtDate(row.purchase_date) : "—"}
                    </TableCell>
                    <TableCell className="num">
                      {row.purchase_cost ? moneyExact(row.purchase_cost) : "—"}
                    </TableCell>
                    <TableCell className="num text-muted-foreground">
                      {row.residual_value ? moneyExact(row.residual_value) : "—"}
                    </TableCell>
                    <TableCell className="num text-muted-foreground">
                      {row.useful_life_months ? `${row.useful_life_months} mo` : "—"}
                    </TableCell>
                    <TableCell className="num text-muted-foreground">
                      {moneyExact(row.accumulated_depreciation)}
                    </TableCell>
                    <TableCell className="num font-medium">
                      {row.net_book_value != null ? (
                        moneyExact(row.net_book_value)
                      ) : (
                        <Tooltip content="No purchase cost was ever entered, so there is nothing to carry.">
                          <span className="text-muted-foreground">Not priced</span>
                        </Tooltip>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <EmptyState icon={<TrendDown />} title="Nothing on the register" />
          )}
          <PaginationBar
            page={page}
            pageSize={pageSize}
            total={data?.total}
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

function DepreciationRunner() {
  const queryClient = useQueryClient();
  const run = useRunDepreciation();
  const [period, setPeriod] = useState(thisMonth());
  const [result, setResult] = useState<{
    posted: number;
    already_done: number;
    total: string | number;
    not_depreciated: string[];
  } | null>(null);

  const go = async () => {
    try {
      const data = await run.mutateAsync({ data: { period_start: period } });
      await queryClient.invalidateQueries();
      setResult(data as never);
      toast.success(`${data.posted} machines written down`);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Card>
      <CardContent className="flex flex-wrap items-end gap-3 py-4">
        <div className="space-y-1.5">
          <Label htmlFor="dep-period">Depreciate month</Label>
          <Input
            id="dep-period"
            type="month"
            value={period.slice(0, 7)}
            onChange={(e) => setPeriod(`${e.target.value}-01`)}
            className="w-40"
          />
        </div>
        <Can perm="inventory:write">
          <Button disabled={run.isPending} onClick={() => void go()}>
            Run Depreciation
          </Button>
        </Can>
        <p className="flex-1 text-xs text-muted-foreground">
          Straight line, and only where a cost and a life were entered. Running the same month
          again changes nothing.
        </p>
        {result && (
          <div className="w-full rounded-md border px-3 py-2 text-sm">
            <span className="font-medium">{result.posted} posted</span>
            {result.already_done > 0 && (
              <span className="ml-2 text-muted-foreground">
                {result.already_done} already done
              </span>
            )}
            <span className="ml-2 tabular-nums">{moneyExact(result.total)}</span>
            {result.not_depreciated.length > 0 && (
              <div className="mt-1 text-xs text-muted-foreground">
                Not depreciated, no cost or life entered:{" "}
                {result.not_depreciated.join(", ")}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// --- Availability ------------------------------------------------------------

export function Availability() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const start = monthsAgo(3);
  const end = new Date().toISOString().slice(0, 10);
  const query = useGetAvailability(
    { start, end, page, page_size: pageSize },
    { query: { placeholderData: keepPreviousData } },
  );
  const { data, isLoading } = query;
  const rows = data?.items ?? [];

  return (
    <Card>
      <CardContent className="p-0">
        <div className="border-b px-4 py-2.5 text-xs text-muted-foreground">
          Last three months. Measured against the days a machine was assigned to a site, not
          calendar days — one in the yard is unused, not unavailable, and adding the two together
          makes both numbers meaningless.
        </div>
        {query.isError ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        ) : isLoading && !data ? (
          <TableSkeleton columns={6} />
        ) : rows.length ? (
          <Table maxHeight="60vh">
            <TableHeader>
              <TableRow>
                <TableHead>Machine</TableHead>
                <TableHead className="num">Days on site</TableHead>
                <TableHead className="num">Worked</TableHead>
                <TableHead className="num">Downtime</TableHead>
                <TableHead className="num">Breakdowns</TableHead>
                <TableHead className="num">Available</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.equipment_id}>
                  <TableCell>
                    <Link
                      to="/fleet/$equipmentId"
                      params={{ equipmentId: row.equipment_id }}
                      className="font-medium hover:underline"
                    >
                      {row.code}
                    </Link>
                    <div className="text-xs text-muted-foreground">{row.name}</div>
                  </TableCell>
                  <TableCell className="num text-muted-foreground">{row.assigned_days}</TableCell>
                  <TableCell className="num text-muted-foreground">
                    {row.metered != null ? Number(row.metered).toLocaleString() : "—"}
                  </TableCell>
                  <TableCell className="num">
                    {Number(row.downtime_hours) > 0 ? `${Number(row.downtime_hours)} hrs` : "—"}
                  </TableCell>
                  <TableCell className="num text-muted-foreground">
                    {row.breakdowns || "—"}
                  </TableCell>
                  <TableCell className="num">
                    {row.availability_pct == null ? (
                      <Tooltip content="It was never sent to a site in this window, so there is no time it was meant to be working.">
                        <span className="text-muted-foreground">Not on a job</span>
                      </Tooltip>
                    ) : (
                      <span
                        className={
                          row.availability_pct < 85 ? "font-medium text-warning" : undefined
                        }
                      >
                        {row.availability_pct}%
                      </span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <EmptyState icon={<Warning />} title="Nothing to measure yet" />
        )}
        <PaginationBar
          page={page}
          pageSize={pageSize}
          total={data?.total}
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setPage(1);
          }}
        />
      </CardContent>
    </Card>
  );
}

// --- Costing -----------------------------------------------------------------

export function Costing() {
  const queryClient = useQueryClient();
  const { data: settings } = useGetSettings();
  const run = useRunRecharge();
  const [period, setPeriod] = useState(thisMonth());
  const start = monthsAgo(3);
  const end = new Date().toISOString().slice(0, 10);
  const { data: recovery } = useGetRecovery({ start, end });

  const internalHire = settings?.plant_costing_mode === "internal_hire";

  const go = async () => {
    try {
      const data = await run.mutateAsync({ data: { period_start: period } });
      await queryClient.invalidateQueries();
      toast.success(
        data.recharged
          ? `${data.recharged} charges raised, ${moneyExact(data.total)}`
          : "Nothing to charge for that month",
      );
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <div className="space-y-4">
      {!internalHire && (
        <div className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning/5 px-3 py-2.5 text-sm">
          <ShieldWarning weight="fill" className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <div>
            <p className="font-medium text-warning">Plant is costed directly</p>
            <p className="mt-0.5 text-muted-foreground">
              Fuel and repairs go straight to whichever job the machine was on, so jobs never
              bear the cost of owning it and plant always looks cheaper than it is. Recharging as
              well would charge a job twice for the same diesel, so it is refused while this
              mode is set. An administrator can switch to internal hire in Settings.
            </p>
          </div>
        </div>
      )}

      {recovery && (
        <div className="grid gap-3 sm:grid-cols-3">
          <StatCard
            label="Yard Cost"
            value={money(recovery.pooled)}
            sub="fuel, workshop, depreciation"
          />
          <StatCard label="Charged To Jobs" value={money(recovery.recovered)} tone="brand" />
          <StatCard
            label={Number(recovery.under_recovered) >= 0 ? "Under Recovered" : "Over Recovered"}
            value={money(Math.abs(Number(recovery.under_recovered)))}
            icon={<Coins />}
            tone={Number(recovery.under_recovered) > 0 ? "negative" : "positive"}
            sub="last three months"
          />
        </div>
      )}

      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 py-4">
          <div className="space-y-1.5">
            <Label htmlFor="rc-period">Charge month</Label>
            <Input
              id="rc-period"
              type="month"
              value={period.slice(0, 7)}
              onChange={(e) => setPeriod(`${e.target.value}-01`)}
              className="w-40"
            />
          </div>
          <Can perm="inventory:write">
            <Button disabled={!internalHire || run.isPending} onClick={() => void go()}>
              Run Recharge
            </Button>
          </Can>
          <p className="flex-1 text-xs text-muted-foreground">
            Charges each job for the hours its machines ran, at the machine's rate. Safe to run
            again — what has already been charged is left alone.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="py-4 text-sm text-muted-foreground">
          <p>
            Under-recovery means the rates are too low or the machines stood idle. Over-recovery
            means jobs are subsidising the yard. Either way it is the only figure that says
            whether owning the plant beats hiring it, and it does not exist anywhere else.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

// --- Certificates ------------------------------------------------------------

export function Certificates() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const query = useGetExpiringCertificates(
    { days: 60 },
    { query: { placeholderData: keepPreviousData } },
  );
  const { data, isLoading } = query;
  const all = data ?? [];
  const rows = all.slice((page - 1) * pageSize, page * pageSize);

  return (
    <Card>
      <CardContent className="p-0">
        <div className="border-b px-4 py-2.5 text-xs text-muted-foreground">
          Certificates lapsing in the next 60 days. An expired one stops the machine going to
          site; lifting gear is stopped by a missing examination too.
        </div>
        {query.isError ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        ) : isLoading && !data ? (
          <TableSkeleton columns={5} />
        ) : rows.length ? (
          <Table maxHeight="60vh">
            <TableHeader>
              <TableRow>
                <TableHead>Machine</TableHead>
                <TableHead>Document</TableHead>
                <TableHead>Reference</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead>State</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row, index) => (
                <TableRow key={`${row.equipment_id}-${row.cert_type}-${index}`}>
                  <TableCell>
                    <Link
                      to="/fleet/$equipmentId"
                      params={{ equipmentId: row.equipment_id }}
                      className="font-medium hover:underline"
                    >
                      {row.code}
                    </Link>
                    <div className="text-xs text-muted-foreground">{row.name}</div>
                  </TableCell>
                  <TableCell>{CERT_LABELS[row.cert_type] ?? row.cert_type}</TableCell>
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
            hint="Every machine's paperwork runs past the next 60 days."
          />
        )}
        <PaginationBar
          page={page}
          pageSize={pageSize}
          total={all.length}
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setPage(1);
          }}
        />
      </CardContent>
    </Card>
  );
}
