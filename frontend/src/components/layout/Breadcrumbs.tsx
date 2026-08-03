import { Link, useRouter } from "@tanstack/react-router";
import { ArrowLeft, ChevronRight } from "lucide-react";
import { Fragment } from "react";

export interface Crumb {
  label: string;
  to?: string;
  params?: Record<string, string>;
  search?: Record<string, unknown>;
}

/** Dashboard › Section › This record — the trail back from any detail page.
 *  The last crumb is the current page (non-link); a ← Back affordance jumps to
 *  the previous crumb (falling back to history). */
export function Breadcrumbs({ items }: { items: Crumb[] }) {
  const router = useRouter();
  const parent = [...items].reverse().find((c, i) => i > 0 && c.to);

  return (
    <nav aria-label="Breadcrumb" className="mb-3 flex items-center gap-1.5 text-sm">
      <button
        type="button"
        title="Back"
        aria-label="Back"
        className="mr-1 flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        onClick={() => {
          if (parent?.to) {
            void router.navigate({
              to: parent.to,
              params: parent.params as never,
              search: parent.search as never,
            });
          } else {
            router.history.back();
          }
        }}
      >
        <ArrowLeft className="h-3.5 w-3.5" />
      </button>
      <Link to="/" className="text-muted-foreground transition-colors hover:text-foreground">
        Dashboard
      </Link>
      {items.map((crumb, i) => {
        const last = i === items.length - 1;
        return (
          <Fragment key={`${crumb.label}-${i}`}>
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60" />
            {last || !crumb.to ? (
              <span
                className={
                  last
                    ? "max-w-64 truncate font-medium text-foreground"
                    : "max-w-48 truncate text-muted-foreground"
                }
                aria-current={last ? "page" : undefined}
              >
                {crumb.label}
              </span>
            ) : (
              <Link
                to={crumb.to}
                params={crumb.params as never}
                search={crumb.search as never}
                className="max-w-48 truncate text-muted-foreground transition-colors hover:text-foreground"
              >
                {crumb.label}
              </Link>
            )}
          </Fragment>
        );
      })}
    </nav>
  );
}
