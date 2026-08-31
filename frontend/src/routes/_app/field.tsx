import { createFileRoute } from "@tanstack/react-router";
import {
  CheckCircle,
  CloudSlash,
  Drop,
  Gauge,
  NotePencil,
  Trash,
  Warning,
  WifiHigh,
} from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api/axios";
import { useListProjects } from "@/lib/api/generated/endpoints";
import { enqueue, remove, type OutboxOperation } from "@/lib/offline/outbox";
import { useOutbox } from "@/lib/offline/useOutbox";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/_app/field")({
  component: FieldCapture,
});

interface Pack {
  project_id: string;
  project_code: string;
  project_name: string;
  workers: { id: string; full_name: string; trade: string | null }[];
  equipment: { id: string; code: string; name: string; meter_type: string; current_meter: number }[];
}

const PACK_KEY = "erp-field-pack";

/** Kept in localStorage rather than fetched, because the whole point is that
 *  the form still works when nothing can be fetched. Downloaded on the way
 *  out of the yard, used all day, replaced on the way back. */
function useFieldPack(projectId: string | null) {
  const [pack, setPack] = useState<Pack | null>(() => {
    const raw = localStorage.getItem(PACK_KEY);
    return raw ? (JSON.parse(raw) as Pack) : null;
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!projectId || !navigator.onLine) return;
    if (pack?.project_id === projectId) return;
    setLoading(true);
    api
      .get<Pack>(`/api/v1/sync/bootstrap/${projectId}`)
      .then(({ data }) => {
        localStorage.setItem(PACK_KEY, JSON.stringify(data));
        setPack(data);
      })
      .catch(() => toast.error("Could not download the site pack"))
      .finally(() => setLoading(false));
  }, [projectId, pack?.project_id]);

  return { pack, loading };
}

function FieldCapture() {
  const { online, waiting, rejected, sending, send } = useOutbox();
  const { data: projects } = useListProjects({ page: 1, page_size: 100 });
  const [projectId, setProjectId] = useState<string>("");
  const { pack, loading } = useFieldPack(projectId || null);

  useEffect(() => {
    if (!projectId && pack) setProjectId(pack.project_id);
  }, [pack, projectId]);

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Site Capture</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Everything written here is saved on this device first and sent when there is signal.
          Nothing is lost by being out of range.
        </p>
      </div>

      <div
        className={
          online
            ? "flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm"
            : "flex items-center justify-between gap-3 rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-sm"
        }
      >
        <span className="flex items-center gap-2">
          {online ? (
            <WifiHigh className="h-4 w-4 text-success" />
          ) : (
            <CloudSlash className="h-4 w-4 text-warning" />
          )}
          {online ? "Connected" : "No signal — still recording"}
          {waiting.length > 0 && (
            <Badge variant="outline">{waiting.length} waiting to send</Badge>
          )}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={!online || sending || !waiting.length}
          onClick={() => void send()}
        >
          {sending ? "Sending…" : "Send Now"}
        </Button>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="field-project">Site</Label>
        <Select
          id="field-project"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          disabled={!online && !pack}
        >
          <option value="">Choose a site</option>
          {(projects?.items ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.code} {p.name}
            </option>
          ))}
          {pack && !projects?.items.some((p) => p.id === pack.project_id) && (
            <option value={pack.project_id}>
              {pack.project_code} {pack.project_name}
            </option>
          )}
        </Select>
        {loading && <p className="text-xs text-muted-foreground">Downloading the site pack…</p>}
        {pack && pack.project_id === projectId && (
          <p className="text-xs text-muted-foreground">
            {pack.workers.length} workers and {pack.equipment.length} machines available offline.
          </p>
        )}
      </div>

      {projectId && (
        <>
          <DiaryForm projectId={projectId} pack={pack} />
          <IssueForm projectId={projectId} />
          <PlantForm projectId={projectId} pack={pack} />
        </>
      )}

      <Queue waiting={waiting} rejected={rejected} />
    </div>
  );
}

function DiaryForm({ projectId, pack }: { projectId: string; pack: Pack | null }) {
  const [form, setForm] = useState({
    entry_date: new Date().toISOString().slice(0, 10),
    weather: "sunny",
    work_done: "",
    delays: "",
    notes: "",
  });
  const [crew, setCrew] = useState<Record<string, string>>({});

  const save = async () => {
    await enqueue(
      "diary_entry",
      { project_id: projectId, ...form },
      `Diary for ${form.entry_date}`,
    );
    const lines = Object.entries(crew)
      .filter(([, hours]) => Number(hours) > 0)
      .map(([worker_id, quantity]) => ({ worker_id, quantity }));
    if (lines.length) {
      await enqueue(
        "diary_labour",
        { project_id: projectId, entry_date: form.entry_date, lines },
        `${lines.length} on site, ${form.entry_date}`,
      );
    }
    setForm({ ...form, work_done: "", delays: "", notes: "" });
    setCrew({});
    toast.success("Saved on this device");
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <NotePencil /> Today's diary
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="d-date">Date</Label>
            <Input
              id="d-date"
              type="date"
              value={form.entry_date}
              onChange={(e) => setForm({ ...form, entry_date: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="d-weather">Weather</Label>
            <Select
              id="d-weather"
              value={form.weather}
              onChange={(e) => setForm({ ...form, weather: e.target.value })}
            >
              <option value="sunny">Sunny</option>
              <option value="cloudy">Cloudy</option>
              <option value="rain">Rain</option>
              <option value="storm">Storm</option>
              <option value="extreme_heat">Extreme Heat</option>
            </Select>
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="d-work">Work done</Label>
          <Textarea
            id="d-work"
            rows={3}
            value={form.work_done}
            onChange={(e) => setForm({ ...form, work_done: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="d-delays">Delays</Label>
          <Input
            id="d-delays"
            value={form.delays}
            onChange={(e) => setForm({ ...form, delays: e.target.value })}
          />
        </div>

        {pack?.workers.length ? (
          <div className="space-y-1.5">
            <Label>Who was on</Label>
            <div className="max-h-56 space-y-1 overflow-y-auto rounded-md border p-2">
              {pack.workers.map((worker) => (
                <div key={worker.id} className="flex items-center gap-2">
                  <span className="flex-1 truncate text-sm">
                    {worker.full_name}
                    {worker.trade && (
                      <span className="ml-1.5 text-xs text-muted-foreground">{worker.trade}</span>
                    )}
                  </span>
                  <Input
                    aria-label={`Hours for ${worker.full_name}`}
                    inputMode="decimal"
                    placeholder="—"
                    className="h-8 w-20 text-right"
                    value={crew[worker.id] ?? ""}
                    onChange={(e) => setCrew({ ...crew, [worker.id]: e.target.value })}
                  />
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              Counted once here rather than again on a timesheet.
            </p>
          </div>
        ) : null}

        <Button className="w-full" disabled={!form.work_done.trim()} onClick={() => void save()}>
          Save Diary
        </Button>
      </CardContent>
    </Card>
  );
}

function IssueForm({ projectId }: { projectId: string }) {
  const [form, setForm] = useState({ title: "", description: "", severity: "medium" });

  const save = async () => {
    await enqueue("site_issue", { project_id: projectId, ...form }, form.title);
    setForm({ title: "", description: "", severity: "medium" });
    toast.success("Saved on this device");
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Warning /> Raise an issue
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="i-title">What is wrong</Label>
          <Input
            id="i-title"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="i-severity">Severity</Label>
            <Select
              id="i-severity"
              value={form.severity}
              onChange={(e) => setForm({ ...form, severity: e.target.value })}
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </Select>
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="i-desc">Detail</Label>
          <Textarea
            id="i-desc"
            rows={2}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>
        <Button className="w-full" disabled={!form.title.trim()} onClick={() => void save()}>
          Save Issue
        </Button>
      </CardContent>
    </Card>
  );
}

function PlantForm({ projectId, pack }: { projectId: string; pack: Pack | null }) {
  const [equipmentId, setEquipmentId] = useState("");
  const [meter, setMeter] = useState("");
  const [litres, setLitres] = useState("");

  const machine = pack?.equipment.find((e) => e.id === equipmentId);

  const saveReading = async () => {
    await enqueue(
      "meter_reading",
      { project_id: projectId, equipment_id: equipmentId, meter },
      `${machine?.code ?? "Plant"} at ${meter}`,
    );
    setMeter("");
    toast.success("Saved on this device");
  };

  const saveFuel = async () => {
    await enqueue(
      "fuel_log",
      { project_id: projectId, equipment_id: equipmentId, litres, meter: meter || null },
      `${litres}L into ${machine?.code ?? "plant"}`,
    );
    setLitres("");
    toast.success("Saved on this device");
  };

  if (!pack?.equipment.length) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Gauge /> Plant
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No machines are assigned to this site, so there is nothing to read or fuel.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Gauge /> Plant
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="p-machine">Machine</Label>
          <Select
            id="p-machine"
            value={equipmentId}
            onChange={(e) => setEquipmentId(e.target.value)}
          >
            <option value="">Choose a machine</option>
            {pack.equipment.map((e) => (
              <option key={e.id} value={e.id}>
                {e.code} {e.name}
              </option>
            ))}
          </Select>
        </div>
        {machine && (
          <>
            <div className="space-y-1.5">
              <Label htmlFor="p-meter">
                Meter ({machine.meter_type === "hours" ? "hrs" : "km"})
              </Label>
              <Input
                id="p-meter"
                inputMode="decimal"
                value={meter}
                onChange={(e) => setMeter(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Last known {machine.current_meter.toLocaleString()}.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="p-litres">Litres put in</Label>
              <Input
                id="p-litres"
                inputMode="decimal"
                value={litres}
                onChange={(e) => setLitres(e.target.value)}
              />
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                className="flex-1"
                disabled={!meter}
                onClick={() => void saveReading()}
              >
                <Gauge /> Save Reading
              </Button>
              <Button className="flex-1" disabled={!litres} onClick={() => void saveFuel()}>
                <Drop /> Save Fuel
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Queue({
  waiting,
  rejected,
}: {
  waiting: OutboxOperation[];
  rejected: OutboxOperation[];
}) {
  if (!waiting.length && !rejected.length) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <CheckCircle className="h-4 w-4 text-success" /> Everything on this device has been sent.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">On this device</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {waiting.map((op) => (
          <div key={op.client_op_id} className="flex items-center gap-2 text-sm">
            <Badge variant="outline">Waiting</Badge>
            <span className="flex-1 truncate">{op.label}</span>
            <span className="text-xs text-muted-foreground">
              {new Date(op.captured_at).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>
        ))}
        {rejected.map((op) => (
          <div key={op.client_op_id} className="flex items-start gap-2 text-sm">
            <Badge variant="destructive">Refused</Badge>
            <div className="min-w-0 flex-1">
              <div className="truncate">{op.label}</div>
              <div className="text-xs text-destructive">{op.detail}</div>
            </div>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Discard"
              onClick={() => void remove(op.client_op_id)}
            >
              <Trash />
            </Button>
          </div>
        ))}
        {rejected.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Refused entries stay here until you deal with them, rather than disappearing.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
