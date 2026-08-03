import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createRouter } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ConfirmHost } from "@/components/ui/confirm";
import { restoreSession } from "@/features/auth/api";
import { Toaster } from "@/lib/toast";
import { routeTree } from "./routeTree.gen";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false },
  },
});

const router = createRouter({
  routeTree,
  context: { queryClient },
  defaultPreload: "intent",
  // Hovering a link preloads its route (and its loader's data) — don't redo it
  // more than once per 30s window.
  defaultPreloadStaleTime: 30_000,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

async function boot() {
  await restoreSession(); // silent refresh before first render so guards see the session
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
        <Toaster />
        <ConfirmHost />
      </QueryClientProvider>
    </StrictMode>,
  );
}

void boot();
