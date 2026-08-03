import type { HTMLAttributes } from "react";
import { TableCell, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-muted motion-reduce:animate-none", className)}
      {...props}
    />
  );
}

/** Table-shaped skeleton: renders real TableRow/TableCells so the column
 *  count, row height and padding match the finished table exactly — data
 *  swaps in with zero layout shift. Place inside <TableBody>. */
export function TableSkeleton({
  columns,
  rows = 5,
  widths,
}: {
  columns: number;
  rows?: number;
  /** optional per-column width classes (e.g. "w-24"); defaults vary naturally */
  widths?: string[];
}) {
  const defaults = ["w-32", "w-40", "w-24", "w-20", "w-28", "w-16", "w-24", "w-20"];
  return (
    <>
      {Array.from({ length: rows }, (_, r) => (
        <TableRow key={r} className="hover:bg-transparent">
          {Array.from({ length: columns }, (_, c) => (
            <TableCell key={c}>
              <Skeleton
                className={cn("h-4", widths?.[c] ?? defaults[(r + c) % defaults.length])}
              />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}

/** A row of StatCard-shaped placeholders (same footprint as StatCard). */
export function StatRowSkeleton({ count = 4 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="rounded-lg border bg-card p-4 shadow-sm">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="mt-2 h-6 w-32" />
          <Skeleton className="mt-1.5 h-3 w-20" />
        </div>
      ))}
    </>
  );
}

/** Card-list placeholders (link-card lists like RFQs/POs/dashboard cards). */
export function CardListSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="space-y-2" aria-busy="true">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="rounded-md border p-3">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0 flex-1 space-y-1.5">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-3 w-64" />
            </div>
            <Skeleton className="h-5 w-16 rounded-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Detail-page pending fallback: breadcrumb + title + meta grid + table. */
export function DetailSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading">
      <Skeleton className="mb-3 h-4 w-64" />
      <Skeleton className="h-7 w-72" />
      <Skeleton className="mt-2 h-4 w-96" />
      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatRowSkeleton count={4} />
      </div>
      <div className="mt-4 space-y-2">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    </div>
  );
}

/** Standard page-level loading state: header bar + content blocks. */
export function PageSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-7 w-56" />
      <Skeleton className="h-4 w-80" />
      <div className="space-y-2 pt-2">
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    </div>
  );
}
