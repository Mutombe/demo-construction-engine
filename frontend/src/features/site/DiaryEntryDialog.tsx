import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "@/lib/toast";
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
import { useCreateDiaryEntry, useUpdateDiaryEntry } from "@/lib/api/generated/endpoints";
import type { DiaryEntryRead } from "@/lib/api/generated/model";

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

export function DiaryEntryDialog({
  open,
  onOpenChange,
  projectId,
  entry,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  entry?: DiaryEntryRead | null;
}) {
  const queryClient = useQueryClient();
  const createMutation = useCreateDiaryEntry();
  const updateMutation = useUpdateDiaryEntry();

  const [entryDate, setEntryDate] = useState("");
  const [weather, setWeather] = useState("sunny");
  const [labour, setLabour] = useState("0");
  const [plant, setPlant] = useState("");
  const [workDone, setWorkDone] = useState("");
  const [delays, setDelays] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (open) {
      setEntryDate(entry?.entry_date ?? new Date().toISOString().slice(0, 10));
      setWeather(entry?.weather ?? "sunny");
      setLabour(String(entry?.labour_headcount ?? 0));
      setPlant(entry?.plant_equipment ?? "");
      setWorkDone(entry?.work_done ?? "");
      setDelays(entry?.delays ?? "");
      setNotes(entry?.notes ?? "");
    }
  }, [open, entry]);

  const save = async () => {
    if (!workDone.trim()) {
      toast.error("Describe the work done");
      return;
    }
    const payload = {
      entry_date: entryDate,
      weather: weather as never,
      labour_headcount: Number(labour) || 0,
      plant_equipment: plant || null,
      work_done: workDone,
      delays: delays || null,
      notes: notes || null,
    };
    try {
      if (entry) {
        await updateMutation.mutateAsync({ entryId: entry.id, data: payload });
        toast.success("Diary entry updated");
      } else {
        await createMutation.mutateAsync({ projectId, data: payload });
        toast.success("Diary entry recorded");
      }
      await queryClient.invalidateQueries();
      onOpenChange(false);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const busy = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{entry ? "Edit diary entry" : "New diary entry"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label>Date</Label>
              <Input type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Weather</Label>
              <Select value={weather} onChange={(e) => setWeather(e.target.value)}>
                <option value="sunny">Sunny</option>
                <option value="cloudy">Cloudy</option>
                <option value="rain">Rain</option>
                <option value="storm">Storm</option>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Labour headcount</Label>
              <Input
                type="number"
                min="0"
                value={labour}
                onChange={(e) => setLabour(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Plant & equipment on site</Label>
            <Input
              value={plant}
              onChange={(e) => setPlant(e.target.value)}
              placeholder="1x tower crane, 2x mixers"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Work done</Label>
            <Textarea rows={3} value={workDone} onChange={(e) => setWorkDone(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Delays</Label>
              <Textarea rows={2} value={delays} onChange={(e) => setDelays(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Notes</Label>
              <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button disabled={busy} onClick={() => void save()}>
              {busy ? "Saving…" : "Save entry"}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
