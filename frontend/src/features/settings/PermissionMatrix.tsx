import { useQueryClient } from "@tanstack/react-query";
import { Check, Lock, X } from "@phosphor-icons/react";
import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { errDetail } from "@/lib/api/errors";
import {
  useGetCatalogue,
  useGetMatrix,
  useUpdateMatrix,
} from "@/lib/api/generated/endpoints";
import { ROLE_LABELS } from "@/lib/format";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

/** The matrix the app actually enforces, editable in place.
 *
 *  Administrators are shown locked rather than hidden: the rule is that they
 *  always keep everything, and a row that silently vanished would look like a
 *  bug rather than a deliberate floor.
 */
export function PermissionMatrix() {
  const queryClient = useQueryClient();
  const { data: catalogue } = useGetCatalogue();
  const { data: matrix } = useGetMatrix();
  const update = useUpdateMatrix();

  if (!catalogue || !matrix) {
    return <div className="h-72 animate-pulse rounded-lg border bg-muted/40" />;
  }

  const roles = catalogue.roles as string[];

  const toggle = async (role: string, permission: string, next: boolean) => {
    try {
      await update.mutateAsync({ data: { role: role as never, permission, allowed: next } });
      await queryClient.invalidateQueries();
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="border-b bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-4 py-2 text-left font-medium">Can do</th>
            {roles.map((role) => (
              <th key={role} className="px-3 py-2 text-center font-medium">
                {ROLE_LABELS[role] ?? role}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(catalogue.modules as ModuleRow[]).map((module) => (
            <>
              <tr key={module.key} className="border-b bg-muted/20">
                <td
                  colSpan={roles.length + 1}
                  className="px-4 py-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                >
                  {module.label}
                </td>
              </tr>
              {module.actions.map((action) => (
                <tr key={action.permission} className="border-b last:border-0">
                  <td className="px-4 py-1.5">{action.label}</td>
                  {roles.map((role) => {
                    const locked = role === "admin";
                    const on = locked || (matrix[role] ?? []).includes(action.permission);
                    return (
                      <td key={role} className="px-3 py-1.5 text-center">
                        {locked ? (
                          <Tooltip content="Administrators always keep every permission">
                            <span className="inline-flex text-muted-foreground">
                              <Lock className="size-3.5" />
                            </span>
                          </Tooltip>
                        ) : (
                          <button
                            type="button"
                            aria-pressed={on}
                            aria-label={`${action.label} for ${role}`}
                            disabled={update.isPending}
                            onClick={() => void toggle(role, action.permission, !on)}
                            className={cn(
                              "inline-flex size-5 items-center justify-center rounded transition-colors",
                              on
                                ? "bg-success/15 text-success hover:bg-success/25"
                                : "bg-muted text-muted-foreground/50 hover:bg-muted/80",
                            )}
                          >
                            {on ? <Check className="size-3.5" /> : <X className="size-3" />}
                          </button>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </>
          ))}
        </tbody>
      </table>
      <p className="border-t px-4 py-2 text-xs text-muted-foreground">
        Changes apply the next time someone loads a page. Individual exceptions live on the
        person, under Administration.
      </p>
    </div>
  );
}

interface ModuleRow {
  key: string;
  label: string;
  actions: { key: string; label: string; permission: string }[];
}

/** Shown on a user so an exception reads as an exception rather than as a
 *  second, competing role. */
export function UserOverrides({
  effective,
  overrides,
}: {
  effective: string[];
  overrides: Record<string, boolean>;
}) {
  const entries = Object.entries(overrides);
  if (entries.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        No exceptions: this person has exactly what their role allows.
      </p>
    );
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.map(([permission, allowed]) => (
        <Badge key={permission} variant={allowed ? "success" : "destructive"}>
          {allowed ? "+" : "−"} {permission}
        </Badge>
      ))}
      <span className="text-xs text-muted-foreground">
        {effective.length} permissions in total
      </span>
    </div>
  );
}
