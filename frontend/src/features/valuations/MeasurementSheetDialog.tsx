import { useQueryClient } from "@tanstack/react-query";
import { Fragment, useEffect, useMemo, useState } from "react";
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
import { Skeleton } from "@/components/ui/skeleton";
import {
  useGetMeasurementContext,
  useSetMeasurement,
} from "@/lib/api/generated/endpoints";
import { moneyExact } from "@/lib/format";
import { cn } from "@/lib/utils";

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

export function MeasurementSheetDialog({
  valuationId,
  onOpenChange,
  retentionPct,
  previousCertified,
}: {
  valuationId: string | null;
  onOpenChange: (open: boolean) => void;
  retentionPct: string | null | undefined;
  previousCertified: string | undefined;
}) {
  const queryClient = useQueryClient();
  const { data: context, isLoading } = useGetMeasurementContext(valuationId ?? "", {
    query: { enabled: !!valuationId },
  });
  const saveMutation = useSetMeasurement();
  const [qty, setQty] = useState<Record<string, string>>({});

  useEffect(() => {
    if (context) {
      const initial: Record<string, string> = {};
      for (const section of context.sections) {
        for (const item of section.items) {
          if (item.current_qty !== null && item.current_qty !== undefined) {
            initial[item.boq_item_id] = String(item.current_qty);
          }
        }
      }
      setQty(initial);
    }
  }, [context]);

  const gross = useMemo(() => {
    let total = 0;
    for (const section of context?.sections ?? []) {
      for (const item of section.items) {
        const q = Number(qty[item.boq_item_id]) || 0;
        total += q * Number(item.rate);
      }
    }
    return total;
  }, [qty, context]);

  const retention = retentionPct ? (gross * Number(retentionPct)) / 100 : 0;
  const previous = Number(previousCertified ?? 0);
  const net = gross - retention - previous;

  const save = async () => {
    if (!valuationId) return;
    const lines = Object.entries(qty)
      .filter(([, value]) => Number(value) > 0)
      .map(([boq_item_id, value]) => ({ boq_item_id, qty_to_date: value }));
    try {
      await saveMutation.mutateAsync({ valuationId, data: { lines } });
      await queryClient.invalidateQueries();
      toast.success(
        lines.length === 0
          ? "Sheet cleared — valuation reverts to single-figure entry"
          : "Measurement saved — gross recomputed from the sheet",
      );
      onOpenChange(false);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={!!valuationId} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] max-w-4xl flex-col">
        <DialogHeader>
          <DialogTitle>Measurement Sheet</DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground">
          Enter the cumulative quantity executed to date per BOQ line. The gross valuation is
          computed bottom-up; over-measurement against the BOQ quantity is highlighted, not
          blocked.
        </p>

        <div className="min-h-0 flex-1 overflow-y-auto rounded-md border">
          {isLoading || !context ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 6 }, (_, i) => (
                <Skeleton key={i} className="h-9 w-full" />
              ))}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 bg-muted text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Item</th>
                  <th className="px-3 py-2 text-left font-medium">Description</th>
                  <th className="px-2 py-2 text-right font-medium">BOQ Qty</th>
                  <th className="px-2 py-2 text-right font-medium">Rate</th>
                  <th className="px-2 py-2 text-right font-medium">Prev.</th>
                  <th className="w-28 px-2 py-2 text-right font-medium">Qty to Date</th>
                  <th className="px-2 py-2 text-right font-medium">%</th>
                  <th className="px-3 py-2 text-right font-medium">Amount</th>
                </tr>
              </thead>
              <tbody>
                {context.sections.map((section) => (
                  <Fragment key={section.code}>
                    <tr className="border-t bg-muted/40">
                      <td colSpan={8} className="px-3 py-1.5 text-xs font-semibold uppercase">
                        {section.code} — {section.title}
                      </td>
                    </tr>
                    {section.items.map((item) => {
                      const value = qty[item.boq_item_id] ?? "";
                      const q = Number(value) || 0;
                      const boqQty = Number(item.boq_quantity);
                      const pctDone = boqQty > 0 ? (q / boqQty) * 100 : 0;
                      const over = boqQty > 0 && q > boqQty;
                      const amount = q * Number(item.rate);
                      return (
                        <tr
                          key={item.boq_item_id}
                          className="border-t transition-colors hover:bg-muted/30"
                        >
                          <td className="px-3 py-1.5 font-mono text-xs">{item.item_code}</td>
                          <td className="max-w-64 truncate px-3 py-1.5" title={item.description}>
                            {item.description}
                          </td>
                          <td className="px-2 py-1.5 text-right tabular-nums text-muted-foreground">
                            {boqQty.toLocaleString()} {item.unit}
                          </td>
                          <td className="px-2 py-1.5 text-right tabular-nums text-muted-foreground">
                            {moneyExact(item.rate)}
                          </td>
                          <td className="px-2 py-1.5 text-right tabular-nums text-muted-foreground">
                            {Number(item.previous_qty) > 0
                              ? Number(item.previous_qty).toLocaleString()
                              : "—"}
                          </td>
                          <td className="px-2 py-1.5">
                            <Input
                              type="number"
                              step="0.001"
                              min="0"
                              placeholder="0"
                              className={cn(
                                "h-8 text-right tabular-nums",
                                over && "border-warning text-warning",
                              )}
                              value={value}
                              onChange={(e) =>
                                setQty((prev) => ({
                                  ...prev,
                                  [item.boq_item_id]: e.target.value,
                                }))
                              }
                            />
                          </td>
                          <td
                            className={cn(
                              "px-2 py-1.5 text-right text-xs tabular-nums",
                              over ? "font-medium text-warning" : "text-muted-foreground",
                            )}
                          >
                            {q > 0 ? `${pctDone.toFixed(0)}%` : "—"}
                          </td>
                          <td className="px-3 py-1.5 text-right font-medium tabular-nums">
                            {q > 0 ? moneyExact(amount) : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="rounded-md border bg-muted/40 p-3 text-sm">
          <div className="flex justify-between py-0.5">
            <span className="text-muted-foreground">Gross measured to date</span>
            <span className="font-medium tabular-nums">{moneyExact(gross)}</span>
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
            <span>Net this valuation</span>
            <span className={cn("tabular-nums", net < 0 && "text-destructive")}>
              {moneyExact(net)}
            </span>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={saveMutation.isPending} onClick={() => void save()}>
            {saveMutation.isPending ? "Saving…" : "Save Measurement"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
