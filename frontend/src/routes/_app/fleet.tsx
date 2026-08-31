import { keepPreviousData } from "@tanstack/react-query";
import { Link, createFileRoute } from "@tanstack/react-router";
import { Drop, Gauge, Plus, Truck, UploadSimple, Warning, Wrench } from "@phosphor-icons/react";
import { z } from "zod";
import { useState } from "react";
import { PageHeader } from "@/components/layout/AppShell";
import { Can } from "@/components/layout/Can";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { DEFAULT_PAGE_SIZE, PaginationBar } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
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
import { Tooltip } from "@/components/ui/tooltip";
import { RegisterDialog, TelematicsDialog } from "@/features/fleet/FleetDialogs";
import { Assets, Availability, Certificates, Costing } from "@/features/fleet/PlantTabs";
import {
  useGetFleetSummary,
  useGetFuelExceptions,
  useGetMaintenanceDue,
  useGetUtilisation,
  useListEquipment,
} from "@/lib/api/generated/endpoints";
import { fmtDate } from "@/lib/format";
import { cn } from "@/lib/utils";

const searchSchema = z.object({
  tab: z
    .enum([
      "register",
      "utilisation",
      "fuel",
      "maintenance",
      "availability",
      "certificates",
      "assets",
      "costing",
    ])
    .optional()
    .default("register"),
  page: z.number().int().min(1).optional().default(1),
  status: z.string().optional(),
});

export const Route = createFileRoute("/_app/fleet")({
  validateSearch: searchSchema,
  component: FleetPage,
});

const STATUS_TONE: Record<string, "success" | "secondary" | "warning" | "outline"> = {
  on_site: "success",
  available: "secondary",
  workshop: "warning",
  standing: "warning",
  off_hired: "outline",
  disposed: "outline",
};

function FleetPage() {
  const { tab } = Route.useSearch();
  const navigate = Route.useNavigate();
  const { data: summary } = useGetFleetSummary();
  const [registerOpen, setRegisterOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  const tabs = [
    { key: "register", label: "The Yard" },
    { key: "utilisation", label: "Utilisation" },
    {
      key: "fuel",
      label: "Fuel",
      badge: summary?.fuel_exceptions ? Number(summary.fuel_exceptions) : 0,
    },
    {
      key: "maintenance",
      label: "Maintenance",
      badge: summary?.maintenance_due ? Number(summary.maintenance_due) : 0,
    },
    { key: "availability", label: "Availability" },
    { key: "certificates", label: "Certificates" },
    { key: "assets", label: "Asset Register" },
    { key: "costing", label: "Costing" },
  ] as const;

  return (
    <div>
      <PageHeader
        title="Fleet"
        description="Where every machine is, what it burned, and what it needs"
        actions={
          <Can perm="inventory:write">
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setImportOpen(true)}>
                <UploadSimple /> Import Readings
              </Button>
              <Button size="sm" onClick={() => setRegisterOpen(true)}>
                <Plus /> Register Machine
              </Button>
            </div>
          </Can>
        }
      />

      <RegisterDialog open={registerOpen} onOpenChange={setRegisterOpen} />
      <TelematicsDialog open={importOpen} onOpenChange={setImportOpen} />

      {summary && (
        <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Machines" value={Number(summary.total)} icon={<Truck />} sub="on the register" />
          <StatCard
            label="On Site"
            value={Number(summary.on_site)}
            icon={<Truck />}
            tone="positive"
          />
          <StatCard
            label="Service Due"
            value={Number(summary.maintenance_due)}
            icon={<Wrench />}
            tone={Number(summary.maintenance_due) > 0 ? "negative" : "default"}
          />
          <StatCard
            label="Fuel To Review"
            value={Number(summary.fuel_exceptions)}
            icon={<Drop />}
            tone={Number(summary.fuel_exceptions) > 0 ? "negative" : "default"}
          />
        </div>
      )}

      <div className="mb-4 border-b">
        <nav className="-mb-px flex flex-wrap gap-1">
          {tabs.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => void navigate({ search: { tab: item.key, page: 1 } })}
              className={cn(
                "flex items-center gap-1.5 border-b-2 px-3.5 py-2 text-sm font-medium transition-colors",
                tab === item.key
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:border-border hover:text-foreground",
              )}
            >
              {item.label}
              {"badge" in item && item.badge > 0 && (
                <Badge variant="warning">{item.badge}</Badge>
              )}
            </button>
          ))}
        </nav>
      </div>

      {tab === "register" && <Register />}
      {tab === "utilisation" && <Utilisation />}
      {tab === "fuel" && <Fuel />}
      {tab === "maintenance" && <Maintenance />}
      {tab === "availability" && <Availability />}
      {tab === "certificates" && <Certificates />}
      {tab === "assets" && <Assets />}
      {tab === "costing" && <Costing />}
    </div>
  );
}

function Register() {
  const { page, status } = Route.useSearch();
  const navigate = Route.useNavigate();
  const { data, isLoading } = useListEquipment(
    { page, page_size: DEFAULT_PAGE_SIZE, status: (status || undefined) as never },
    { query: { placeholderData: keepPreviousData } },
  );

  return (
    <div>
      <div className="mb-3 flex gap-2">
        <Select
          className="w-48"
          value={status ?? ""}
          onChange={(e) =>
            void navigate({
              search: (prev) => ({ ...prev, status: e.target.value || undefined, page: 1 }),
            })
          }
        >
          <option value="">Anywhere</option>
          <option value="on_site">On site</option>
          <option value="available">In the yard</option>
          <option value="workshop">In the workshop</option>
          <option value="standing">Standing</option>
        </Select>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-24">Code</TableHead>
                <TableHead>Machine</TableHead>
                <TableHead>Registration</TableHead>
                <TableHead>Where</TableHead>
                <TableHead className="text-right">Meter</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && !data && <TableSkeleton columns={6} />}
              {data?.items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="p-0">
                    <EmptyState
                      icon={<Truck />}
                      title="No machines yet"
                      hint="Add plant to track hours, fuel and servicing against each job."
                    />
                  </TableCell>
                </TableRow>
              )}
              {data?.items.map((machine) => (
                <TableRow key={machine.id}>
                  <TableCell className="font-mono text-xs">
                    <Link
                      to="/fleet/$equipmentId"
                      params={{ equipmentId: machine.id }}
                      className="underline-offset-2 hover:text-primary hover:underline"
                    >
                      {machine.code}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <div className="font-medium">{machine.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {[machine.make, machine.model].filter(Boolean).join(" ") ||
                        machine.category.replace(/_/g, " ")}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">{machine.registration ?? "—"}</TableCell>
                  <TableCell className="text-sm">
                    {machine.current_project_name ?? "In the yard"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {Number(machine.current_meter).toLocaleString()}{" "}
                    <span className="text-xs text-muted-foreground">
                      {machine.meter_type === "hours" ? "hrs" : "km"}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Badge variant={STATUS_TONE[machine.status] ?? "secondary"}>
                      {machine.status.replace(/_/g, " ")}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <PaginationBar
            page={page}
            pageSize={DEFAULT_PAGE_SIZE}
            total={data?.total}
            onPageChange={(next) =>
              void navigate({ search: (prev) => ({ ...prev, page: next }) })
            }
          />
        </CardContent>
      </Card>
    </div>
  );
}

function Utilisation() {
  const { data } = useGetUtilisation({});
  if (!data) return <div className="h-64 animate-pulse rounded-lg border bg-muted/40" />;

  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Machine</TableHead>
              <TableHead className="text-right">Worked</TableHead>
              <TableHead className="text-right">Idle</TableHead>
              <TableHead className="text-right">Available</TableHead>
              <TableHead className="w-48">Utilisation</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((row) => {
              const pct = row.utilisation_pct === null ? null : Number(row.utilisation_pct);
              return (
                <TableRow key={String(row.equipment_id)}>
                  <TableCell>
                    <div className="font-medium">{String(row.name)}</div>
                    <div className="font-mono text-xs text-muted-foreground">
                      {String(row.code)}
                    </div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {row.worked === null ? "—" : Number(row.worked).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {Number(row.idle_hours) || "—"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {Number(row.available_hours).toLocaleString()}
                  </TableCell>
                  <TableCell>
                    {pct === null ? (
                      <Tooltip content="Fewer than two readings in this window, so there is nothing to measure. Not the same as idle.">
                        <span className="text-xs text-muted-foreground">Not measured</span>
                      </Tooltip>
                    ) : (
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                          <div
                            className={cn(
                              "h-full rounded-full",
                              pct < 30 ? "bg-destructive" : pct < 60 ? "bg-warning" : "bg-success",
                            )}
                            style={{ width: `${Math.min(pct, 100)}%` }}
                          />
                        </div>
                        <span className="w-12 text-right text-xs tabular-nums">{pct}%</span>
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function Fuel() {
  const { data } = useGetFuelExceptions({});
  if (!data) return <div className="h-64 animate-pulse rounded-lg border bg-muted/40" />;

  if (data.length === 0) {
    return (
      <Card>
        <CardContent className="p-0">
          <EmptyState
            icon={<Drop />}
            title="Nothing unusual"
            hint="Every fill is in line with what that machine normally burns for the hours it ran."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      <p className="rounded-lg border border-warning/40 bg-warning/5 p-3 text-sm">
        <Warning className="mr-1.5 inline size-4 text-warning" />
        These fills used far more than the machine normally does for the hours it ran. Worth
        asking about — a blocked filter and a siphon look the same here.
      </p>
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Machine</TableHead>
                <TableHead>Date</TableHead>
                <TableHead className="text-right">Litres</TableHead>
                <TableHead className="text-right">Hours run</TableHead>
                <TableHead className="text-right">Rate</TableHead>
                <TableHead className="text-right">Normal</TableHead>
                <TableHead>Operator</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((row, index) => (
                <TableRow key={`${row.fuel_log_id}-${index}`}>
                  <TableCell>
                    <div className="font-medium">{String(row.name)}</div>
                    <div className="font-mono text-xs text-muted-foreground">
                      {String(row.code)}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">{fmtDate(String(row.log_date))}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {Number(row.litres).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {Number(row.meter_run).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right font-semibold tabular-nums text-destructive">
                    {Number(row.rate)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {Number(row.baseline)}
                  </TableCell>
                  <TableCell className="text-sm">
                    {row.operator ? String(row.operator) : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

function Maintenance() {
  const { data } = useGetMaintenanceDue();
  if (!data) return <div className="h-64 animate-pulse rounded-lg border bg-muted/40" />;

  if (data.length === 0) {
    return (
      <Card>
        <CardContent className="p-0">
          <EmptyState
            icon={<Gauge />}
            title="Nothing due"
            hint="No machine is at or near a service interval."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Machine</TableHead>
              <TableHead>Service</TableHead>
              <TableHead className="text-right">Meter now</TableHead>
              <TableHead className="text-right">Due at</TableHead>
              <TableHead className="text-right">Left</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((row) => (
              <TableRow key={String(row.schedule_id)}>
                <TableCell>
                  <Link
                    to="/fleet/$equipmentId"
                    params={{ equipmentId: String(row.equipment_id) }}
                    className="font-medium underline-offset-2 hover:text-primary hover:underline"
                  >
                    {String(row.name)}
                  </Link>
                  <div className="font-mono text-xs text-muted-foreground">
                    {String(row.code)}
                  </div>
                </TableCell>
                <TableCell className="text-sm">{String(row.service)}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {Number(row.current_meter).toLocaleString()}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {row.meter_due_at ? Number(row.meter_due_at).toLocaleString() : "—"}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {row.meter_remaining !== null && row.meter_remaining !== undefined
                    ? Number(row.meter_remaining)
                    : row.days_remaining !== null && row.days_remaining !== undefined
                      ? `${Number(row.days_remaining)}d`
                      : "—"}
                </TableCell>
                <TableCell>
                  <Badge variant={row.status === "overdue" ? "destructive" : "warning"}>
                    {String(row.status).replace(/_/g, " ")}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
