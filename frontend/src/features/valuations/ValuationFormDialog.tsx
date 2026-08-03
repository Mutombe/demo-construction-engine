import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
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
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateValuation,
  useUpdateValuation,
} from "@/lib/api/generated/endpoints";
import type { RevenueSummary, ValuationRead } from "@/lib/api/generated/model";
import { errDetail } from "@/lib/api/errors";
import { addRow, optimistic, tempId } from "@/lib/api/optimistic";
import { moneyExact } from "@/lib/format";

export function ValuationFormDialog({
  open,
  onOpenChange,
  projectId,
  summary,
  retentionPct,
  valuation,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  summary: RevenueSummary | undefined;
  retentionPct: string | null | undefined;
  valuation?: ValuationRead;
}) {
  const queryClient = useQueryClient();
  const listPrefix = `/api/v1/projects/${projectId}/valuations`;
  const createMutation = useCreateValuation({
    mutation: optimistic(queryClient, {
      prefixes: [listPrefix],
      invalidate: ["/api/v1/projects", "/api/v1/valuations"],
      successToast: "Draft valuation created",
      apply: (old, vars: { projectId: string; data: Record<string, unknown> }) => {
        const grossNum = Number(vars.data.gross_valuation) || 0;
        const retention = retentionPct ? (grossNum * Number(retentionPct)) / 100 : 0;
        const previous = Number(summary?.invoiced_to_date ?? 0);
        return addRow(() => ({
          id: tempId(),
          project_id: vars.projectId,
          doc_number: "INV-…",
          valuation_number: (summary?.valuation_count ?? 0) + 1,
          status: "draft",
          retention_amount: String(retention),
          previous_certified: String(previous),
          net_certified: String(grossNum - retention - previous),
          issued_date: null,
          paid_date: null,
          is_measured: false,
          created_at: new Date().toISOString(),
          ...vars.data,
        }))(old);
      },
    }),
  });
  const updateMutation = useUpdateValuation();

  const [periodEnd, setPeriodEnd] = useState("");
  const [gross, setGross] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (open) {
      setPeriodEnd(valuation?.period_end ?? new Date().toISOString().slice(0, 10));
      setGross(valuation?.gross_valuation ?? summary?.suggested_gross ?? "");
      setNotes(valuation?.notes ?? "");
    }
  }, [open, valuation, summary]);

  // Live preview mirroring the backend math: retention = gross × pct/100,
  // net = gross − retention − previously certified.
  const grossNum = Number(gross) || 0;
  const retention = retentionPct ? (grossNum * Number(retentionPct)) / 100 : 0;
  const previous = valuation
    ? Number(valuation.previous_certified)
    : Number(summary?.invoiced_to_date ?? 0);
  const net = grossNum - retention - previous;

  const save = async () => {
    if (!periodEnd || !gross) {
      toast.error("Period end and gross valuation are required");
      return;
    }
    if (valuation) {
      // Edits recompute server-side figures; keep the confirmed round-trip.
      try {
        await updateMutation.mutateAsync({
          valuationId: valuation.id,
          data: { period_end: periodEnd, gross_valuation: gross, notes: notes || null },
        });
        await queryClient.invalidateQueries({ queryKey: ["/api/v1/projects"] });
        await queryClient.invalidateQueries({ queryKey: ["/api/v1/valuations"] });
        toast.success("Valuation updated");
        onOpenChange(false);
      } catch (err) {
        toast.error(errDetail(err));
      }
      return;
    }
    // Optimistic create: close now, placeholder row settles or rolls back.
    onOpenChange(false);
    void createMutation
      .mutateAsync({
        projectId,
        data: { period_end: periodEnd, gross_valuation: gross, notes: notes || null },
      })
      .catch(() => undefined);
  };

  const pending = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{valuation ? `Edit ${valuation.doc_number}` : "New valuation"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Period ending</Label>
              <Input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Gross valuation to date (USD)</Label>
              <Input
                type="number"
                step="0.01"
                min="0.01"
                value={gross}
                onChange={(e) => setGross(e.target.value)}
              />
              {summary?.suggested_gross && !valuation && (
                <p className="text-xs text-muted-foreground">
                  Suggested from progress: {moneyExact(summary.suggested_gross)}
                </p>
              )}
            </div>
          </div>

          <div className="rounded-md border bg-muted/40 p-3 text-sm">
            <div className="flex justify-between py-0.5">
              <span className="text-muted-foreground">Gross work certified</span>
              <span className="tabular-nums">{moneyExact(grossNum)}</span>
            </div>
            <div className="flex justify-between py-0.5">
              <span className="text-muted-foreground">
                Less retention {retentionPct ? `(${Number(retentionPct)}%)` : "(none)"}
              </span>
              <span className="tabular-nums">− {moneyExact(retention)}</span>
            </div>
            <div className="flex justify-between py-0.5">
              <span className="text-muted-foreground">Less previously certified</span>
              <span className="tabular-nums">− {moneyExact(previous)}</span>
            </div>
            <div className="mt-1 flex justify-between border-t pt-1.5 font-semibold">
              <span>Net certified this valuation</span>
              <span className={net < 0 ? "text-destructive tabular-nums" : "tabular-nums"}>
                {moneyExact(net)}
              </span>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Notes</Label>
            <Textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Work covered by this valuation…"
            />
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button disabled={pending} onClick={() => void save()}>
              {pending ? "Saving…" : valuation ? "Save changes" : "Create draft"}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
