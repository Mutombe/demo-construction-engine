import { create } from "zustand";

export type Role =
  | "admin"
  | "project_manager"
  | "site_manager"
  | "procurement_officer"
  | "viewer";

export interface SessionUser {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
}

interface AuthState {
  accessToken: string | null;
  user: SessionUser | null;
  /** true once the boot-time silent refresh has settled (success or failure) */
  initialized: boolean;
  setSession: (token: string, user: SessionUser) => void;
  clearSession: () => void;
  setInitialized: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  initialized: false,
  setSession: (accessToken, user) => set({ accessToken, user }),
  clearSession: () => set({ accessToken: null, user: null }),
  setInitialized: () => set({ initialized: true }),
}));
