import { useQueryClient } from "@tanstack/react-query";
import { CaretDown, CaretRight, Plus, Trash } from "@phosphor-icons/react";
import { useState } from "react";
import { toast } from "@/lib/toast";
import { Badge } from "@/components/ui/badge";
import { confirmDialog } from "@/components/ui/confirm";
import { usePermission } from "@/features/auth/hooks";
import {
  useCreateItem,
  useCreateSection,
  useDeleteItem,
  useUpdateItem,
} from "@/lib/api/generated/endpoints";
import type { BoqItemRead, BoqTree } from "@/lib/api/generated/model";
import { moneyExact } from "@/lib/format";
import { cn } from "@/lib/utils";
import { EditableCell } from "./EditableCell";

const CATEGORIES = ["material", "labour", "plant", "subcontract", "preliminaries", "other"];

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Save failed"
  );
}

export function BoqSheet({ projectId, tree }: { projectId: string; tree: BoqTree }) {
  const queryClient = useQueryClient();
  const canWrite = usePermission("boq:write");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const updateItem = useUpdateItem();
  const createItem = useCreateItem();
  const deleteItem = useDeleteItem();
  const createSection = useCreateSection();

  const invalidate = () => queryClient.invalidateQueries();

  const patchItem = async (item: BoqItemRead, patch: Record<string, unknown>) => {
    try {
      await updateItem.mutateAsync({ itemId: item.id, data: patch });
      await invalidate();
    } catch (err) {
      toast.error(errDetail(err));
      await invalidate(); // revert visible state
    }
  };

  const addItem = async (sectionId: string, sectionItems: BoqItemRead[]) => {
    const nextNum = sectionItems.length + 1;
    const sectionCode = tree.sections.find((s) => s.id === sectionId)?.code ?? "X";
    try {
      await createItem.mutateAsync({
        sectionId,
        data: {
          item_code: `${sectionCode}.${nextNum}`,
          description: "New item — edit description",
          unit: "nr",
          quantity: "0",
          rate: "0",
        },
      });
      await invalidate();
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const addSection = async () => {
    const codes = tree.sections.map((s) => s.code);
    let code = String.fromCharCode(65 + tree.sections.length); // A, B, C...
    while (codes.includes(code)) code = `${code}X`;
    try {
      await createSection.mutateAsync({
        projectId,
        data: { code, title: "New section — rename me", sort_order: tree.sections.length + 1 },
      });
      await invalidate();
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const removeItem = async (item: BoqItemRead) => {
    if (
      !(await confirmDialog({
        title: "Delete item",
        message: `Delete item ${item.item_code}?`,
        tone: "danger",
      }))
    )
      return;
    try {
      await deleteItem.mutateAsync({ itemId: item.id });
      await invalidate();
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const toggle = (id: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const gridCols = canWrite
    ? "grid-cols-[90px_1fr_64px_90px_100px_110px_110px_90px_36px]"
    : "grid-cols-[90px_1fr_64px_90px_100px_110px_110px_90px]";

  return (
    <div className="rounded-lg border bg-card">
      <div
        className={cn(
          "grid items-center gap-px border-b bg-secondary/60 px-2 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground",
          gridCols,
        )}
      >
        <div className="px-2">Code</div>
        <div className="px-2">Description</div>
        <div className="px-2">Unit</div>
        <div className="px-2 text-right">Qty</div>
        <div className="px-2 text-right">Rate</div>
        <div className="px-2 text-right">Amount</div>
        <div className="px-2 text-right">Actual</div>
        <div className="px-2">Category</div>
        {canWrite && <div />}
      </div>

      {tree.sections.map((section) => {
        const isCollapsed = collapsed.has(section.id);
        const items = section.items ?? [];
        return (
          <div key={section.id}>
            <div
              className="flex cursor-pointer items-center justify-between border-b bg-secondary/40 px-3 py-2"
              onClick={() => toggle(section.id)}
            >
              <div className="flex items-center gap-1.5 text-sm font-semibold">
                {isCollapsed ? (
                  <CaretRight className="h-4 w-4" />
                ) : (
                  <CaretDown className="h-4 w-4" />
                )}
                {section.code} — {section.title}
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  {items.length} item{items.length === 1 ? "" : "s"}
                </span>
              </div>
              <div className="text-sm font-semibold tabular-nums">
                {moneyExact(section.subtotal)}
              </div>
            </div>

            {!isCollapsed &&
              items.map((item) => {
                const over =
                  Number(item.amount) > 0 && Number(item.actual_total) > Number(item.amount);
                return (
                  <div
                    key={item.id}
                    className={cn(
                      "grid items-stretch gap-px border-b transition-colors hover:bg-accent/40",
                      gridCols,
                      item.item_type === "variation" && "bg-warning/5",
                      item.item_type === "omission" && "bg-destructive/5 line-through opacity-70",
                    )}
                  >
                    <EditableCell
                      value={item.item_code}
                      onCommit={(v) => void patchItem(item, { item_code: v })}
                      disabled={!canWrite}
                      className="font-mono text-xs"
                    />
                    <div className="flex items-center gap-1">
                      <EditableCell
                        value={item.description}
                        onCommit={(v) => void patchItem(item, { description: v })}
                        disabled={!canWrite}
                      />
                      {item.item_type === "variation" && (
                        <Badge variant="warning" className="mr-1 shrink-0">
                          {item.variation_ref ?? "VO"}
                        </Badge>
                      )}
                    </div>
                    <EditableCell
                      value={item.unit}
                      onCommit={(v) => void patchItem(item, { unit: v })}
                      disabled={!canWrite}
                    />
                    <EditableCell
                      value={String(item.quantity ?? "0")}
                      display={Number(item.quantity).toLocaleString()}
                      onCommit={(v) => void patchItem(item, { quantity: v || "0" })}
                      align="right"
                      type="number"
                      disabled={!canWrite}
                    />
                    <EditableCell
                      value={String(item.rate ?? "0")}
                      display={Number(item.rate).toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                      })}
                      onCommit={(v) => void patchItem(item, { rate: v || "0" })}
                      align="right"
                      type="number"
                      disabled={!canWrite}
                    />
                    <div className="px-2 py-1.5 text-right text-sm font-medium tabular-nums">
                      {moneyExact(item.amount)}
                    </div>
                    <div
                      className={cn(
                        "px-2 py-1.5 text-right text-sm tabular-nums",
                        over ? "font-semibold text-destructive" : "text-muted-foreground",
                      )}
                    >
                      {Number(item.actual_total) ? moneyExact(item.actual_total) : "—"}
                    </div>
                    <div className="flex items-center px-1">
                      {canWrite ? (
                        <select
                          className="w-full rounded-sm bg-transparent py-1 text-xs capitalize hover:bg-accent focus:outline-none"
                          value={item.cost_category ?? "material"}
                          onChange={(e) =>
                            void patchItem(item, { cost_category: e.target.value })
                          }
                        >
                          {CATEGORIES.map((c) => (
                            <option key={c} value={c}>
                              {c}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className="px-1 text-xs capitalize text-muted-foreground">
                          {item.cost_category}
                        </span>
                      )}
                    </div>
                    {canWrite && (
                      <button
                        onClick={() => void removeItem(item)}
                        className="flex items-center justify-center text-muted-foreground hover:text-destructive"
                        title="Delete item"
                      >
                        <Trash className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                );
              })}

            {!isCollapsed && canWrite && (
              <button
                onClick={() => void addItem(section.id, items)}
                className="flex w-full items-center gap-1.5 border-b px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <Plus className="h-3.5 w-3.5" /> Add line to {section.code}
              </button>
            )}
          </div>
        );
      })}

      {canWrite && (
        <button
          onClick={() => void addSection()}
          className="flex w-full items-center gap-1.5 px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <Plus className="h-4 w-4" /> Add section
        </button>
      )}

      <div className="sticky bottom-0 flex items-center justify-between border-t bg-card px-4 py-3">
        <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Grand total (excl. omissions)
        </span>
        <span className="text-lg font-bold tabular-nums">{moneyExact(tree.grand_total)}</span>
      </div>
    </div>
  );
}
