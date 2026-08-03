import type { ReactNode } from "react";
import { usePermission } from "@/features/auth/hooks";
import type { Permission } from "@/features/auth/permissions";

export function Can({ perm, children }: { perm: Permission; children: ReactNode }) {
  const allowed = usePermission(perm);
  if (!allowed) return null;
  return <>{children}</>;
}
