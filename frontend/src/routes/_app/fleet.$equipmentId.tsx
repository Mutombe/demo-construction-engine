import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Drop, Gauge, Plus, Truck } from "@phosphor-icons/react";
import { useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Badge } from "@/components/ui/badge";
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
import { Select } from "@/components/ui/select";
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
  useCreateReading,
  useGetEquipment,
  useListAssignments,
  useListFuel,
  useListProjects,
  useListReadings,
  useReleaseEquipment,
} from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/_app/fleet/$equipmentId")({
  component: EquipmentDetail,
});

function EquipmentDetail() {
  const { equipmentId } = Route.useParams();
  const queryClient = useQueryClient();
  const { data: machine } = useGetEquipment(equipmentId);
  const { data: readings } = useListReadings(equipmentId, {});
  const { data: fuel } = useListFuel(equipmentId, {});
  const { data: assignments } = useListAssignments(equipmentId);
  const release = useReleaseEquipment();

  const [readingOpen, setReadingOpen] = useState(false);
  const [fuelOpen, setFuelOpen] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);

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

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Fuel</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {fuel?.length ? (
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
                    {fuel.map((log) => (
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
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Meter readings</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {readings?.length ? (
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
                    {readings.map((row) => (
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
              <CardTitle className="text-base">Been on</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {assignments?.length ? (
                assignments.map((a) => (
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
