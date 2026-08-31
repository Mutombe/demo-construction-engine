import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createRouter } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ConfirmHost } from "@/components/ui/confirm";
import { restoreSession } from "@/features/auth/api";
import { initTheme } from "@/features/settings/theme";
import { startSyncLoop } from "@/lib/offline/sync";
import { Toaster } from "@/lib/toast";
import { routeTree } from "./routeTree.gen";
import "./index.css";

// Before React renders, so there is no flash of the wrong theme
initTheme();

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

// Drains whatever was captured with no signal, whenever there is signal.
startSyncLoop();

// Keeps the app loadable offline so the site forms can be reached at all.
// Dev is left alone: a service worker and HMR fight over the same requests.
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  });
}
