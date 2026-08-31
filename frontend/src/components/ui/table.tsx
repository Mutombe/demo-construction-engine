import { forwardRef, type HTMLAttributes, type TdHTMLAttributes, type ThHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/** `maxHeight` turns the table into its own scroll area and pins the header
 *  to the top of it. Worth doing on anything that can run past a screenful:
 *  scrolling a hundred rows of figures with the column names gone is how
 *  people read the wrong column. */
export const Table = forwardRef<
  HTMLTableElement,
  HTMLAttributes<HTMLTableElement> & { maxHeight?: string }
>(({ className, maxHeight, ...props }, ref) => (
  <div
    className={cn(
      "relative w-full overflow-auto",
      maxHeight &&
        "[&_thead_th]:sticky [&_thead_th]:top-0 [&_thead_th]:z-10 [&_thead_th]:bg-card",
    )}
    style={maxHeight ? { maxHeight } : undefined}
  >
    <table
      ref={ref}
      className={cn(
        "w-full caption-bottom text-sm",
        // Digits line up down the column and between pages, so a number that
        // changes length does not shift the ones around it.
        "[&_td.num]:text-right [&_td.num]:tabular-nums [&_th.num]:text-right",
        className,
      )}
      {...props}
    />
  </div>
));
Table.displayName = "Table";

export const TableHeader = forwardRef<HTMLTableSectionElement, HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => (
    <thead ref={ref} className={cn("[&_tr]:border-b", className)} {...props} />
  ),
);
TableHeader.displayName = "TableHeader";

export const TableBody = forwardRef<HTMLTableSectionElement, HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => (
    <tbody ref={ref} className={cn("[&_tr:last-child]:border-0", className)} {...props} />
  ),
);
TableBody.displayName = "TableBody";

export const TableRow = forwardRef<HTMLTableRowElement, HTMLAttributes<HTMLTableRowElement>>(
  ({ className, ...props }, ref) => (
    <tr
      ref={ref}
      className={cn("border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted", className)}
      {...props}
    />
  ),
);
TableRow.displayName = "TableRow";

export const TableHead = forwardRef<HTMLTableCellElement, ThHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <th
      ref={ref}
      className={cn(
        "h-9 px-3 text-left align-middle text-xs font-semibold uppercase tracking-wide text-muted-foreground",
        className,
      )}
      {...props}
    />
  ),
);
TableHead.displayName = "TableHead";

export const TableCell = forwardRef<HTMLTableCellElement, TdHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <td ref={ref} className={cn("px-3 py-2 align-middle", className)} {...props} />
  ),
);
TableCell.displayName = "TableCell";
