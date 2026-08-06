import { Outlet, createFileRoute, redirect } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { useEffect } from "react";
import { setLivePermissions } from "@/features/auth/permissions";
import { useAuthStore } from "@/features/auth/store";
import { useMyPermissions } from "@/lib/api/generated/endpoints";

export const Route = createFileRoute("/_app")({
  beforeLoad: ({ location }) => {
    if (!useAuthStore.getState().user) {
      throw redirect({ to: "/login", search: { redirect: location.href } });
    }
  },
  component: AppLayout,
});


/** Loads the permissions this session actually has, once, before the shell
 *  decides what to show. The compiled table is only a fallback for that first
 *  moment — the matrix is editable, so gating on a bundled copy would show
 *  whatever it was on the day of the last deploy. */
function AppLayout() {
  const { data } = useMyPermissions({ query: { staleTime: 5 * 60_000 } });

  useEffect(() => {
    setLivePermissions(data ?? null);
  }, [data]);

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}
