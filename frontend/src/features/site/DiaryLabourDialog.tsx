import { useQueryClient } from "@tanstack/react-query";
import { ArrowSquareOut, Plus, Trash } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
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
import { errDetail } from "@/lib/api/errors";
import {
  useGetDiaryEntry,
  useListWorkers,
  usePushDiaryLabourToTimesheets,
  useSetDiaryLabour,
} from "@/lib/api/generated/endpoints";
import { fmtDate } from "@/lib/format";
import { toast } from "@/lib/toast";

type Line = { worker_id: string; quantity: string; overtime_quantity: string };

const EMPTY: Line = { worker_id: "", quantity: "1", overtime_quantity: "0" };

/** Record who worked today once, in the diary, then push it to payroll —
 *  instead of site and payroll entering the same fact twice. */
export function DiaryLabourDialog({
  entryId,
  onOpenChange,
}: {
  entryId: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const { data: entry } = useGetDiaryEntry(entryId ?? "", {
    query: { enabled: !!entryId } as { enabled: boolean },
  });
  const { data: workers } = useListWorkers({ page_size: 200 });
  const saveLabour = useSetDiaryLabour();
  const pushMutation = usePushDiaryLabourToTimesheets();
  const [lines, setLines] = useState<Line[]>([]);

  useEffect(() => {
    if (entry) {
      const labour = entry.labour ?? [];
      setLines(
        labour.length > 0
          ? labour.map((l) => ({
              worker_id: l.worker_id,
              quantity: String(l.quantity),
              overtime_quantity: String(l.overtime_quantity),
            }))
          : [{ ...EMPTY }],
      );
    }
  }, [entry]);

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["/api/v1/diary"] }),
      queryClient.invalidateQueries({ queryKey: ["/api/v1/projects"] }),
      queryClient.invalidateQueries({ queryKey: ["/api/v1/timesheets"] }),
    ]);

  const setLine = (index: number, patch: Partial<Line>) =>
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, ...patch } : l)));

  const save = async () => {
    if (!entryId) return;
    const filled = lines.filter((l) => l.worker_id);
    try {
      await saveLabour.mutateAsync({
        entryId,
        data: {
          lines: filled.map((l) => ({
            worker_id: l.worker_id,
            quantity: l.quantity || "0",
            overtime_quantity: l.overtime_quantity || "0",
          })),
        },
      });
      await refresh();
      toast.success("Labour saved on the diary");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const push = async () => {
    if (!entryId) return;
    try {
      const result = await pushMutation.mutateAsync({ entryId });
      await refresh();
      const parts = [];
      if (result.created) parts.push(`${result.created} created`);
      if (result.updated) parts.push(`${result.updated} updated`);
      toast.success(
        parts.length ? `Timesheets ${parts.join(", ")}` : "Timesheets already up to date",
      );
      if (result.skipped_locked.length > 0) {
        toast.error(
          `Already paid, left unchanged: ${result.skipped_locked.join(", ")}`,
        );
      }
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={!!entryId} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            Labour on Site
            {entry && (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                {fmtDate(entry.entry_date)}
              </span>
            )}
            {entry?.timesheets_pushed && (
              <Badge variant="success" className="ml-2">
                In payroll
              </Badge>
            )}
          </DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground">
          Record the crew once here; pushing creates their timesheets for this project and
          day. Time already inside an approved pay run is never overwritten.
        </p>

        <div className="space-y-2">
          <div className="grid grid-cols-12 gap-2 text-xs uppercase tracking-wide text-muted-foreground">
            <span className="col-span-6">Worker</span>
            <span className="col-span-2 text-right">Normal</span>
            <span className="col-span-2 text-right">Overtime</span>
          </div>
          {lines.map((line, index) => (
            <div key={index} className="grid grid-cols-12 items-center gap-2">
              <Select
                className="col-span-6"
                value={line.worker_id}
                onChange={(e) => setLine(index, { worker_id: e.target.value })}
              >
                <option value="">Select worker…</option>
                {workers?.items.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.full_name} · {w.trade}
                  </option>
                ))}
              </Select>
              <Input
                className="col-span-2 text-right"
                type="number"
                min="0"
                step="0.5"
                value={line.quantity}
                onChange={(e) => setLine(index, { quantity: e.target.value })}
              />
              <Input
                className="col-span-2 text-right"
                type="number"
                min="0"
                step="0.5"
                value={line.overtime_quantity}
                onChange={(e) => setLine(index, { overtime_quantity: e.target.value })}
              />
              <Button
                variant="ghost"
                size="icon"
                className="col-span-2 text-destructive"
                onClick={() => setLines((prev) => prev.filter((_, i) => i !== index))}
              >
                <Trash />
              </Button>
            </div>
          ))}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setLines((prev) => [...prev, { ...EMPTY }])}
          >
            <Plus /> Add Worker
          </Button>
          <Label className="block pt-1 text-xs text-muted-foreground">
            Quantity is hours or days depending on how the worker is paid.
          </Label>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button variant="outline" disabled={saveLabour.isPending} onClick={() => void save()}>
            {saveLabour.isPending ? "Saving…" : "Save Labour"}
          </Button>
          <Button
            disabled={pushMutation.isPending || !entry?.labour?.length}
            onClick={() => void push()}
          >
            <ArrowSquareOut /> {pushMutation.isPending ? "Pushing…" : "Push to Timesheets"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
