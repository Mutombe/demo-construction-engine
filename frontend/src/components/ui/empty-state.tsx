import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Designed empty state: icon in a soft ring, title, hint, optional CTA. */
export function EmptyState({
  icon,
  title,
  hint,
  action,
  className,
}: {
  icon: ReactNode;
  title: string;
  hint?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 px-6 py-12 text-center",
        className,
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary [&_svg]:size-6">
        {icon}
      </div>
      <div className="text-sm font-medium">{title}</div>
      {hint && <p className="max-w-sm text-xs text-muted-foreground">{hint}</p>}
      {action && <div className="pt-2">{action}</div>}
    </div>
  );
}
