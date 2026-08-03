import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-muted motion-reduce:animate-none", className)}
      {...props}
    />
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
