/** Custom in-house toast system (replaces sonner).
 *
 * Same call surface the app already uses — `toast.success(msg)`,
 * `toast.error(msg)`, `toast.info(msg)` — so swapping is an import change.
 * Renders as stacked cards top-right with the app's dropdown-in motion,
 * auto-dismissing (errors linger longer), dismissable by click.
 */

import { CheckCircle, Info, WarningCircle, X } from "@phosphor-icons/react";
import { useSyncExternalStore } from "react";
import { cn } from "@/lib/utils";

type Kind = "success" | "error" | "info" | "warning";

interface ToastItem {
  id: number;
  kind: Kind;
  message: string;
  leaving?: boolean;
}

let seq = 0;
let items: ToastItem[] = [];
const listeners = new Set<() => void>();

function emit() {
  items = [...items];
  for (const listener of listeners) listener();
}

function dismiss(id: number) {
  const item = items.find((t) => t.id === id);
  if (!item || item.leaving) return;
  item.leaving = true;
  emit();
  setTimeout(() => {
    items = items.filter((t) => t.id !== id);
    emit();
  }, 180);
}

function push(kind: Kind, message: string) {
  const id = ++seq;
  items = [...items.slice(-4), { id, kind, message }]; // keep at most 5
  emit();
  setTimeout(() => dismiss(id), kind === "error" ? 6000 : 4000);
  return id;
}

export const toast = {
  success: (message: string) => push("success", message),
  error: (message: string) => push("error", message),
  info: (message: string) => push("info", message),
  warning: (message: string) => push("warning", message),
};

const KIND_STYLES: Record<Kind, { border: string; icon: React.ReactNode }> = {
  success: {
    border: "border-l-success",
    icon: <CheckCircle size={18} weight="fill" className="text-success" />,
  },
  error: {
    border: "border-l-destructive",
    icon: <WarningCircle size={18} weight="fill" className="text-destructive" />,
  },
  info: {
    border: "border-l-primary",
    icon: <Info size={18} weight="fill" className="text-primary" />,
  },
  warning: {
    border: "border-l-warning",
    icon: <WarningCircle size={18} weight="fill" className="text-warning" />,
  },
};

/** Mount once (main.tsx). */
export function Toaster() {
  const current = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => items,
  );

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed right-4 top-4 z-[2000] flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2"
    >
      {current.map((item) => {
        const style = KIND_STYLES[item.kind];
        return (
          <div
            key={item.id}
            role="status"
            className={cn(
              "dropdown-in pointer-events-auto flex items-start gap-2.5 rounded-lg border border-l-4 bg-card p-3 shadow-lg",
              style.border,
              item.leaving && "opacity-0 transition-opacity duration-150",
            )}
          >
            <span className="mt-0.5 shrink-0">{style.icon}</span>
            <p className="flex-1 text-sm leading-snug">{item.message}</p>
            <button
              type="button"
              aria-label="Dismiss"
              className="shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              onClick={() => dismiss(item.id)}
            >
              <X size={13} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
