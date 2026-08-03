import { CaretDoubleLeft, CaretDoubleRight, CaretLeft, CaretRight } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";

export const DEFAULT_PAGE_SIZE = 25;

/** Standard table pager: "26–50 of 312" plus first/prev/next/last.
 *  Renders nothing while total is unknown or everything fits on one page,
 *  so small datasets stay chrome-free. Pairs with `keepPreviousData` — the
 *  previous rows stay visible while the next page loads. */
export function PaginationBar({
  page,
  pageSize,
  total,
  onPageChange,
  className,
}: {
  page: number;
  pageSize: number;
  total: number | undefined;
  onPageChange: (page: number) => void;
  className?: string;
}) {
  if (total === undefined || total <= pageSize) return null;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);

  return (
    <div
      className={
        className ??
        "flex items-center justify-between gap-3 border-t px-3 py-2 text-sm text-muted-foreground"
      }
    >
      <span className="tabular-nums">
        {first.toLocaleString()}–{last.toLocaleString()} of {total.toLocaleString()}
      </span>
      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          disabled={page <= 1}
          aria-label="First page"
          onClick={() => onPageChange(1)}
        >
          <CaretDoubleLeft />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          disabled={page <= 1}
          aria-label="Previous page"
          onClick={() => onPageChange(page - 1)}
        >
          <CaretLeft />
        </Button>
        <span className="min-w-16 text-center text-xs tabular-nums">
          Page {page} / {totalPages}
        </span>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          disabled={page >= totalPages}
          aria-label="Next page"
          onClick={() => onPageChange(page + 1)}
        >
          <CaretRight />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          disabled={page >= totalPages}
          aria-label="Last page"
          onClick={() => onPageChange(totalPages)}
        >
          <CaretDoubleRight />
        </Button>
      </div>
    </div>
  );
}
