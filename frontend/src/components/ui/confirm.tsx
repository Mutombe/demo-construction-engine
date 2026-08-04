/** Custom confirm dialog replacing the native browser confirm().
 *
 * Usage anywhere (no hook needed):
 *   if (!(await confirmDialog({ title: "Issue PO?", message: "…" }))) return;
 *
 * `<ConfirmHost/>` is mounted once in main.tsx. Promise resolves false on
 * cancel/Escape/overlay click; Enter confirms.
 */

import { Question, Warning } from "@phosphor-icons/react";
import { useEffect, useRef, useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";
import { FLOATING_LAYER, useLayerDismissGuard } from "@/components/ui/floating-layer";
import { cn } from "@/lib/utils";

export interface ConfirmOptions {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** "danger" renders the confirm button destructive. */
  tone?: "default" | "danger";
}

interface PendingConfirm extends ConfirmOptions {
  resolve: (ok: boolean) => void;
}

let pending: PendingConfirm | null = null;
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

export function confirmDialog(options: ConfirmOptions): Promise<boolean> {
  // If one is somehow already open, cancel it first.
  pending?.resolve(false);
  return new Promise<boolean>((resolve) => {
    pending = { ...options, resolve };
    emit();
  });
}

function settle(ok: boolean) {
  pending?.resolve(ok);
  pending = null;
  emit();
}

export function ConfirmHost() {
  const overlayRef = useRef<HTMLDivElement>(null);
  const current = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => pending,
  );

  useEffect(() => {
    if (!current) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") settle(false);
      if (e.key === "Enter") settle(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current]);

  useLayerDismissGuard(overlayRef, !!current);

  if (!current) return null;
  const danger = current.tone === "danger";

  return (
    <div
      ref={overlayRef}
      className={cn(
        "fixed inset-0 z-[1900] flex items-center justify-center bg-black/40 p-4",
        FLOATING_LAYER,
      )}
      onClick={() => settle(false)}
      role="presentation"
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-label={current.title ?? "Confirm"}
        className="dropdown-in w-full max-w-sm rounded-lg border bg-card p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3">
          <span
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
              danger ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary",
            )}
          >
            {danger ? <Warning size={18} weight="fill" /> : <Question size={18} weight="fill" />}
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-semibold">{current.title ?? "Are you sure?"}</h2>
            <p className="mt-1 whitespace-pre-line text-sm text-muted-foreground">
              {current.message}
            </p>
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" size="sm" autoFocus onClick={() => settle(false)}>
            {current.cancelLabel ?? "Cancel"}
          </Button>
          <Button
            size="sm"
            variant={danger ? "destructive" : "default"}
            onClick={() => settle(true)}
          >
            {current.confirmLabel ?? "Confirm"}
          </Button>
        </div>
      </div>
    </div>
  );
}
