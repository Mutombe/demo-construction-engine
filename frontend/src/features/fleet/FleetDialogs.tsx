import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { errDetail } from "@/lib/api/errors";
import { useCreateEquipment, useImportTelematics } from "@/lib/api/generated/endpoints";
import { toast } from "@/lib/toast";

const CATEGORIES = [
  "excavator",
  "loader",
  "grader",
  "roller",
  "tipper",
  "truck",
  "crane",
  "generator",
  "pump",
  "compressor",
  "light_vehicle",
  "other",
];

function titleCase(value: string) {
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function RegisterDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const create = useCreateEquipment();
  const [form, setForm] = useState({
    code: "",
    name: "",
    category: "excavator",
    ownership: "owned",
    meter_type: "hours",
    current_meter: "0",
    hourly_rate: "",
    expected_burn_rate: "",
    registration: "",
  });

  const submit = async () => {
    try {
      await create.mutateAsync({
        data: {
          code: form.code,
          name: form.name,
          category: form.category as never,
          ownership: form.ownership as never,
          meter_type: form.meter_type as never,
          current_meter: form.current_meter || "0",
          hourly_rate: form.hourly_rate || null,
          expected_burn_rate: form.expected_burn_rate || null,
          registration: form.registration || null,
        },
      });
      await queryClient.invalidateQueries();
      onOpenChange(false);
      toast.success(`${form.code} is on the register`);
      setForm({ ...form, code: "", name: "", registration: "", current_meter: "0" });
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Register a machine</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="e-code">Fleet number</Label>
            <Input
              id="e-code"
              placeholder="EXC-004"
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="e-name">Description</Label>
            <Input
              id="e-name"
              placeholder="Cat 320D Excavator"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="e-category">Category</Label>
            <Select
              id="e-category"
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
            >
              {CATEGORIES.map((value) => (
                <option key={value} value={value}>
                  {titleCase(value)}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="e-ownership">Ownership</Label>
            <Select
              id="e-ownership"
              value={form.ownership}
              onChange={(e) => setForm({ ...form, ownership: e.target.value })}
            >
              <option value="owned">Owned</option>
              <option value="hired">Hired In</option>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="e-meter-type">Meter</Label>
            <Select
              id="e-meter-type"
              value={form.meter_type}
              onChange={(e) => setForm({ ...form, meter_type: e.target.value })}
            >
              <option value="hours">Hours</option>
              <option value="kilometres">Kilometres</option>
            </Select>
            <p className="text-xs text-muted-foreground">
              Yellow plant runs on hours, vehicles on distance. Mixing them makes utilisation
              meaningless.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="e-meter">Meter today</Label>
            <Input
              id="e-meter"
              inputMode="decimal"
              value={form.current_meter}
              onChange={(e) => setForm({ ...form, current_meter: e.target.value })}
            />
            <p className="text-xs text-muted-foreground">
              Counts as its first reading, so nothing lower can be entered later.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="e-rate">
              Charge-out rate per {form.meter_type === "hours" ? "hour" : "km"}
            </Label>
            <Input
              id="e-rate"
              inputMode="decimal"
              value={form.hourly_rate}
              onChange={(e) => setForm({ ...form, hourly_rate: e.target.value })}
            />
            <p className="text-xs text-muted-foreground">
              {form.meter_type === "hours"
                ? "What a job is charged for each hour it runs."
                : "Per kilometre, not per hour. A truck charged at an hourly rate bills a job six figures for one month of tipping."}
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="e-burn">Expected burn (L/hr)</Label>
            <Input
              id="e-burn"
              inputMode="decimal"
              value={form.expected_burn_rate}
              onChange={(e) => setForm({ ...form, expected_burn_rate: e.target.value })}
            />
            <p className="text-xs text-muted-foreground">
              Optional. Left blank, the machine builds its own baseline from what it has burned.
            </p>
          </div>
          {form.meter_type === "kilometres" && (
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="e-reg">Registration</Label>
              <Input
                id="e-reg"
                value={form.registration}
                onChange={(e) => setForm({ ...form, registration: e.target.value })}
              />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!form.code.trim() || !form.name.trim() || create.isPending}
            onClick={() => void submit()}
          >
            Register
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface ImportRow {
  code: string;
  reading_date?: string | null;
  meter?: string | null;
  idle_hours?: string | null;
  litres?: string | null;
  unit_cost?: string | null;
}

/** Parses the CSV a tracker or a bowser sheet actually produces.
 *
 *  Headers are matched loosely because no two exports name the columns the
 *  same way, and a blank cell means "not recorded" rather than zero — the
 *  difference between a machine that stood still and one nobody wrote down. */
export function parseCsv(text: string): { rows: ImportRow[]; problem: string | null } {
  const lines = text
    .trim()
    .split(/\r?\n/)
    .filter((line) => line.trim());
  if (lines.length < 2) return { rows: [], problem: "There is a header but no rows under it." };

  const headers = (lines[0] ?? "").split(",").map((header) => header.trim().toLowerCase());
  const find = (...names: string[]) =>
    headers.findIndex((header) => names.some((name) => header.includes(name)));
  const columns = {
    code: find("code", "fleet", "asset", "unit"),
    date: find("date", "day"),
    meter: find("meter", "hours", "odo", "reading"),
    idle: find("idle"),
    litres: find("litre", "liter", "fuel", "qty"),
    cost: find("price", "cost", "rate"),
  };
  if (columns.code < 0) {
    return { rows: [], problem: "No column in that file looks like a fleet number." };
  }

  const cell = (cells: string[], index: number) =>
    index >= 0 && cells[index]?.trim() ? cells[index].trim() : null;

  const rows = lines.slice(1).map((line) => {
    const cells = line.split(",");
    return {
      code: (cell(cells, columns.code) ?? "").toUpperCase(),
      reading_date: cell(cells, columns.date),
      meter: cell(cells, columns.meter),
      idle_hours: cell(cells, columns.idle),
      litres: cell(cells, columns.litres),
      unit_cost: cell(cells, columns.cost),
    };
  });
  return { rows, problem: null };
}

const SAMPLE = "code,date,meter,litres,price\nEXC-001,2026-08-24,4820,310,1.62";

export function TelematicsDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const send = useImportTelematics();
  const [text, setText] = useState("");
  const [result, setResult] = useState<{
    applied: number;
    rejected: number;
    results: { line: number; code: string; status: string; detail?: string | null }[];
  } | null>(null);

  const parsed = text.trim() ? parseCsv(text) : { rows: [], problem: null };

  const submit = async () => {
    try {
      const data = await send.mutateAsync({ data: { rows: parsed.rows as never } });
      await queryClient.invalidateQueries();
      setResult(data as never);
      toast.success(`${data.applied} rows applied`);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const failures = (result?.results ?? []).filter((row) => row.status === "rejected");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import readings and fuel</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="csv">Paste the export</Label>
            <Textarea
              id="csv"
              rows={8}
              className="font-mono text-xs"
              placeholder={SAMPLE}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setResult(null);
              }}
            />
            <p className="text-xs text-muted-foreground">
              Column names are matched loosely, because no two trackers name them the same way.
            </p>
          </div>

          {parsed.problem && <p className="text-sm text-destructive">{parsed.problem}</p>}
          {!parsed.problem && parsed.rows.length > 0 && !result && (
            <p className="text-sm text-muted-foreground">
              {parsed.rows.length} rows ready. Each is applied on its own, so a file that is
              partly wrong still lands the part that is right.
            </p>
          )}

          {result && (
            <div className="space-y-2 rounded-md border p-3">
              <p className="text-sm">
                <span className="font-medium text-success">{result.applied} applied</span>
                {result.rejected > 0 && (
                  <span className="ml-2 font-medium text-destructive">
                    {result.rejected} refused
                  </span>
                )}
              </p>
              {failures.length > 0 && (
                <div className="max-h-40 space-y-1 overflow-y-auto">
                  {failures.map((row) => (
                    <div key={row.line} className="text-xs">
                      <span className="font-mono text-muted-foreground">Line {row.line}</span>{" "}
                      <span className="text-destructive">{row.detail}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {result ? "Close" : "Cancel"}
          </Button>
          <Button
            disabled={!parsed.rows.length || !!parsed.problem || send.isPending}
            onClick={() => void submit()}
          >
            Import
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
