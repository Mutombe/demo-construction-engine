import { useAuthStore } from "./store";
import { can, type Permission } from "./permissions";

export function useAuth() {
  const user = useAuthStore((s) => s.user);
  const initialized = useAuthStore((s) => s.initialized);
  return { user, initialized, isAuthenticated: user !== null };
}

export function usePermission(permission: Permission): boolean {
  const user = useAuthStore((s) => s.user);
  return can(user?.role, permission);
}
