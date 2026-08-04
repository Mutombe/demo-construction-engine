import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ThemePreference = "light" | "dark" | "system";

/** Applies the resolved theme to <html>, which is what the CSS keys off.
 *  Kept outside React so the very first paint is already correct. */
function apply(preference: ThemePreference) {
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const dark = preference === "dark" || (preference === "system" && prefersDark);
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
}

interface ThemeState {
  preference: ThemePreference;
  setPreference: (preference: ThemePreference) => void;
}

export const useTheme = create<ThemeState>()(
  persist(
    (set) => ({
      preference: "system",
      setPreference: (preference) => {
        apply(preference);
        set({ preference });
      },
    }),
    {
      name: "erp-theme",
      onRehydrateStorage: () => (state) => apply(state?.preference ?? "system"),
    },
  ),
);

/** Call once at startup, before React renders, so there is no flash of the
 *  wrong theme. Also keeps "system" honest by following the OS if it changes
 *  while the app is open. */
export function initTheme() {
  const stored = localStorage.getItem("erp-theme");
  let preference: ThemePreference = "system";
  try {
    preference = JSON.parse(stored ?? "{}")?.state?.preference ?? "system";
  } catch {
    preference = "system";
  }
  apply(preference);

  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => {
      if (useTheme.getState().preference === "system") apply("system");
    });
}
