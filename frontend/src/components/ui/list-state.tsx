import { ArrowClockwise, WarningCircle } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { errDetail } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

/** Why a table has no rows.
 *
 *  Loading, failed and genuinely empty look identical to a reader unless the
 *  screen says which it is, and defaulting to "nothing here" tells somebody
 *  their data is gone when the truth is that the request failed. That is the
 *  one wrong answer of the three, because it is the one they will act on.
 */
export function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const detail = errDetail(error);
  const status = (error as { response?: { status?: number } })?.response?.status;

  // A permission failure is not a fault and there is nothing to retry, so it
  // is said plainly rather than dressed up as an error.
  const forbidden = status === 403;

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 px-6 py-12 text-center",
        className,
      )}
    >
      <div
        className={cn(
          "flex h-12 w-12 items-center justify-center rounded-full [&_svg]:size-6",
          forbidden ? "bg-muted text-muted-foreground" : "bg-destructive/10 text-destructive",
        )}
      >
        <WarningCircle />
      </div>
      <div className="text-sm font-medium">
        {forbidden ? "Not yours to see" : "This did not load"}
      </div>
      <p className="max-w-sm text-xs text-muted-foreground">
        {forbidden
          ? "Your role does not cover this. Nothing is wrong — ask an administrator if you need it."
          : detail}
      </p>
      {!forbidden && onRetry && (
        <Button variant="outline" size="sm" className="mt-2" onClick={onRetry}>
          <ArrowClockwise /> Try Again
        </Button>
      )}
    </div>
  );
}

/** Picks between the three, in the order that keeps them honest.
 *
 *  Failure is checked before emptiness on purpose: a request that errored has
 *  no rows either, and reporting that as "nothing here" is the answer people
 *  act on wrongly.
 */
export function ListState({
  isLoading,
  isError,
  error,
  isEmpty,
  onRetry,
  skeleton,
  empty,
  children,
}: {
  isLoading: boolean;
  isError: boolean;
  error?: unknown;
  isEmpty: boolean;
  onRetry?: () => void;
  skeleton: ReactNode;
  empty: ReactNode;
  children: ReactNode;
}) {
  if (isError) return <ErrorState error={error} onRetry={onRetry} />;
  if (isLoading) return <>{skeleton}</>;
  if (isEmpty) return <>{empty}</>;
  return <>{children}</>;
}
