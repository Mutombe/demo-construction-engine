import { useNavigate } from "@tanstack/react-router";
import {
  AddressBook,
  Buildings,
  ClipboardText,
  FileText,
  MagnifyingGlass,
  Package,
  Receipt,
  ShoppingCart,
  UsersThree,
} from "@phosphor-icons/react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { FLOATING_LAYER, useLayerDismissGuard } from "@/components/ui/floating-layer";
import { useGlobalSearch } from "@/lib/api/generated/endpoints";
import type { SearchHit } from "@/lib/api/generated/model";
import { cn } from "@/lib/utils";

/** Destinations the palette can jump to, mirroring the sidebar. Keeping the
 *  list here rather than importing the nav avoids a cycle with AppShell. */
export interface PaletteDestination {
  to: string;
  label: string;
  group: string;
  keywords?: string;
}

const TYPE_ICONS: Record<string, ReactNode> = {
  project: <Buildings />,
  client: <AddressBook />,
  supplier: <UsersThree />,
  purchase_order: <ShoppingCart />,
  rfq: <FileText />,
  requisition: <ClipboardText />,
  stock_item: <Package />,
  valuation: <Receipt />,
  expense: <Receipt />,
  worker: <UsersThree />,
};

/** Recent picks are remembered so the palette opens on what you use, not on
 *  an empty box. */
const useRecent = create<{ paths: string[]; push: (path: string) => void }>()(
  persist(
    (set) => ({
      paths: [],
      push: (path) =>
        set((state) => ({
          paths: [path, ...state.paths.filter((p) => p !== path)].slice(0, 5),
        })),
    }),
    { name: "erp-palette-recent" },
  ),
);

export const usePalette = create<{ open: boolean; setOpen: (open: boolean) => void }>(
  (set) => ({ open: false, setOpen: (open) => set({ open }) }),
);

interface PageRow {
  kind: "page";
  key: string;
  label: string;
  sublabel?: string;
  group: string;
  to: string;
}

type Row = PageRow | { kind: "record"; key: string; hit: SearchHit; group: string };

export function CommandPalette({
  destinations,
}: {
  destinations: PaletteDestination[];
}) {
  const navigate = useNavigate();
  const { open, setOpen } = usePalette();
  const recent = useRecent((s) => s.paths);
  const pushRecent = useRecent((s) => s.push);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [cursor, setCursor] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);

  // Ctrl/Cmd+K anywhere, and Escape to leave.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setDebounced("");
      setCursor(0);
    }
  }, [open]);

  // Typing is local and instant; the server is only asked once you pause, so
  // holding a key down does not fire a request per character.
  useEffect(() => {
    const id = setTimeout(() => setDebounced(query.trim()), 180);
    return () => clearTimeout(id);
  }, [query]);

  const { data: results, isFetching } = useGlobalSearch(
    { q: debounced },
    { query: { enabled: open && debounced.length >= 2 } },
  );

  const rows = useMemo<Row[]>(() => {
    const needle = query.trim().toLowerCase();
    const pageRows: PageRow[] = destinations
      .filter(
        (d) =>
          !needle ||
          d.label.toLowerCase().includes(needle) ||
          d.group.toLowerCase().includes(needle) ||
          (d.keywords ?? "").toLowerCase().includes(needle),
      )
      .map((d) => ({
        kind: "page" as const,
        key: `page:${d.to}`,
        label: d.label,
        sublabel: d.group,
        group: "Go to",
        to: d.to,
      }));

    if (!needle) {
      // Resting state: what you opened last, then everywhere you can go.
      const recentRows: PageRow[] = recent
        .map((path) => destinations.find((d) => d.to === path))
        .filter((d): d is PaletteDestination => !!d)
        .map((d) => ({
          kind: "page" as const,
          key: `recent:${d.to}`,
          label: d.label,
          sublabel: d.group,
          group: "Recent",
          to: d.to,
        }));
      const recentPaths = new Set(recentRows.map((r) => r.to));
      return [...recentRows, ...pageRows.filter((r) => !recentPaths.has(r.to))];
    }

    const recordRows: Row[] = (results?.hits ?? []).map((hit) => ({
      kind: "record" as const,
      key: `hit:${hit.type}:${hit.id}`,
      hit,
      group: hit.type_label,
    }));
    return [...pageRows, ...recordRows];
  }, [destinations, query, recent, results]);

  useEffect(() => setCursor(0), [rows.length, debounced]);

  const choose = (row: Row) => {
    const to = row.kind === "page" ? row.to : row.hit.url;
    if (row.kind === "page") pushRecent(to);
    setOpen(false);
    void navigate({ to });
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(c + 1, rows.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const row = rows[cursor];
      if (row) choose(row);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  // Keep the highlighted row in view when arrowing past the fold.
  useEffect(() => {
    listRef.current
      ?.querySelector(`[data-index="${cursor}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  useLayerDismissGuard(overlayRef, open);

  if (!open) return null;

  let lastGroup = "";

  return (
    <div
      ref={overlayRef}
      // z-50 put it level with dialogs, so Ctrl+K over an open modal opened it
      // underneath. It sits above dialogs and below confirm/toasts.
      className={cn(
        "fixed inset-0 z-[1800] flex items-start justify-center bg-black/40 p-4 pt-[12vh]",
        FLOATING_LAYER,
      )}
      onClick={() => setOpen(false)}
    >
      <div
        className="w-full max-w-xl overflow-hidden rounded-xl border bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2.5 border-b px-4">
          <MagnifyingGlass className="size-4 shrink-0 text-muted-foreground" />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search pages, projects, orders, stock…"
            className="h-12 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          {isFetching && (
            <span className="text-xs text-muted-foreground">searching…</span>
          )}
        </div>

        <div ref={listRef} className="max-h-[55vh] overflow-y-auto p-1.5">
          {rows.length === 0 && (
            <div className="px-3 py-8 text-center text-sm text-muted-foreground">
              {debounced.length >= 2
                ? `Nothing matches “${debounced}”`
                : "Keep typing to search records"}
            </div>
          )}
          {rows.map((row, index) => {
            const header = row.group !== lastGroup ? row.group : null;
            lastGroup = row.group;
            const active = index === cursor;
            return (
              <div key={row.key}>
                {header && (
                  <div className="px-2.5 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    {header}
                  </div>
                )}
                <button
                  type="button"
                  data-index={index}
                  onMouseEnter={() => setCursor(index)}
                  onClick={() => choose(row)}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-muted-foreground",
                    active && "bg-accent",
                  )}
                >
                  {row.kind === "page" ? (
                    <MagnifyingGlass />
                  ) : (
                    (TYPE_ICONS[row.hit.type] ?? <FileText />)
                  )}
                  <span className="min-w-0 flex-1 truncate">
                    {row.kind === "page" ? row.label : row.hit.label}
                    {row.kind === "record" && row.hit.sublabel && (
                      <span className="ml-2 text-xs text-muted-foreground">
                        {row.hit.sublabel}
                      </span>
                    )}
                    {row.kind === "page" && row.sublabel && (
                      <span className="ml-2 text-xs text-muted-foreground">
                        {row.sublabel}
                      </span>
                    )}
                  </span>
                  {row.kind === "record" && row.hit.code && (
                    <span className="shrink-0 font-mono text-xs text-muted-foreground">
                      {row.hit.code}
                    </span>
                  )}
                </button>
              </div>
            );
          })}
        </div>

        <div className="flex items-center gap-3 border-t px-3 py-2 text-[11px] text-muted-foreground">
          <span>
            <kbd className="rounded border px-1">↑</kbd>
            <kbd className="ml-0.5 rounded border px-1">↓</kbd> navigate
          </span>
          <span>
            <kbd className="rounded border px-1">↵</kbd> open
          </span>
          <span>
            <kbd className="rounded border px-1">esc</kbd> close
          </span>
        </div>
      </div>
    </div>
  );
}
