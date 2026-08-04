import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { AddressBook, Buildings, CaretDoubleLeft, CaretDoubleRight, ChartBar, ClipboardText, Gear, HardHat, MapTrifold, Money, Package, Receipt, ShoppingCart, SignOut, SquaresFour, Tray } from "@phosphor-icons/react";
import { ClaudeIcon } from "@/components/ui/claude-icon";
import type { ReactNode } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { Button } from "@/components/ui/button";
import { ChatPanel } from "@/features/ai/ChatPanel";
import { useChatStore } from "@/features/ai/chatStore";
import { logout } from "@/features/auth/api";
import { useAuth } from "@/features/auth/hooks";
import { NotificationBell } from "@/features/notifications/NotificationBell";
import { can, type Permission } from "@/features/auth/permissions";
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

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: <SquaresFour /> },
  { to: "/projects", label: "Projects", icon: <Buildings /> },
  { to: "/map", label: "Site Map", icon: <MapTrifold />, permission: "project:read" },
  { to: "/clients", label: "Clients", icon: <AddressBook />, permission: "project:read" },
  { to: "/procurement", label: "Procurement", icon: <ShoppingCart />, permission: "procurement:read" },
  { to: "/procurement/requisitions", label: "Material Requests", icon: <ClipboardText />, permission: "procurement:read" },
  { to: "/expenses", label: "Expenses", icon: <Receipt />, permission: "expense:read" },
  { to: "/inventory", label: "Inventory", icon: <Package />, permission: "inventory:read" },
  { to: "/payroll", label: "Payroll", icon: <Money />, permission: "timesheet:write" },
  { to: "/inbox", label: "AI Inbox", icon: <Tray />, permission: "ingestion:use" },
  { to: "/reports", label: "Reports", icon: <ChartBar /> },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { collapsed, toggle } = useSidebar();
  const toggleChat = useChatStore((s) => s.toggle);
  const chatOpen = useChatStore((s) => s.open);
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  const handleLogout = async () => {
    await logout();
    await navigate({ to: "/login" });
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <aside
        className={cn(
          "flex shrink-0 flex-col bg-sidebar text-sidebar-foreground transition-all",
          collapsed ? "w-14" : "w-56",
        )}
      >
        <div className="flex h-14 items-center gap-2.5 px-3.5">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <HardHat className="h-4.5 w-4.5" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">Construction ERP</div>
              <div className="truncate text-[11px] text-sidebar-muted">Demo Construction Co.</div>
            </div>
          )}
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-2">
          {NAV.filter((item) => !item.permission || can(user?.role, item.permission)).map(
            (item) =>
              item.soon || !item.to ? (
                <div
                  key={item.label}
                  className="flex cursor-default items-center gap-3 rounded-md px-2.5 py-2 text-sm text-sidebar-muted [&_svg]:size-4.5 [&_svg]:shrink-0"
                  title={collapsed ? item.label : undefined}
                >
                  {item.icon}
                  {!collapsed && (
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
                  title={collapsed ? item.label : undefined}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-2.5 py-2 text-sm transition-colors hover:bg-sidebar-accent [&_svg]:size-4.5 [&_svg]:shrink-0",
                    (item.to === "/" ? pathname === "/" : pathname.startsWith(item.to)) &&
                      "bg-sidebar-accent font-medium",
                  )}
                >
                  {item.icon}
                  {!collapsed && <span className="truncate">{item.label}</span>}
                </Link>
              ),
          )}
        </nav>

        <div className="space-y-0.5 px-2 pb-2">
          {can(user?.role, "users:manage") && (
            <Link
              to="/settings/users"
              title={collapsed ? "Settings" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-md px-2.5 py-2 text-sm transition-colors hover:bg-sidebar-accent [&_svg]:size-4.5 [&_svg]:shrink-0",
                pathname.startsWith("/settings") && "bg-sidebar-accent font-medium",
              )}
            >
              <Gear />
              {!collapsed && <span>Settings</span>}
            </Link>
          )}
          <button
            onClick={toggle}
            className="flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-sm text-sidebar-muted transition-colors hover:bg-sidebar-accent [&_svg]:size-4.5"
          >
            {collapsed ? <CaretDoubleRight /> : <CaretDoubleLeft />}
            {!collapsed && <span>Collapse</span>}
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b bg-card px-5">
          <div className="text-sm text-muted-foreground" />
          <div className="flex items-center gap-3">
            <Button
              variant={chatOpen ? "secondary" : "outline"}
              size="sm"
              onClick={toggleChat}
              title="AI assistant"
            >
              <ClaudeIcon className="text-claude" /> Assistant
            </Button>
            <NotificationBell />
            {user && (
              <div className="text-right">
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
        <main className="min-h-0 flex-1 overflow-y-auto p-5">{children}</main>
      </div>
      <ChatPanel />
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
