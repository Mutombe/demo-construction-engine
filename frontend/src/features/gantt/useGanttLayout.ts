import {
  addDays,
  differenceInCalendarDays,
  eachMonthOfInterval,
  eachWeekOfInterval,
  endOfMonth,
  max as maxDate,
  min as minDate,
  parseISO,
  startOfWeek,
} from "date-fns";
import { useMemo } from "react";
import type { GanttPayload } from "@/lib/api/generated/model";

export type Zoom = "day" | "week" | "month";

export const PX_PER_DAY: Record<Zoom, number> = { day: 30, week: 9, month: 3 };
export const ROW_H = 36;
export const NAME_W = 260;
export const HEADER_H = 44;

export interface GanttRowModel {
  kind: "phase" | "task";
  id: string;
  phaseId: string | null;
  name: string;
  wbs: string | null;
  status: string;
  progress: number;
  plannedStart: Date | null;
  plannedEnd: Date | null;
  actualStart: Date | null;
  actualEnd: Date | null;
  isMilestone: boolean;
  assignee: string | null;
  y: number; // row index among visible rows
  // Critical path analysis (tasks only; phases carry no float)
  isCritical: boolean;
  totalFloat: number | null;
  baselineStart: Date | null;
  baselineEnd: Date | null;
  slippageDays: number | null;
}

export interface GanttLayout {
  rows: GanttRowModel[];
  rangeStart: Date;
  totalDays: number;
  totalWidth: number;
  pxPerDay: number;
  months: { label: string; x: number; width: number }[];
  ticks: { label: string; x: number }[];
  todayX: number | null;
  dateToX: (d: Date) => number;
  barFor: (row: GanttRowModel) => { x: number; width: number } | null;
  actualBarFor: (row: GanttRowModel) => { x: number; width: number } | null;
  baselineBarFor: (row: GanttRowModel) => { x: number; width: number } | null;
}

const parse = (value: string | null | undefined): Date | null =>
  value ? parseISO(value) : null;

export function useGanttLayout(
  payload: GanttPayload | undefined,
  zoom: Zoom,
  collapsed: Set<string>,
): GanttLayout | null {
  return useMemo(() => {
    if (!payload) return null;
    const pxPerDay = PX_PER_DAY[zoom];

    const phaseRows = payload.phases.map((p) => ({
      kind: "phase" as const,
      id: p.id,
      phaseId: p.id,
      name: p.name,
      wbs: null,
      status: p.status,
      progress: 0,
      plannedStart: parse(p.planned_start),
      plannedEnd: parse(p.planned_end),
      actualStart: parse(p.actual_start),
      actualEnd: parse(p.actual_end),
      isMilestone: false,
      assignee: null,
      y: 0,
      isCritical: false,
      totalFloat: null,
      baselineStart: null,
      baselineEnd: null,
      slippageDays: null,
    }));

    const taskRow = (t: (typeof payload.tasks)[number]): GanttRowModel => ({
      kind: "task",
      id: t.id,
      phaseId: t.phase_id ?? null,
      name: t.name,
      wbs: t.wbs_code ?? null,
      status: t.status,
      progress: t.progress_pct,
      plannedStart: parse(t.planned_start),
      plannedEnd: parse(t.planned_end),
      actualStart: parse(t.actual_start),
      actualEnd: parse(t.actual_end),
      isMilestone: t.is_milestone,
      assignee: t.assignee_name ?? null,
      y: 0,
      isCritical: t.is_critical ?? false,
      totalFloat: t.total_float ?? null,
      baselineStart: parse(t.baseline_start),
      baselineEnd: parse(t.baseline_end),
      slippageDays: t.slippage_days ?? null,
    });

    const rows: GanttRowModel[] = [];
    for (const phase of phaseRows) {
      rows.push(phase);
      if (!collapsed.has(phase.id)) {
        rows.push(...payload.tasks.filter((t) => t.phase_id === phase.id).map(taskRow));
      }
    }
    const orphans = payload.tasks.filter((t) => !t.phase_id).map(taskRow);
    rows.push(...orphans);
    rows.forEach((r, i) => (r.y = i));

    const allDates = rows
      .flatMap((r) => [r.plannedStart, r.plannedEnd, r.actualStart, r.actualEnd])
      .filter((d): d is Date => d !== null);
    const today = new Date();
    const rawStart = allDates.length ? minDate([...allDates, today]) : today;
    const rawEnd = allDates.length ? maxDate([...allDates, today]) : addDays(today, 30);
    const rangeStart = startOfWeek(addDays(rawStart, -7), { weekStartsOn: 1 });
    const rangeEnd = addDays(rawEnd, 14);
    const totalDays = differenceInCalendarDays(rangeEnd, rangeStart) + 1;
    const totalWidth = totalDays * pxPerDay;

    const dateToX = (d: Date) => differenceInCalendarDays(d, rangeStart) * pxPerDay;

    const months = eachMonthOfInterval({ start: rangeStart, end: rangeEnd }).map((m) => {
      const from = maxDate([m, rangeStart]);
      const to = minDate([endOfMonth(m), rangeEnd]);
      return {
        label: m.toLocaleDateString("en-US", { month: "short", year: "2-digit" }),
        x: dateToX(from),
        width: (differenceInCalendarDays(to, from) + 1) * pxPerDay,
      };
    });

    let ticks: { label: string; x: number }[] = [];
    if (zoom === "day") {
      ticks = Array.from({ length: totalDays }, (_, i) => {
        const d = addDays(rangeStart, i);
        return { label: String(d.getDate()), x: i * pxPerDay };
      }).filter((_, i) => i % 1 === 0);
    } else if (zoom === "week") {
      ticks = eachWeekOfInterval(
        { start: rangeStart, end: rangeEnd },
        { weekStartsOn: 1 },
      ).map((w) => ({ label: String(w.getDate()), x: dateToX(w) }));
    }

    const todayX =
      today >= rangeStart && today <= rangeEnd ? dateToX(today) + pxPerDay / 2 : null;

    const barFor = (row: GanttRowModel) => {
      if (!row.plannedStart || !row.plannedEnd) return null;
      const x = dateToX(row.plannedStart);
      const width = Math.max(
        (differenceInCalendarDays(row.plannedEnd, row.plannedStart) + 1) * pxPerDay,
        4,
      );
      return { x, width };
    };
    const actualBarFor = (row: GanttRowModel) => {
      if (!row.actualStart) return null;
      const end = row.actualEnd ?? today;
      const x = dateToX(row.actualStart);
      const width = Math.max((differenceInCalendarDays(end, row.actualStart) + 1) * pxPerDay, 4);
      return { x, width };
    };

    const baselineBarFor = (row: GanttRowModel) => {
      if (!row.baselineStart || !row.baselineEnd) return null;
      const x = dateToX(row.baselineStart);
      const width = Math.max(
        (differenceInCalendarDays(row.baselineEnd, row.baselineStart) + 1) * pxPerDay,
        4,
      );
      return { x, width };
    };

    return {
      rows,
      rangeStart,
      totalDays,
      totalWidth,
      pxPerDay,
      months,
      ticks,
      todayX,
      dateToX,
      barFor,
      actualBarFor,
      baselineBarFor,
    };
  }, [payload, zoom, collapsed]);
}
