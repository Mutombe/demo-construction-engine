import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
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
import {
  useBulkCreateTimesheets,
  useListProjects,
  useListWorkers,
} from "@/lib/api/generated/endpoints";
import { moneyExact } from "@/lib/format";

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

interface Row {
  quantity: string;
  overtime: string;
}

/** The site manager's hero flow: pick project + date, tab through the crew.
 *  Rows left at 0 are skipped (or clear an existing unpaid entry). */
export function DayEntryDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const { data: projects } = useListProjects({ page_size: 100 }, { query: { enabled: open } });
  const { data: workers } = useListWorkers({ page_size: 200 }, { query: { enabled: open } });
  const bulkMutation = useBulkCreateTimesheets();

  const [projectId, setProjectId] = useState("");
  const [workDate, setWorkDate] = useState("");
  const [rows, setRows] = useState<Record<string, Row>>({});

  useEffect(() => {
    if (open) {
      setProjectId("");
      setWorkDate(new Date().toISOString().slice(0, 10));
      setRows({});
    }
  }, [open]);

  const workerList = workers?.items ?? [];
  const setRow = (id: string, patch: Partial<Row>) =>
    setRows((prev) => ({
      ...prev,
      [id]: { quantity: "", overtime: "", ...prev[id], ...patch },
    }));

  const markAll = (value: string) => {
    setRows(
      Object.fromEntries(
        workerList.map((w) => [
          w.id,
          { quantity: w.pay_basis === "hourly" ? "8" : value, overtime: "" },
        ]),
      ),
    );
  };

  const estimate = useMemo(() => {
    let total = 0;
    for (const worker of workerList) {
      const row = rows[worker.id];
      if (!row) continue;
      const qty = Number(row.quantity) || 0;
      const ot = Number(row.overtime) || 0;
      total += qty * Number(worker.rate) + ot * Number(worker.rate) * 1.5;
    }
    return total;
  }, [rows, workerList]);

  const filledCount = Object.values(rows).filter((r) => Number(r.quantity) > 0).length;

  const save = async () => {
    if (!projectId || !workDate) {
      toast.error("Pick the project and date first");
      return;
    }
    const entries = workerList.flatMap((w) => {
      const row = rows[w.id];
      if (!row) return [];
      return [
        {
          worker_id: w.id,
          quantity: row.quantity || "0",
          overtime_quantity: row.overtime || "0",
        },
      ];
    });
    if (entries.length === 0) {
      toast.error("Enter time for at least one worker");
      return;
    }
    try {
      await bulkMutation.mutateAsync({
        data: { project_id: projectId, work_date: workDate, entries },
      });
      await queryClient.invalidateQueries();
      toast.success(`Day recorded — ${filledCount} worker${filledCount === 1 ? "" : "s"}`);
      onOpenChange(false);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Site day entry</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Project</Label>
              <Select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                <option value="">Select project…</option>
                {projects?.items.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.code} — {p.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Date</Label>
              <Input type="date" value={workDate} onChange={(e) => setWorkDate(e.target.value)} />
            </div>
          </div>

          <div className="flex items-center justify-between">
            <Label>Crew — tab through quantities</Label>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => markAll("1")}>
                Everyone full day
              </Button>
              <Button variant="outline" size="sm" onClick={() => setRows({})}>
                Clear
              </Button>
            </div>
          </div>
          <div className="max-h-80 overflow-y-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-muted text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Worker</th>
                  <th className="px-3 py-2 text-left font-medium">Basis</th>
                  <th className="w-24 px-2 py-2 text-right font-medium">Qty</th>
                  <th className="w-24 px-2 py-2 text-right font-medium">OT</th>
                </tr>
              </thead>
              <tbody>
                {workerList.map((worker) => {
                  const row = rows[worker.id];
                  return (
                    <tr key={worker.id} className="border-t transition-colors hover:bg-muted/40">
                      <td className="px-3 py-1.5">
                        <div className="font-medium">{worker.full_name}</div>
                        <div className="text-xs text-muted-foreground">{worker.trade}</div>
                      </td>
                      <td className="px-3 py-1.5 text-xs text-muted-foreground">
                        {worker.pay_basis === "hourly" ? "hrs" : "days"} @{" "}
                        {moneyExact(worker.rate)}
                      </td>
                      <td className="px-2 py-1.5">
                        <Input
                          type="number"
                          step="0.5"
                          min="0"
                          className="h-8 text-right tabular-nums"
                          placeholder="0"
                          value={row?.quantity ?? ""}
                          onChange={(e) => setRow(worker.id, { quantity: e.target.value })}
                        />
                      </td>
                      <td className="px-2 py-1.5">
                        <Input
                          type="number"
                          step="0.5"
                          min="0"
                          className="h-8 text-right tabular-nums"
                          placeholder="0"
                          value={row?.overtime ?? ""}
                          onChange={(e) => setRow(worker.id, { overtime: e.target.value })}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <DialogFooter className="items-center gap-3 sm:justify-between">
            <div className="text-sm text-muted-foreground">
              {filledCount} worker{filledCount === 1 ? "" : "s"} ·{" "}
              <span className="font-medium text-foreground tabular-nums">
                ≈ {moneyExact(estimate)}
              </span>{" "}
              labour
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button disabled={bulkMutation.isPending} onClick={() => void save()}>
                {bulkMutation.isPending ? "Saving…" : "Record day"}
              </Button>
            </div>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
