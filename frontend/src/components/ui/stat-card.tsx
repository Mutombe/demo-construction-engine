import type { ReactNode } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** Unified KPI/summary card used by the dashboard, valuations, payroll etc. */
export function StatCard({
  label,
  value,
  sub,
  icon,
  tone = "default",
  className,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon?: ReactNode;
  tone?: "default" | "positive" | "negative" | "brand";
  className?: string;
}) {
  return (
    <Card className={cn("transition-shadow hover:shadow-md", className)}>
      <CardContent className="flex items-start justify-between gap-3 p-4">
        <div className="min-w-0">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {label}
          </div>
          <div
            className={cn(
              "mt-1 truncate text-xl font-semibold tabular-nums",
              tone === "positive" && "text-success",
              tone === "negative" && "text-destructive",
              tone === "brand" && "text-primary",
            )}
          >
            {value}
          </div>
          {sub && <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>}
        </div>
        {icon && (
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary [&_svg]:size-4.5">
            {icon}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
