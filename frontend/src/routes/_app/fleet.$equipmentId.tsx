import { keepPreviousData, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import {
  Drop,
  Gauge,
  PencilSimple,
  Plus,
  ShieldCheck,
  Trash,
  Truck,
  WarningCircle,
  Wrench,
} from "@phosphor-icons/react";
import { useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Badge } from "@/components/ui/badge";
import { confirmDialog } from "@/components/ui/confirm";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DEFAULT_PAGE_SIZE, PaginationBar } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
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
import { CommentThread } from "@/features/comments/CommentThread";
import { errDetail } from "@/lib/api/errors";
import {
  useAssignEquipment,
  useCreateFuel,
  useCreateMaintenance,
  useCreateReading,
  useGetEquipment,
  useGetEquipmentCosts,
  useListAssignments,
  useListFuel,
  useListMaintenance,
  useListProjects,
  useListReadings,
  useListSchedules,
  useReleaseEquipment,
  useUpdateEquipment,
  useGetEquipmentCompliance,
  useAddCertificate,
  useRemoveCertificate,
} from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/_app/fleet/$equipmentId")({
  component: EquipmentDetail,
});

function EquipmentDetail() {
  const { equipmentId } = Route.useParams();
  const queryClient = useQueryClient();
  const machineQuery = useGetEquipment(equipmentId);
  const { data: machine } = machineQuery;
  const [readingPage, setReadingPage] = useState(1);
  const [fuelPage, setFuelPage] = useState(1);
  const [jobPage, setJobPage] = useState(1);
  const keep = { query: { placeholderData: keepPreviousData } };

  const { data: readings } = useListReadings(
    equipmentId,
    { page: readingPage, page_size: DEFAULT_PAGE_SIZE },
    keep,
  );
  const { data: fuel } = useListFuel(
    equipmentId,
    { page: fuelPage, page_size: DEFAULT_PAGE_SIZE },
    keep,
  );
  const { data: assignments } = useListAssignments(equipmentId, {
    page: 1,
    page_size: 10,
  });
  const { data: maintenance } = useListMaintenance(
    equipmentId,
    { page: jobPage, page_size: DEFAULT_PAGE_SIZE },
    keep,
  );
  const { data: schedules } = useListSchedules(equipmentId);
  const { data: costs } = useGetEquipmentCosts(equipmentId, {});
  const { data: compliance } = useGetEquipmentCompliance(equipmentId);
  const release = useReleaseEquipment();

  const [readingOpen, setReadingOpen] = useState(false);
  const [fuelOpen, setFuelOpen] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [serviceOpen, setServiceOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [certOpen, setCertOpen] = useState(false);

  if (machineQuery.isError) {
    return (
      <ErrorState
        error={machineQuery.error}
        onRetry={() => void machineQuery.refetch()}
      />
    );
  }
  if (!machine) return <PageSkeleton rows={4} />;

  const unit = machine.meter_type === "hours" ? "hrs" : "km";

  const bringBack = async () => {
    try {
      await release.mutateAsync({ equipmentId, params: {} });
      await queryClient.invalidateQueries();
      toast.success(`${machine.code} is back in the yard`);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <div>
      <Breadcrumbs items={[{ label: "Fleet", to: "/fleet" }, { label: machine.code }]} />

      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight">{machine.name}</h1>
            <Badge variant={machine.status === "on_site" ? "success" : "secondary"}>
              {machine.status.replace(/_/g, " ")}
            </Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            <span className="font-mono">{machine.code}</span>
            {machine.registration && <> · {machine.registration}</>}
            {(machine.make || machine.model) && (
              <> · {[machine.make, machine.model].filter(Boolean).join(" ")}</>
            )}
            {" · "}
            {machine.ownership === "hired" ? "Hired" : "Owned"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => setReadingOpen(true)}>
            <Gauge /> Reading
          </Button>
          <Button variant="outline" onClick={() => setFuelOpen(true)}>
            <Drop /> Fuel
          </Button>
          <Button variant="outline" onClick={() => setServiceOpen(true)}>
            <Wrench /> Service
          </Button>
          <Button variant="outline" onClick={() => setEditOpen(true)}>
            <PencilSimple /> Edit
          </Button>
          {machine.current_project_id ? (
            <Button variant="outline" onClick={() => void bringBack()}>
              Bring Back
            </Button>
          ) : (
            <Button onClick={() => setAssignOpen(true)}>
              <Truck /> Send to Site
            </Button>
          )}
        </div>
      </div>

      {compliance && !compliance.is_compliant && (
        <div
          className={
            (compliance.blocking ?? []).length
              ? "mb-4 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
              : "mb-4 flex items-start gap-2 rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-sm text-warning"
          }
        >
          <WarningCircle weight="fill" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            {(compliance.blocking ?? []).length
              ? `Cannot go to site: ${(compliance.blocking ?? [])
                  .map((c) => c.replace(/_/g, " "))
                  .join(", ")} has lapsed.`
              : `Paperwork not on file: ${(compliance.incomplete ?? [])
                  .map((c) => c.replace(/_/g, " "))
                  .join(", ")}. It can still be sent out, but somebody should chase this.`}
          </span>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Fuel</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {fuel?.items.length ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Date</TableHead>
                      <TableHead className="text-right">Litres</TableHead>
                      <TableHead className="text-right">Meter</TableHead>
                      <TableHead className="text-right">Cost</TableHead>
                      <TableHead>Operator</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {fuel.items.map((log) => (
                      <TableRow key={log.id}>
                        <TableCell className="text-sm">{fmtDate(log.log_date)}</TableCell>
                        <TableCell className="text-right tabular-nums">
                          {Number(log.litres).toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">
                          {log.meter ? Number(log.meter).toLocaleString() : "—"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {log.total_cost ? moneyExact(log.total_cost) : "—"}
                        </TableCell>
                        <TableCell className="text-sm">{log.operator ?? "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <EmptyState icon={<Drop />} title="No fuel logged" />
              )}
              {fuel && (
                <PaginationBar
                  page={fuel.page}
                  pageSize={fuel.page_size}
                  total={fuel.total}
                  onPageChange={setFuelPage}
                />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Meter readings</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {readings?.items.length ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Date</TableHead>
                      <TableHead className="text-right">Reading</TableHead>
                      <TableHead className="text-right">Idle</TableHead>
                      <TableHead>Source</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {readings.items.map((row) => (
                      <TableRow key={row.id}>
                        <TableCell className="text-sm">{fmtDate(row.reading_date)}</TableCell>
                        <TableCell className="text-right tabular-nums">
                          {Number(row.meter).toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">
                          {row.idle_hours ? Number(row.idle_hours) : "—"}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {row.source}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <EmptyState icon={<Gauge />} title="No readings yet" />
              )}
              {readings && (
                <PaginationBar
                  page={readings.page}
                  pageSize={readings.page_size}
                  total={readings.total}
                  onPageChange={setReadingPage}
                />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Workshop</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {maintenance?.items.length ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Date</TableHead>
                      <TableHead>Work</TableHead>
                      <TableHead className="text-right">Meter</TableHead>
                      <TableHead className="text-right">Cost</TableHead>
                      <TableHead className="text-right">Off the job</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {maintenance.items.map((job) => (
                      <TableRow key={job.id}>
                        <TableCell className="text-sm">{fmtDate(job.service_date)}</TableCell>
                        <TableCell className="text-sm">{job.description}</TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">
                          {job.meter ? Number(job.meter).toLocaleString() : "—"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {job.cost ? moneyExact(job.cost) : "—"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">
                          {job.downtime_hours ? `${Number(job.downtime_hours)} hrs` : "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <EmptyState icon={<Wrench />} title="Never been in" />
              )}
              {maintenance && (
                <PaginationBar
                  page={maintenance.page}
                  pageSize={maintenance.page_size}
                  total={maintenance.total}
                  onPageChange={setJobPage}
                />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Notes</CardTitle>
            </CardHeader>
            <CardContent>
              <CommentThread entityType="equipment" entityId={equipmentId} />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Where it stands</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row label="Meter" value={`${Number(machine.current_meter).toLocaleString()} ${unit}`} />
              <Row label="On" value={machine.current_project_name ?? "In the yard"} />
              <Row
                label="Hourly rate"
                value={machine.hourly_rate ? moneyExact(machine.hourly_rate) : "Not set"}
              />
              <Row
                label="Expected burn"
                value={
                  machine.expected_burn_rate
                    ? `${Number(machine.expected_burn_rate)} L/hr`
                    : "Learned from its own history"
                }
              />
              {machine.supplier_name && <Row label="Hired from" value={machine.supplier_name} />}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">What it costs</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {costs ? (
                <>
                  <Row label="Fuel" value={moneyExact(costs.fuel_cost)} />
                  <Row label="Workshop" value={moneyExact(costs.workshop_cost)} />
                  <div className="flex items-baseline justify-between border-t pt-2">
                    <span className="text-muted-foreground">Last 12 months</span>
                    <span className="font-semibold tabular-nums">
                      {moneyExact(costs.total_cost)}
                    </span>
                  </div>
                  <div className="flex items-baseline justify-between">
                    <span className="text-muted-foreground">
                      Per {costs.meter_type === "hours" ? "hour" : "km"} run
                    </span>
                    <span className="font-medium tabular-nums">
                      {costs.cost_per_unit ? moneyExact(costs.cost_per_unit) : "Not measured"}
                    </span>
                  </div>
                  {costs.hourly_rate && costs.cost_per_unit && (
                    <p
                      className={
                        Number(costs.cost_per_unit) > Number(costs.hourly_rate)
                          ? "text-xs text-destructive"
                          : "text-xs text-muted-foreground"
                      }
                    >
                      {Number(costs.cost_per_unit) > Number(costs.hourly_rate)
                        ? `Charged out at ${moneyExact(costs.hourly_rate)} and costing more than that to run.`
                        : `Charged out at ${moneyExact(costs.hourly_rate)}.`}
                    </p>
                  )}
                  {!costs.cost_per_unit && (
                    <p className="text-xs text-muted-foreground">
                      The meter has not moved in this window, so there is no cost per hour to
                      report. A zero here would read as free.
                    </p>
                  )}
                </>
              ) : null}
            </CardContent>
          </Card>

          {schedules && schedules.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Servicing</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                {schedules.map((schedule) => {
                  const nextAt = schedule.last_done_meter && schedule.interval_meter
                    ? Number(schedule.last_done_meter) + Number(schedule.interval_meter)
                    : null;
                  const toGo = nextAt !== null ? nextAt - Number(machine.current_meter) : null;
                  return (
                    <div key={schedule.id} className="flex items-baseline justify-between gap-2">
                      <span className="truncate">{schedule.name}</span>
                      <span
                        className={
                          toGo !== null && toGo <= 50
                            ? "shrink-0 font-medium text-warning"
                            : "shrink-0 text-muted-foreground"
                        }
                      >
                        {toGo === null
                          ? "On date only"
                          : toGo <= 0
                            ? `${Math.abs(toGo).toLocaleString()} ${unit} overdue`
                            : `${toGo.toLocaleString()} ${unit} to go`}
                      </span>
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <CardTitle className="text-base">Paperwork</CardTitle>
              <Button variant="outline" size="sm" onClick={() => setCertOpen(true)}>
                <Plus /> Add
              </Button>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {compliance?.certificates?.length ? (
                (compliance.certificates ?? []).map((cert) => (
                  <div key={cert.cert_type} className="flex items-center justify-between gap-2">
                    <span className="truncate">
                      {certLabel(cert.cert_type)}
                      {!cert.is_mandatory && (
                        <span className="ml-1.5 text-xs text-muted-foreground">optional</span>
                      )}
                    </span>
                    <div className="flex shrink-0 items-center gap-1">
                      <CertBadge state={cert.state} days={cert.days_to_expiry} />
                      {cert.certificate_id && (
                        <RemoveCert certificateId={cert.certificate_id} />
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-muted-foreground">Nothing on file.</p>
              )}
              {compliance?.is_compliant && (
                <p className="flex items-center gap-1.5 border-t pt-2 text-xs text-success">
                  <ShieldCheck weight="fill" className="h-3.5 w-3.5" /> Clear to work.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Been on</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {assignments?.items.length ? (
                assignments.items.map((a) => (
                  <div key={a.id} className="text-sm">
                    <div className="flex justify-between gap-2">
                      <span className="truncate">{fmtDate(a.started_on)}</span>
                      <span className="shrink-0 text-muted-foreground">
                        {a.ended_on ? fmtDate(a.ended_on) : "Still there"}
                      </span>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">Never sent out</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <ReadingDialog
        equipmentId={equipmentId}
        open={readingOpen}
        onOpenChange={setReadingOpen}
        unit={unit}
      />
      <FuelDialog equipmentId={equipmentId} open={fuelOpen} onOpenChange={setFuelOpen} />
      <ServiceDialog
        equipmentId={equipmentId}
        schedules={schedules ?? []}
        open={serviceOpen}
        onOpenChange={setServiceOpen}
      />
      <EditDialog machine={machine} open={editOpen} onOpenChange={setEditOpen} />
      <CertificateDialog
        equipmentId={equipmentId}
        open={certOpen}
        onOpenChange={setCertOpen}
      />
      <AssignDialog equipmentId={equipmentId} open={assignOpen} onOpenChange={setAssignOpen} />
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className="truncate text-right font-medium">{value}</span>
    </div>
  );
}

function ReadingDialog({
  equipmentId,
  open,
  onOpenChange,
  unit,
}: {
  equipmentId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  unit: string;
}) {
  const queryClient = useQueryClient();
  const create = useCreateReading();
  const [meter, setMeter] = useState("");
  const [idle, setIdle] = useState("");

  const submit = async () => {
    try {
      await create.mutateAsync({
        equipmentId,
        data: { meter, idle_hours: idle || null },
      });
      await queryClient.invalidateQueries();
      setMeter("");
      setIdle("");
      onOpenChange(false);
      toast.success("Reading recorded");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Record a reading</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="meter">Meter ({unit})</Label>
            <Input
              id="meter"
              inputMode="decimal"
              value={meter}
              onChange={(e) => setMeter(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              A meter only goes forward. A lower number is refused rather than accepted.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="idle">Idle hours, if known</Label>
            <Input
              id="idle"
              inputMode="decimal"
              value={idle}
              onChange={(e) => setIdle(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!meter || create.isPending} onClick={() => void submit()}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FuelDialog({
  equipmentId,
  open,
  onOpenChange,
}: {
  equipmentId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const create = useCreateFuel();
  const { data: projects } = useListProjects({ page: 1, page_size: 100 });
  const [form, setForm] = useState({
    litres: "",
    meter: "",
    unit_cost: "",
    operator: "",
    project_id: "",
  });

  const submit = async () => {
    try {
      await create.mutateAsync({
        equipmentId,
        data: {
          litres: form.litres,
          meter: form.meter || null,
          unit_cost: form.unit_cost || null,
          operator: form.operator || null,
          project_id: form.project_id || null,
        },
      });
      await queryClient.invalidateQueries();
      setForm({ litres: "", meter: "", unit_cost: "", operator: "", project_id: "" });
      onOpenChange(false);
      toast.success("Fuel recorded");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Record fuel</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="litres">Litres</Label>
            <Input
              id="litres"
              inputMode="decimal"
              value={form.litres}
              onChange={(e) => setForm({ ...form, litres: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="fuel-meter">Meter at the pump</Label>
            <Input
              id="fuel-meter"
              inputMode="decimal"
              value={form.meter}
              onChange={(e) => setForm({ ...form, meter: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="unit-cost">Price per litre</Label>
            <Input
              id="unit-cost"
              inputMode="decimal"
              value={form.unit_cost}
              onChange={(e) => setForm({ ...form, unit_cost: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="operator">Operator</Label>
            <Input
              id="operator"
              value={form.operator}
              onChange={(e) => setForm({ ...form, operator: e.target.value })}
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="fuel-project">Charge to</Label>
            <Select
              id="fuel-project"
              value={form.project_id}
              onChange={(e) => setForm({ ...form, project_id: e.target.value })}
            >
              <option value="">Wherever the machine is</option>
              {projects?.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code} {p.name}
                </option>
              ))}
            </Select>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          The meter matters: litres against the hours run since the last fill is what shows
          whether fuel went into the machine.
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!form.litres || create.isPending} onClick={() => void submit()}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AssignDialog({
  equipmentId,
  open,
  onOpenChange,
}: {
  equipmentId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const assign = useAssignEquipment();
  const { data: projects } = useListProjects({ page: 1, page_size: 100 });
  const [projectId, setProjectId] = useState("");

  const submit = async () => {
    try {
      await assign.mutateAsync({ equipmentId, data: { project_id: projectId } });
      await queryClient.invalidateQueries();
      onOpenChange(false);
      toast.success("Sent to site");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Send to site</DialogTitle>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="assign-project">Project</Label>
          <Select
            id="assign-project"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
          >
            <option value="">Choose a project</option>
            {projects?.items.map((p) => (
              <option key={p.id} value={p.id}>
                {p.code} {p.name}
              </option>
            ))}
          </Select>
          <p className="text-xs text-muted-foreground">
            Whatever it is on now is closed off, so its hours only ever count against one job.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!projectId || assign.isPending} onClick={() => void submit()}>
            <Plus /> Send
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ServiceDialog({
  equipmentId,
  schedules,
  open,
  onOpenChange,
}: {
  equipmentId: string;
  schedules: { id: string; name: string }[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const create = useCreateMaintenance();
  const [form, setForm] = useState({
    schedule_id: "",
    description: "",
    cost: "",
    downtime_hours: "",
    meter: "",
    reference: "",
  });

  const submit = async () => {
    try {
      await create.mutateAsync({
        equipmentId,
        data: {
          schedule_id: form.schedule_id || null,
          description: form.description,
          cost: form.cost || null,
          downtime_hours: form.downtime_hours || null,
          meter: form.meter || null,
          reference: form.reference || null,
        },
      });
      await queryClient.invalidateQueries();
      setForm({
        schedule_id: "",
        description: "",
        cost: "",
        downtime_hours: "",
        meter: "",
        reference: "",
      });
      onOpenChange(false);
      toast.success("Service recorded");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Record a service</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          {schedules.length > 0 && (
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="s-schedule">Against a schedule</Label>
              <Select
                id="s-schedule"
                value={form.schedule_id}
                onChange={(e) => setForm({ ...form, schedule_id: e.target.value })}
              >
                <option value="">Unplanned work</option>
                {schedules.map((schedule) => (
                  <option key={schedule.id} value={schedule.id}>
                    {schedule.name}
                  </option>
                ))}
              </Select>
              <p className="text-xs text-muted-foreground">
                Naming the schedule is what resets the clock on it. Unplanned work does not.
              </p>
            </div>
          )}
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="s-desc">What was done</Label>
            <Input
              id="s-desc"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="s-meter">Meter at service</Label>
            <Input
              id="s-meter"
              inputMode="decimal"
              value={form.meter}
              onChange={(e) => setForm({ ...form, meter: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="s-cost">Cost</Label>
            <Input
              id="s-cost"
              inputMode="decimal"
              value={form.cost}
              onChange={(e) => setForm({ ...form, cost: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="s-downtime">Hours off the job</Label>
            <Input
              id="s-downtime"
              inputMode="decimal"
              value={form.downtime_hours}
              onChange={(e) => setForm({ ...form, downtime_hours: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="s-ref">Job card</Label>
            <Input
              id="s-ref"
              value={form.reference}
              onChange={(e) => setForm({ ...form, reference: e.target.value })}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!form.description.trim() || create.isPending}
            onClick={() => void submit()}
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Correcting the register.
 *
 *  Only the things that legitimately change: what it is called, what it is
 *  charged out at, and where it is. The meter is not here — it moves by being
 *  read, and letting somebody type it would undo the one rule that keeps
 *  utilisation honest. */
function EditDialog({
  machine,
  open,
  onOpenChange,
}: {
  machine: {
    id: string;
    name: string;
    status: string;
    hourly_rate?: string | number | null;
    expected_burn_rate?: string | number | null;
    registration?: string | null;
    notes?: string | null;
  };
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const update = useUpdateEquipment();
  const [form, setForm] = useState({
    name: machine.name,
    status: machine.status,
    hourly_rate: machine.hourly_rate != null ? String(machine.hourly_rate) : "",
    expected_burn_rate:
      machine.expected_burn_rate != null ? String(machine.expected_burn_rate) : "",
    registration: machine.registration ?? "",
    notes: machine.notes ?? "",
  });

  const submit = async () => {
    try {
      await update.mutateAsync({
        equipmentId: machine.id,
        data: {
          name: form.name,
          status: form.status as never,
          hourly_rate: form.hourly_rate || null,
          expected_burn_rate: form.expected_burn_rate || null,
          registration: form.registration || null,
          notes: form.notes || null,
        },
      });
      await queryClient.invalidateQueries();
      onOpenChange(false);
      toast.success("Register updated");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit {machine.name}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="ed-name">Description</Label>
            <Input
              id="ed-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ed-status">Status</Label>
            <Select
              id="ed-status"
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
            >
              <option value="available">Available</option>
              <option value="on_site">On Site</option>
              <option value="workshop">In The Workshop</option>
              <option value="standing">Standing</option>
              <option value="off_hired">Off Hired</option>
              <option value="disposed">Disposed</option>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ed-reg">Registration</Label>
            <Input
              id="ed-reg"
              value={form.registration}
              onChange={(e) => setForm({ ...form, registration: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ed-rate">Charge-out rate</Label>
            <Input
              id="ed-rate"
              inputMode="decimal"
              value={form.hourly_rate}
              onChange={(e) => setForm({ ...form, hourly_rate: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ed-burn">Expected burn (L/hr)</Label>
            <Input
              id="ed-burn"
              inputMode="decimal"
              value={form.expected_burn_rate}
              onChange={(e) => setForm({ ...form, expected_burn_rate: e.target.value })}
            />
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          The meter is not editable. It moves by being read, and typing it would undo the rule
          that keeps every utilisation and burn figure honest.
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!form.name.trim() || update.isPending} onClick={() => void submit()}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const CERT_LABELS: Record<string, string> = {
  insurance: "Insurance",
  roadworthiness: "Roadworthiness",
  thorough_examination: "Thorough Examination",
  fitness: "Fitness",
  calibration: "Calibration",
  operator_licence: "Operator Licence",
  other: "Other",
};

function certLabel(certType: string) {
  return CERT_LABELS[certType] ?? certType.replace(/_/g, " ");
}

function CertBadge({ state, days }: { state: string; days?: number | null }) {
  switch (state) {
    case "valid":
      return <Badge variant="success">In date</Badge>;
    case "expiring":
      return <Badge variant="warning">{days === 0 ? "Today" : `${days}d left`}</Badge>;
    case "expired":
      return <Badge variant="destructive">Expired</Badge>;
    default:
      return <Badge variant="outline">Not on file</Badge>;
  }
}

function RemoveCert({ certificateId }: { certificateId: string }) {
  const queryClient = useQueryClient();
  const remove = useRemoveCertificate();

  const drop = async () => {
    const ok = await confirmDialog({
      title: "Remove this certificate?",
      message: "The machine goes back to having none on file for it.",
      confirmLabel: "Remove",
      tone: "danger",
    });
    if (!ok) return;
    try {
      await remove.mutateAsync({ certificateId });
      await queryClient.invalidateQueries();
      toast.success("Removed");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Button variant="ghost" size="icon" aria-label="Remove certificate" onClick={() => void drop()}>
      <Trash />
    </Button>
  );
}

/** Certificates are dated, not ticked.
 *
 *  There is no "is it insured?" checkbox anywhere here on purpose: a box
 *  somebody ticked two years ago tells you nothing, and an expiry date tells
 *  you everything. */
function CertificateDialog({
  equipmentId,
  open,
  onOpenChange,
}: {
  equipmentId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const add = useAddCertificate();
  const [form, setForm] = useState({
    cert_type: "insurance",
    reference: "",
    issued_on: "",
    expires_on: "",
  });

  const submit = async () => {
    try {
      await add.mutateAsync({
        equipmentId,
        data: {
          cert_type: form.cert_type as never,
          reference: form.reference || null,
          issued_on: form.issued_on || null,
          expires_on: form.expires_on || null,
        },
      });
      await queryClient.invalidateQueries();
      setForm({ cert_type: "insurance", reference: "", issued_on: "", expires_on: "" });
      onOpenChange(false);
      toast.success("Certificate recorded");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Record a certificate</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="c-type">Document</Label>
            <Select
              id="c-type"
              value={form.cert_type}
              onChange={(e) => setForm({ ...form, cert_type: e.target.value })}
            >
              {Object.entries(CERT_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="c-ref">Reference</Label>
            <Input
              id="c-ref"
              value={form.reference}
              onChange={(e) => setForm({ ...form, reference: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="c-issued">Issued</Label>
            <Input
              id="c-issued"
              type="date"
              value={form.issued_on}
              onChange={(e) => setForm({ ...form, issued_on: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="c-expires">Expires</Label>
            <Input
              id="c-expires"
              type="date"
              value={form.expires_on}
              onChange={(e) => setForm({ ...form, expires_on: e.target.value })}
            />
            <p className="text-xs text-muted-foreground">
              An expired certificate stops the machine going to site.
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={add.isPending} onClick={() => void submit()}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
