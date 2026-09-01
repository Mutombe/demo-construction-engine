import { Link, useRouterState } from "@tanstack/react-router";
import { ChartLineUp, ListChecks, Package, TrashSimple } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

/** Stocktaking is a step inside inventory, not a destination of its own, so it
 *  sits here as a tab. Both views stay separately addressable — the tabs
 *  navigate rather than swap local state — so links and refreshes still land. */
const TABS = [
  { to: "/inventory", label: "Stock Items", icon: <Package />, exact: true },
  { to: "/inventory/stocktake", label: "Stocktake", icon: <ListChecks />, exact: false },
  { to: "/inventory/insights", label: "Insights", icon: <ChartLineUp />, exact: false },
  { to: "/inventory/losses", label: "Losses", icon: <TrashSimple />, exact: false },
] as const;

export function InventoryTabs() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  return (
    <div className="mb-4 border-b">
      <nav className="-mb-px flex gap-1">
        {TABS.map((tab) => {
          const active = tab.exact
            ? pathname === tab.to
            : pathname.startsWith(tab.to);
          return (
            <Link
              key={tab.to}
              to={tab.to}
              className={cn(
                "flex items-center gap-1.5 border-b-2 px-3.5 py-2 text-sm font-medium transition-colors",
                active
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:border-border hover:text-foreground",
              )}
            >
              {tab.icon}
              {tab.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
