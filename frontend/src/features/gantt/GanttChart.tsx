import { CaretDown, CaretRight, Diamond } from "@phosphor-icons/react";
import { Fragment, useState } from "react";
import type { GanttPayload } from "@/lib/api/generated/model";
import { cn } from "@/lib/utils";
import {
  HEADER_H,
  NAME_W,
  ROW_H,
  useGanttLayout,
  type GanttRowModel,
  type Zoom,
} from "./useGanttLayout";

const STATUS_COLORS: Record<string, string> = {
  not_started: "var(--muted-foreground)",
  in_progress: "var(--primary)",
  blocked: "var(--destructive)",
  done: "var(--success)",
  cancelled: "var(--border)",
};

export function GanttChart({ payload }: { payload: GanttPayload }) {
  const [zoom, setZoom] = useState<Zoom>("week");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const layout = useGanttLayout(payload, zoom, collapsed);

  if (!layout) return null;
  const { rows, totalWidth, months, ticks, todayX, barFor, actualBarFor } = layout;
  const bodyHeight = rows.length * ROW_H;

  const togglePhase = (id: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const rowById = new Map(rows.map((r) => [r.id, r] as const));

  return (
    <div className="rounded-lg border bg-card">
      <div className="flex items-center justify-between border-b p-2.5">
        <div className="flex items-center gap-4 px-1 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-5 rounded-sm bg-primary" /> Planned
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-1.5 w-5 rounded-sm bg-warning" /> Actual
          </span>
          <span className="flex items-center gap-1.5">
            <Diamond className="h-3 w-3 text-primary" /> Milestone
          </span>
        </div>
        <div className="flex gap-1">
          {(["day", "week", "month"] as const).map((z) => (
            <button
              key={z}
              onClick={() => setZoom(z)}
              className={cn(
                "rounded-md px-2.5 py-1 text-xs font-medium capitalize transition-colors",
                zoom === z ? "bg-primary text-primary-foreground" : "hover:bg-accent",
              )}
            >
              {z}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-auto" style={{ maxHeight: "calc(100vh - 320px)" }}>
        <div style={{ width: NAME_W + totalWidth, position: "relative" }}>
          {/* Header */}
          <div
            className="sticky top-0 z-30 flex border-b bg-card"
            style={{ height: HEADER_H }}
          >
            <div
              className="sticky left-0 z-40 flex items-end border-r bg-card px-3 pb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
              style={{ width: NAME_W, minWidth: NAME_W }}
            >
              Phase / Task
            </div>
            <div className="relative" style={{ width: totalWidth }}>
              {months.map((m) => (
                <div
                  key={`${m.label}-${m.x}`}
                  className="absolute top-0 flex h-5 items-center border-r px-1.5 text-[11px] font-medium text-muted-foreground"
                  style={{ left: m.x, width: m.width }}
                >
                  <span className="truncate">{m.label}</span>
                </div>
              ))}
              {ticks.map((t) => (
                <div
                  key={t.x}
                  className="absolute bottom-0 h-5 border-l pl-0.5 text-[10px] text-muted-foreground"
                  style={{ left: t.x }}
                >
                  {t.label}
                </div>
              ))}
            </div>
          </div>

          {/* Body */}
          <div className="relative" style={{ height: bodyHeight }}>
            {/* Row stripes + names */}
            {rows.map((row) => (
              <Fragment key={row.id}>
                <div
                  className={cn(
                    "absolute left-0 right-0 border-b",
                    row.kind === "phase" && "bg-secondary/50",
                  )}
                  style={{ top: row.y * ROW_H, height: ROW_H }}
                />
                <div
                  className={cn(
                    "sticky-name absolute z-20 flex items-center gap-1 border-b border-r bg-card px-3 text-sm",
                    row.kind === "phase" ? "bg-secondary font-semibold" : "",
                  )}
                  style={{
                    top: row.y * ROW_H,
                    height: ROW_H,
                    width: NAME_W,
                    minWidth: NAME_W,
                    position: "sticky",
                    left: 0,
                  }}
                >
                  {row.kind === "phase" ? (
                    <button
                      onClick={() => togglePhase(row.id)}
                      className="flex min-w-0 items-center gap-1 text-left"
                    >
                      {collapsed.has(row.id) ? (
                        <CaretRight className="h-3.5 w-3.5 shrink-0" />
                      ) : (
                        <CaretDown className="h-3.5 w-3.5 shrink-0" />
                      )}
                      <span className="truncate">{row.name}</span>
                    </button>
                  ) : (
                    <span className="flex min-w-0 items-center gap-1.5 pl-5">
                      {row.isMilestone && <Diamond className="h-3 w-3 shrink-0 text-primary" />}
                      <span className="truncate" title={`${row.wbs ?? ""} ${row.name}`}>
                        {row.wbs && (
                          <span className="mr-1 font-mono text-xs text-muted-foreground">
                            {row.wbs}
                          </span>
                        )}
                        {row.name}
                      </span>
                    </span>
                  )}
                </div>
              </Fragment>
            ))}

            {/* Timeline canvas */}
            <div
              className="absolute top-0"
              style={{ left: NAME_W, width: totalWidth, height: bodyHeight }}
            >
              {/* Dependency arrows */}
              <svg
                className="pointer-events-none absolute inset-0 z-10"
                width={totalWidth}
                height={bodyHeight}
              >
                {payload.dependencies.map((dep) => {
                  const from = rowById.get(dep.predecessor_id);
                  const to = rowById.get(dep.successor_id);
                  if (!from || !to) return null;
                  const fromBar = barFor(from);
                  const toBar = barFor(to);
                  if (!fromBar || !toBar) return null;
                  const x1 = fromBar.x + fromBar.width;
                  const y1 = from.y * ROW_H + ROW_H / 2;
                  const x2 = toBar.x;
                  const y2 = to.y * ROW_H + ROW_H / 2;
                  const elbow = Math.max(x1 + 8, x2 - 8);
                  const path = `M ${x1} ${y1} L ${x1 + 8} ${y1} L ${x1 + 8} ${y2} L ${x2 - 4} ${y2}`;
                  const pathBack =
                    x2 > x1 + 16
                      ? `M ${x1} ${y1} L ${elbow} ${y1} L ${elbow} ${y2} L ${x2 - 4} ${y2}`
                      : path;
                  return (
                    <g key={`${dep.predecessor_id}-${dep.successor_id}`}>
                      <path
                        d={pathBack}
                        fill="none"
                        stroke="var(--muted-foreground)"
                        strokeWidth={1.2}
                        opacity={0.55}
                      />
                      <polygon
                        points={`${x2 - 4},${y2 - 3.5} ${x2 - 4},${y2 + 3.5} ${x2 + 1},${y2}`}
                        fill="var(--muted-foreground)"
                        opacity={0.7}
                      />
                    </g>
                  );
                })}
              </svg>

              {/* Bars */}
              {rows.map((row) => {
                const planned = barFor(row);
                const actual = actualBarFor(row);
                const color = STATUS_COLORS[row.status] ?? "var(--primary)";
                const centerY = row.y * ROW_H + ROW_H / 2;
                return (
                  <Fragment key={row.id}>
                    {row.isMilestone && planned ? (
                      <div
                        className="absolute z-10"
                        style={{ left: planned.x - 6, top: centerY - 6 }}
                        title={row.name}
                      >
                        <div
                          className="h-3 w-3 rotate-45 border-2"
                          style={{
                            borderColor: color,
                            backgroundColor: row.progress === 100 ? color : "var(--card)",
                          }}
                        />
                      </div>
                    ) : (
                      planned && (
                        <div
                          className={cn(
                            "absolute z-10 rounded-sm",
                            row.kind === "phase" ? "opacity-90" : "",
                          )}
                          style={{
                            left: planned.x,
                            top: centerY - (row.kind === "phase" ? 4 : 8),
                            width: planned.width,
                            height: row.kind === "phase" ? 8 : 16,
                            backgroundColor:
                              row.kind === "phase" ? "var(--sidebar)" : "var(--secondary)",
                            border: row.kind === "phase" ? "none" : `1px solid ${color}`,
                          }}
                          title={`${row.name} · ${row.progress}%`}
                        >
                          {row.kind === "task" && (
                            <div
                              className="h-full rounded-[1px]"
                              style={{
                                width: `${row.progress}%`,
                                backgroundColor: color,
                                opacity: 0.75,
                              }}
                            />
                          )}
                        </div>
                      )
                    )}
                    {actual && row.kind === "task" && !row.isMilestone && (
                      <div
                        className="absolute z-10 rounded-sm"
                        style={{
                          left: actual.x,
                          top: centerY + 9,
                          width: actual.width,
                          height: 4,
                          backgroundColor: "var(--warning)",
                        }}
                        title={`Actual: ${row.name}`}
                      />
                    )}
                  </Fragment>
                );
              })}

              {/* Today line */}
              {todayX !== null && (
                <div
                  className="absolute top-0 z-20 w-px bg-destructive"
                  style={{ left: todayX, height: bodyHeight }}
                >
                  <div className="absolute -left-[14px] -top-0 rounded-b bg-destructive px-1 text-[9px] font-semibold text-destructive-foreground">
                    today
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export type { GanttRowModel };
