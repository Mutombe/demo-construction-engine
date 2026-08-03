import type { QueryClient } from "@tanstack/react-query";
import { Outlet, createRootRouteWithContext, Link } from "@tanstack/react-router";

interface RouterContext {
  queryClient: QueryClient;
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: () => <Outlet />,
  notFoundComponent: () => (
    <div className="flex h-screen flex-col items-center justify-center gap-3">
      <div className="text-5xl font-bold text-muted-foreground">404</div>
      <p className="text-muted-foreground">This page does not exist.</p>
      <Link to="/" className="text-primary underline underline-offset-4">
        Back to dashboard
      </Link>
    </div>
  ),
});
