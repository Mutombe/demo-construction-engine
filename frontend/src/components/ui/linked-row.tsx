import { useQueryClient, type FetchQueryOptions } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useCallback, useRef, type HTMLAttributes, type ReactNode } from "react";
import { TableCell, TableRow } from "@/components/ui/table";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/* Every record is a destination; every row that represents one navigates to it.
   ClickableRow = the whole row is a big forgiving hit target with hover
   prefetch; RowActions = in-row controls that never hijack the navigation;
   EntityLink = an inline identifier that links to its own record. */

// Loose on purpose: orval emits concretely-typed query options and TS variance
// would otherwise reject every one of them.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyQueryOptions = FetchQueryOptions<any, any, any, any>;

/** Prefetch detail data on intent (hover/focus), throttled to once per row. */
function usePrefetchOnIntent(prefetch?: () => AnyQueryOptions) {
  const queryClient = useQueryClient();
  const done = useRef(false);
  return useCallback(() => {
    if (done.current || !prefetch) return;
    done.current = true;
    void queryClient.prefetchQuery(prefetch());
  }, [prefetch, queryClient]);
}

export function ClickableRow({
  to,
  params,
  search,
  prefetch,
  disabled,
  className,
  children,
  ...props
}: {
  to: string;
  params?: Record<string, string>;
  search?: Record<string, unknown>;
  /** orval getGetXQueryOptions(id) factory — fetched on hover so the click lands instantly */
  prefetch?: () => AnyQueryOptions;
  /** e.g. optimistic placeholder rows aren't navigable yet */
  disabled?: boolean;
  children: ReactNode;
} & HTMLAttributes<HTMLTableRowElement>) {
  const navigate = useNavigate();
  const onIntent = usePrefetchOnIntent(prefetch);

  const go = () => {
    if (disabled) return;
    void navigate({ to, params: params as never, search: search as never });
  };

  return (
    <TableRow
      role="link"
      tabIndex={disabled ? undefined : 0}
      className={cn(
        !disabled && "cursor-pointer focus-visible:bg-muted/60 focus-visible:outline-none",
        "transition-colors",
        className,
      )}
      onClick={go}
      onKeyDown={(e) => {
        if (e.key === "Enter" && e.target === e.currentTarget) go();
      }}
      onMouseEnter={onIntent}
      onFocus={onIntent}
      {...props}
    >
      {children}
    </TableRow>
  );
}

/** Cell whose contents (buttons, selects, menus) must not trigger row navigation. */
export function RowActions({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLTableCellElement>) {
  return (
    <TableCell
      className={className}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
      {...props}
    >
      {children}
    </TableCell>
  );
}

/** Inline reference to another record — a name/code/doc-number that is a link,
 *  safe to use inside a ClickableRow (stops propagation) with hover prefetch. */
export function EntityLink({
  to,
  params,
  search,
  prefetch,
  className,
  title,
  children,
}: {
  to: string;
  params?: Record<string, string>;
  search?: Record<string, unknown>;
  prefetch?: () => AnyQueryOptions;
  className?: string;
  /** Says where the link goes, for codes whose destination is not obvious. */
  title?: string;
  children: ReactNode;
}) {
  const onIntent = usePrefetchOnIntent(prefetch);
  const link = (
    <Link
      to={to}
      params={params as never}
      search={search as never}
      className={cn(
        "font-medium text-foreground underline-offset-2 transition-colors hover:text-primary hover:underline",
        className,
      )}
      onClick={(e) => e.stopPropagation()}
      onMouseEnter={onIntent}
      onFocus={onIntent}
    >
      {children}
    </Link>
  );
  return title ? <Tooltip content={title}>{link}</Tooltip> : link;
}
