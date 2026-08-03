import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Bell, Checks, Tray } from "@phosphor-icons/react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dropdown } from "@/components/ui/dropdown";
import { EmptyState } from "@/components/ui/empty-state";
import {
  useGetUnreadCount,
  useListNotifications,
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
} from "@/lib/api/generated/endpoints";
import type { NotificationRead } from "@/lib/api/generated/model";
import { optimistic } from "@/lib/api/optimistic";
import { cn } from "@/lib/utils";

function timeAgo(iso: string): string {
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: unread } = useGetUnreadCount({
    query: { refetchInterval: 60_000, refetchIntervalInBackground: false },
  });
  const { data: list } = useListNotifications(
    { page_size: 15 },
    { query: { enabled: open, refetchOnMount: "always" } },
  );
  // Reads apply instantly: the badge decrements and the row un-bolds the moment
  // you click, reconciling with the server in the background.
  const markRead = useMarkNotificationRead({
    mutation: optimistic(queryClient, {
      prefixes: ["/api/v1/notifications"],
      errorToast: false,
      apply: (old, vars: { notificationId: string }) => {
        if (old && typeof old.count === "number") {
          return { ...old, count: Math.max(0, old.count - 1) };
        }
        if (old && Array.isArray(old.items)) {
          return {
            ...old,
            items: old.items.map((n: NotificationRead) =>
              n.id === vars.notificationId ? { ...n, is_read: true } : n,
            ),
          };
        }
        return old;
      },
    }),
  });
  const markAll = useMarkAllNotificationsRead({
    mutation: optimistic(queryClient, {
      prefixes: ["/api/v1/notifications"],
      errorToast: false,
      apply: (old) => {
        if (old && typeof old.count === "number") return { ...old, count: 0 };
        if (old && Array.isArray(old.items)) {
          return {
            ...old,
            items: old.items.map((n: NotificationRead) => ({ ...n, is_read: true })),
          };
        }
        return old;
      },
    }),
  });

  const count = unread?.count ?? 0;

  const openItem = async (item: NotificationRead) => {
    setOpen(false);
    if (!item.is_read) {
      markRead.mutateAsync({ notificationId: item.id }).catch(() => undefined);
    }
    if (item.link_path) {
      await navigate({ to: item.link_path });
    }
  };

  return (
    <Dropdown
      open={open}
      onClose={() => setOpen(false)}
      className="w-96 max-w-[90vw]"
      trigger={
        <Button
          variant="ghost"
          size="icon"
          className="relative"
          title="Notifications"
          aria-label={`Notifications${count ? ` (${count} unread)` : ""}`}
          onClick={() => setOpen((v) => !v)}
        >
          <Bell />
          {count > 0 && (
            <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold text-destructive-foreground">
              {count > 9 ? "9+" : count}
            </span>
          )}
        </Button>
      }
    >
      <div className="flex items-center justify-between border-b px-3.5 py-2.5">
        <span className="text-sm font-semibold">Notifications</span>
        {count > 0 && (
          <button
            type="button"
            className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
            onClick={() => void markAll.mutateAsync().catch(() => undefined)}
          >
            <Checks className="h-3.5 w-3.5" /> Mark all read
          </button>
        )}
      </div>
      <div className="max-h-96 overflow-y-auto">
        {(list?.items.length ?? 0) === 0 ? (
          <EmptyState
            icon={<Tray />}
            title="You're all caught up"
            hint="Approvals, certificates and pay runs that need your attention will land here."
            className="py-8"
          />
        ) : (
          <ul className="divide-y">
            {list?.items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => void openItem(item)}
                  className={cn(
                    "flex w-full items-start gap-2.5 px-3.5 py-2.5 text-left transition-colors hover:bg-muted/60",
                    !item.is_read && "bg-primary/[0.04]",
                  )}
                >
                  <span
                    className={cn(
                      "mt-1.5 h-2 w-2 shrink-0 rounded-full",
                      item.is_read ? "bg-transparent" : "bg-primary",
                    )}
                  />
                  <span className="min-w-0 flex-1">
                    <span
                      className={cn(
                        "block truncate text-sm",
                        item.is_read ? "text-muted-foreground" : "font-medium",
                      )}
                    >
                      {item.title}
                    </span>
                    {item.body && (
                      <span className="block truncate text-xs text-muted-foreground">
                        {item.body}
                      </span>
                    )}
                  </span>
                  <span className="shrink-0 pt-0.5 text-[11px] text-muted-foreground">
                    {timeAgo(item.created_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Dropdown>
  );
}
