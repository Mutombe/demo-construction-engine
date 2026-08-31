import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { AddressBook, Bank, Buildings, CalendarBlank, CaretDoubleLeft, CaretDoubleRight, ChartBar, ClipboardText, Gear, MagnifyingGlass, HardHat, MapTrifold, Money, Package, Receipt, ShieldCheck, ShoppingCart, SignOut, SquaresFour, Tray, Truck, UsersThree, DeviceMobile, Handshake, List, X } from "@phosphor-icons/react";
import { ClaudeIcon } from "@/components/ui/claude-icon";
import { useEffect, useState, type ReactNode } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { Button } from "@/components/ui/button";
import { logout } from "@/features/auth/api";
import { useAuth } from "@/features/auth/hooks";
import { NotificationBell } from "@/features/notifications/NotificationBell";
import { SyncIndicator } from "@/features/offline/SyncIndicator";
import {
  CommandPalette,
  usePalette,
  type PaletteDestination,
} from "@/features/search/CommandPalette";
import { can, type Permission } from "@/features/auth/permissions";
import { useNavCounts } from "@/lib/api/generated/endpoints";
import { ROLE_LABELS } from "@/lib/format";
import { cn } from "@/lib/utils";

const useSidebar = create<{ collapsed: boolean; toggle: () => void }>()(
  persist(
    (set) => ({ collapsed: false, toggle: () => set((s) => ({ collapsed: !s.collapsed })) }),
    { name: "erp-sidebar" },
  ),
);

interface NavItem {
  to?: string;
  label: string;
  icon: ReactNode;
  permission?: Permission;
  soon?: boolean;
}

interface NavGroup {
  /** Undefined for the pinned items at the top, which carry no header. */
  title?: string;
  items: NavItem[];
}

/** Grouped by business function so new modules have an obvious home:
 *  accounting and invoicing land under Finance, CRM and contracts under
 *  Commercial, without the sidebar growing another flat row each time.
 *
 *  A page earns a row here only if it is somewhere you START work. Anything
 *  that is a step inside another workflow (stocktaking, raising an adjustment)
 *  lives as a view inside its parent page instead.
 */
const NAV: NavGroup[] = [
  {
    items: [
      { to: "/", label: "Dashboard", icon: <SquaresFour /> },
      { to: "/map", label: "Site Map", icon: <MapTrifold />, permission: "project:read" },
    ],
  },
  {
    title: "Delivery",
    items: [
      { to: "/projects", label: "Projects", icon: <Buildings /> },
      { to: "/workload", label: "Workload", icon: <UsersThree />, permission: "task:write" },
      { to: "/calendar", label: "Calendar", icon: <CalendarBlank /> },
      { to: "/field", label: "Site Capture", icon: <DeviceMobile /> },
    ],
  },
  {
    title: "Commercial",
    items: [
      { to: "/clients", label: "Clients", icon: <AddressBook />, permission: "project:read" },
    ],
  },
  {
    title: "Supply Chain",
    items: [
      { to: "/procurement", label: "Procurement", icon: <ShoppingCart />, permission: "procurement:read" },
      { to: "/procurement/requisitions", label: "Material Requests", icon: <ClipboardText />, permission: "procurement:read" },
      { to: "/inventory", label: "Inventory", icon: <Package />, permission: "inventory:read" },
      { to: "/fleet", label: "Plant & Fleet", icon: <Truck /> },
      { to: "/subcontracts", label: "Subcontracts", icon: <Handshake />, permission: "procurement:read" },
    ],
  },
  {
    title: "Finance",
    items: [
      { to: "/expenses", label: "Expenses", icon: <Receipt />, permission: "expense:read" },
      { to: "/payroll", label: "Payroll", icon: <Money />, permission: "timesheet:write" },
      { to: "/accounting", label: "Accounting", icon: <Bank />, permission: "accounting:read" },
    ],
  },
  {
    title: "Insights",
    items: [
      { to: "/assistant", label: "Assistant", icon: <ClaudeIcon /> },
      { to: "/inbox", label: "AI Inbox", icon: <Tray />, permission: "ingestion:use" },
      { to: "/reports", label: "Reports", icon: <ChartBar /> },
    ],
  },
];

/** Longest matching path wins, so /procurement/requisitions highlights only
 *  Material Requests rather than lighting up Procurement as well. */
function activeNavPath(pathname: string, candidates: string[]): string | null {
  if (pathname === "/") return "/";
  return candidates
    .filter((to) => to !== "/" && (pathname === to || pathname.startsWith(`${to}/`)))
    .sort((a, b) => b.length - a.length)[0] ?? null;
}

/** Work waiting on a destination. Collapsed to icons there is no room for a
 *  number, so it becomes a dot — presence still reads, the count moves to the
 *  tooltip. */
function NavBadge({
  entry,
  collapsed,
}: {
  entry?: { count: number; tone: string };
  collapsed: boolean;
}) {
  if (!entry) return null;
  const tone =
    entry.tone === "danger"
      ? "bg-destructive text-white"
      : entry.tone === "warning"
        ? "bg-warning text-black"
        : "bg-sidebar-accent text-sidebar-foreground";

  if (collapsed) {
    return (
      <span
        className={cn(
          "absolute right-1.5 top-1.5 size-2 rounded-full",
          tone.split(" ")[0],
        )}
      />
    );
  }
  return (
    <span
      className={cn(
        "ml-auto min-w-[1.25rem] shrink-0 rounded-full px-1.5 py-0.5 text-center text-[10px] font-semibold tabular-nums",
        tone,
      )}
    >
      {entry.count > 99 ? "99+" : entry.count}
    </span>
  );
}

/** Whether there is room for the sidebar to sit beside the content.
 *  Matches the `md` breakpoint the layout classes use, so the JS that hides
 *  labels and the CSS that moves the panel never disagree. */
function useIsWide() {
  const [wide, setWide] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(min-width: 768px)").matches,
  );
  useEffect(() => {
    const query = window.matchMedia("(min-width: 768px)");
    const update = () => setWide(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return wide;
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { collapsed, toggle } = useSidebar();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  // On a phone the sidebar is a drawer rather than a column: 224px of a
  // 390px screen is most of the screen. Not persisted — a drawer that is
  // still open when you come back is a drawer in the way.
  const [drawerOpen, setDrawerOpen] = useState(false);
  useEffect(() => setDrawerOpen(false), [pathname]);
  const wide = useIsWide();
  // Collapsing to icons is a desktop affordance. In the drawer there is
  // room for the labels and no reason to hide them.
  const iconsOnly = collapsed && wide;

  // A group vanishes entirely once the role can see none of its pages, so a
  // viewer never meets an empty "Finance" heading.
  const visibleGroups = NAV.map((group) => ({
    ...group,
    items: group.items.filter(
      (item) => !item.permission || can(user?.role, item.permission),
    ),
  })).filter((group) => group.items.length > 0);

  const activePath = activeNavPath(
    pathname,
    visibleGroups.flatMap((group) => group.items.map((item) => item.to ?? "")),
  );

  // Work waiting for this user, refreshed on the same cadence as the bell.
  const { data: navCounts } = useNavCounts({
    query: { refetchInterval: 60_000, refetchIntervalInBackground: false },
  });
  const countByPath = new Map(
    (navCounts?.items ?? []).map((entry) => [entry.path, entry]),
  );

  const countFor = (item: NavItem) =>
    item.to ? countByPath.get(item.to) : undefined;

  const openPalette = usePalette((s) => s.setOpen);
  const paletteDestinations: PaletteDestination[] = visibleGroups.flatMap((group) =>
    group.items
      .filter((item) => item.to)
      .map((item) => ({
        to: item.to as string,
        label: item.label,
        group: group.title ?? "Overview",
      })),
  );

  const handleLogout = async () => {
    await logout();
    await navigate({ to: "/login" });
  };

  return (
    <div className="flex h-screen overflow-hidden">
      {drawerOpen && (
        <button
          type="button"
          aria-label="Close menu"
          className="fixed inset-0 z-40 bg-black/40 md:hidden"
          onClick={() => setDrawerOpen(false)}
        />
      )}
      <aside
        className={cn(
          "flex shrink-0 flex-col bg-sidebar text-sidebar-foreground transition-all",
          // Off-canvas below md, an ordinary column from md up.
          "fixed inset-y-0 left-0 z-50 w-64 md:static md:z-auto md:w-auto md:translate-x-0",
          drawerOpen ? "translate-x-0" : "-translate-x-full",
          collapsed ? "md:w-14" : "md:w-56",
        )}
      >
        <button
          type="button"
          aria-label="Close menu"
          className="absolute right-2 top-3.5 rounded-md p-1.5 text-sidebar-muted hover:bg-sidebar-accent md:hidden"
          onClick={() => setDrawerOpen(false)}
        >
          <X className="size-4" />
        </button>
        <div className="flex h-14 items-center gap-2.5 px-3.5">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <HardHat className="h-4.5 w-4.5" />
          </div>
          {!iconsOnly && (
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">Construction ERP</div>
              <div className="truncate text-[11px] text-sidebar-muted">Demo Construction Co.</div>
            </div>
          )}
        </div>

        <nav className="flex-1 overflow-y-auto px-2 py-2">
          {visibleGroups.map((group, groupIndex) => (
            <div key={group.title ?? "pinned"} className="space-y-0.5">
              {group.title &&
                (iconsOnly ? (
                  // Collapsed to icons only: a rule keeps the grouping legible
                  // where a heading would not fit.
                  <div className="mx-2 my-2 border-t border-sidebar-accent" />
                ) : (
                  <div
                    className={cn(
                      "px-2.5 pb-1 text-[10px] font-semibold uppercase tracking-wider text-sidebar-muted",
                      groupIndex > 0 && "pt-3",
                    )}
                  >
                    {group.title}
                  </div>
                ))}
              {group.items.map((item) =>
                item.soon || !item.to ? (
                  <div
                    key={item.label}
                    className="flex cursor-default items-center gap-3 rounded-md px-2.5 py-2 text-sm text-sidebar-muted [&_svg]:size-4.5 [&_svg]:shrink-0"
                    title={iconsOnly ? item.label : undefined}
                  >
                    {item.icon}
                    {!iconsOnly && (
                      <span className="flex flex-1 items-center justify-between gap-2 truncate">
                        {item.label}
                        <span className="rounded bg-sidebar-accent px-1.5 py-0.5 text-[10px] uppercase tracking-wide">
                          Soon
                        </span>
                      </span>
                    )}
                  </div>
                ) : (
                  <Link
                    key={item.label}
                    to={item.to}
                    title={
                      iconsOnly
                        ? countFor(item)
                          ? `${item.label}: ${countFor(item)?.count} waiting`
                          : item.label
                        : undefined
                    }
                    className={cn(
                      "relative flex items-center gap-3 rounded-md px-2.5 py-2 text-sm transition-colors hover:bg-sidebar-accent [&_svg]:size-4.5 [&_svg]:shrink-0",
                      item.to === activePath && "bg-sidebar-accent font-medium",
                    )}
                  >
                    {item.icon}
                    {!iconsOnly && <span className="flex-1 truncate">{item.label}</span>}
                    <NavBadge entry={countFor(item)} collapsed={iconsOnly} />
                  </Link>
                ),
              )}
            </div>
          ))}
        </nav>

        <div className="space-y-0.5 px-2 pb-2">
          {can(user?.role, "users:manage") && (
            <Link
              to="/admin"
              title={iconsOnly ? "Administration" : "People, invites and the activity log"}
              className={cn(
                "flex items-center gap-3 rounded-md px-2.5 py-2 text-sm transition-colors hover:bg-sidebar-accent [&_svg]:size-4.5 [&_svg]:shrink-0",
                pathname.startsWith("/admin") && "bg-sidebar-accent font-medium",
              )}
            >
              <ShieldCheck />
              {!iconsOnly && <span>Administration</span>}
            </Link>
          )}
          <Link
            to="/settings"
            title={iconsOnly ? "Settings" : "Your profile, appearance and integrations"}
            className={cn(
              "flex items-center gap-3 rounded-md px-2.5 py-2 text-sm transition-colors hover:bg-sidebar-accent [&_svg]:size-4.5 [&_svg]:shrink-0",
              pathname.startsWith("/settings") && "bg-sidebar-accent font-medium",
            )}
          >
            <Gear />
            {!iconsOnly && <span>Settings</span>}
          </Link>
          <button
            onClick={toggle}
            className="flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-sm text-sidebar-muted transition-colors hover:bg-sidebar-accent [&_svg]:size-4.5"
          >
            {iconsOnly ? <CaretDoubleRight /> : <CaretDoubleLeft />}
            {!iconsOnly && <span>Collapse</span>}
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between gap-2 border-b bg-card px-3 sm:px-5">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Open menu"
            className="md:hidden"
            onClick={() => setDrawerOpen(true)}
          >
            <List />
          </Button>
          <div className="hidden text-sm text-muted-foreground md:block" />
          <div className="flex items-center gap-2 sm:gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => openPalette(true)}
              title="Search everything (Ctrl+K)"
              className="gap-2 text-muted-foreground"
            >
              <MagnifyingGlass />
              <span className="hidden sm:inline">Search</span>
              <kbd className="hidden rounded border px-1 text-[10px] sm:inline">Ctrl K</kbd>
            </Button>
            <Link
              to="/assistant"
              title="Ask the assistant"
              className={cn(
                "inline-flex h-8 items-center gap-2 rounded-md border border-input px-3 text-sm font-medium transition-colors hover:bg-accent",
                pathname.startsWith("/assistant") && "bg-secondary",
              )}
            >
              <ClaudeIcon className="size-4 text-claude" />
              <span className="hidden sm:inline">Assistant</span>
            </Link>
            <SyncIndicator />
            <NotificationBell />
            {user && (
              <div className="hidden text-right lg:block">
                <div className="text-sm font-medium leading-tight">{user.full_name}</div>
                <div className="text-xs text-muted-foreground">{ROLE_LABELS[user.role]}</div>
              </div>
            )}
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">
              {user?.full_name
                ?.split(" ")
                .map((p) => p[0])
                .slice(0, 2)
                .join("")}
            </div>
            <Button variant="ghost" size="icon" onClick={handleLogout} title="Sign out">
              <SignOut />
            </Button>
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto p-3 sm:p-5">{children}</main>
      </div>
      <CommandPalette destinations={paletteDestinations} />
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
