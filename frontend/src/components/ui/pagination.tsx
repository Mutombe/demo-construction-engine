import { CaretDoubleLeft, CaretDoubleRight, CaretLeft, CaretRight } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";

/** Sized to fill a normal screen without pushing the pager below the fold.
 *  Small enough that a page arrives fast, large enough to avoid constant
 *  paging. */
export const DEFAULT_PAGE_SIZE = 15;

/** Standard table pager: "26–50 of 312" plus first/prev/next/last.
 *  Renders nothing while total is unknown or everything fits on one page,
 *  so small datasets stay chrome-free. Pairs with `keepPreviousData` — the
 *  previous rows stay visible while the next page loads. */
export const PAGE_SIZES = [15, 50, 100, 200];

export function PaginationBar({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  className,
}: {
  page: number;
  pageSize: number;
  total: number | undefined;
  onPageChange: (page: number) => void;
  /** Supply this on anything somebody works through in bulk. Reconciling a
   *  ledger fifteen rows at a time is not reconciling. */
  onPageSizeChange?: (pageSize: number) => void;
  className?: string;
}) {
  if (total === undefined) return null;
  // The size control has to stay reachable even when everything fits, or a
  // list that shrank to one page traps the reader on the small size.
  if (total <= pageSize && !onPageSizeChange) return null;
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
      <div className="flex items-center gap-3">
        <span className="tabular-nums">
          {total === 0
            ? "Nothing to show"
            : `${first.toLocaleString()}–${last.toLocaleString()} of ${total.toLocaleString()}`}
        </span>
        {onPageSizeChange && (
          <label className="flex items-center gap-1.5 text-xs">
            <span className="sr-only">Rows per page</span>
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="h-7 rounded-md border border-input bg-transparent px-1.5 text-xs"
              aria-label="Rows per page"
            >
              {PAGE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size} rows
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
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
