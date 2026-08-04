import { useQueryClient } from "@tanstack/react-query";
import { Plus, Trash } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
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
import {
  useCreateRequisition,
  useGetBoq,
  useListProjects,
} from "@/lib/api/generated/endpoints";
import { toast } from "@/lib/toast";

type Line = { boq_item_id: string; description: string; unit: string; quantity: string };

const EMPTY: Line = { boq_item_id: "", description: "", unit: "", quantity: "" };

export function RequisitionFormDialog({
  open,
  onOpenChange,
  projectId: fixedProjectId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId?: string;
}) {
  const queryClient = useQueryClient();
  const createMutation = useCreateRequisition();
  const { data: projects } = useListProjects({ page_size: 100 });

  const [projectId, setProjectId] = useState(fixedProjectId ?? "");
  const [neededBy, setNeededBy] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<Line[]>([{ ...EMPTY }]);

  const { data: boq } = useGetBoq(projectId, {
    query: { enabled: !!projectId && open },
  });
  const boqItems = (boq?.sections ?? []).flatMap((section) =>
    (section.items ?? []).map((item) => ({
      id: item.id,
      label: `${item.item_code} — ${item.description}`,
      unit: item.unit,
      description: item.description,
    })),
  );

  useEffect(() => {
    if (open) {
      setProjectId(fixedProjectId ?? projects?.items[0]?.id ?? "");
      setNeededBy("");
      setNotes("");
      setLines([{ ...EMPTY }]);
    }
  }, [open, fixedProjectId, projects]);

  const setLine = (index: number, patch: Partial<Line>) =>
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, ...patch } : l)));

  const save = async () => {
    const filled = lines.filter((l) => l.description.trim() && Number(l.quantity) > 0);
    if (!projectId || filled.length === 0) {
      toast.error("Pick a project and add at least one line with a quantity");
      return;
    }
    try {
      await createMutation.mutateAsync({
        projectId,
        data: {
          needed_by: neededBy || null,
          notes: notes || null,
          items: filled.map((l) => ({
            boq_item_id: l.boq_item_id || null,
            description: l.description,
            unit: l.unit || "ea",
            quantity: l.quantity,
          })),
        },
      });
      await queryClient.invalidateQueries({ queryKey: ["/api/v1/requisitions"] });
      await queryClient.invalidateQueries({ queryKey: ["/api/v1/dashboard"] });
      toast.success("Request sent to procurement");
      onOpenChange(false);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Request Materials</DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground">
          Tell procurement what site needs. Linking a line to its BOQ item lets the resulting
          order price itself from what you last paid.
        </p>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            {!fixedProjectId && (
              <div className="space-y-1.5">
                <Label>Project</Label>
                <Select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                  {projects?.items.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.code} — {p.name}
                    </option>
                  ))}
                </Select>
              </div>
            )}
            <div className="space-y-1.5">
              <Label>Needed By</Label>
              <Input
                type="date"
                value={neededBy}
                onChange={(e) => setNeededBy(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>Items</Label>
            {lines.map((line, index) => (
              <div key={index} className="grid grid-cols-12 gap-2">
                <Select
                  className="col-span-4"
                  value={line.boq_item_id}
                  onChange={(e) => {
                    const match = boqItems.find((b) => b.id === e.target.value);
                    setLine(index, {
                      boq_item_id: e.target.value,
                      description: match?.description ?? line.description,
                      unit: match?.unit ?? line.unit,
                    });
                  }}
                >
                  <option value="">No BOQ link</option>
                  {boqItems.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </Select>
                <Input
                  className="col-span-4"
                  placeholder="What is needed"
                  value={line.description}
                  onChange={(e) => setLine(index, { description: e.target.value })}
                />
                <Input
                  className="col-span-2"
                  placeholder="Unit"
                  value={line.unit}
                  onChange={(e) => setLine(index, { unit: e.target.value })}
                />
                <Input
                  className="col-span-1"
                  type="number"
                  min="0"
                  step="any"
                  placeholder="Qty"
                  value={line.quantity}
                  onChange={(e) => setLine(index, { quantity: e.target.value })}
                />
                <Button
                  variant="ghost"
                  size="icon"
                  className="col-span-1 text-destructive"
                  disabled={lines.length === 1}
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
              <Plus /> Add Line
            </Button>
          </div>

          <div className="space-y-1.5">
            <Label>Notes</Label>
            <Textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Why it is needed and when — helps procurement prioritise"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={createMutation.isPending} onClick={() => void save()}>
            {createMutation.isPending ? "Sending…" : "Send Request"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
