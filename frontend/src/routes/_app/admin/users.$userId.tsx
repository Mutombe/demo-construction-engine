import { createFileRoute } from "@tanstack/react-router";
import { ShieldCheck, User as UserIcon } from "@phosphor-icons/react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/list-state";
import { PageSkeleton } from "@/components/ui/skeleton";
import { useGetUser, useGetUserPermissions } from "@/lib/api/generated/endpoints";
import { ROLE_LABELS, fmtDate } from "@/lib/format";

export const Route = createFileRoute("/_app/admin/users/$userId")({
  component: UserDetail,
});

/** One person, and exactly what they can do.
 *
 *  The list can show a role, but a role is a shorthand: what somebody can
 *  actually reach is their role's permissions plus whatever has been granted
 *  or taken away from them personally. Answering "why can they see that" from
 *  a role name alone is guesswork, so both are set out here. */
function UserDetail() {
  const { userId } = Route.useParams();
  const userQuery = useGetUser(userId);
  const permsQuery = useGetUserPermissions(userId);

  const user = userQuery.data;
  if (userQuery.isError) {
    return <ErrorState error={userQuery.error} onRetry={() => void userQuery.refetch()} />;
  }
  if (!user) return <PageSkeleton rows={3} />;

  const perms = permsQuery.data as
    | { effective?: string[]; overrides?: Record<string, boolean> }
    | undefined;
  const effective = perms?.effective ?? [];
  const overrides = perms?.overrides ?? {};
  const overrideKeys = Object.keys(overrides);

  // Grouped by the thing they act on, since that is how somebody asks the
  // question: "what can they do with purchase orders?"
  const grouped = effective.reduce<Record<string, string[]>>((acc, permission) => {
    const [area, action] = permission.split(":");
    const key = area || permission;
    (acc[key] ??= []).push(action ?? permission);
    return acc;
  }, {});

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Administration", to: "/admin", search: { tab: "users" } },
          { label: user.full_name },
        ]}
      />

      <div className="mb-5">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold tracking-tight">{user.full_name}</h1>
          <Badge variant="secondary">{ROLE_LABELS[user.role] ?? user.role}</Badge>
          {user.is_active ? (
            <Badge variant="success">Active</Badge>
          ) : (
            <Badge variant="outline">Suspended</Badge>
          )}
        </div>
        <p className="mt-1 text-sm text-muted-foreground">{user.email}</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <ShieldCheck /> What they can reach
              </CardTitle>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Their role's permissions, plus anything granted or withdrawn from them
                personally.
              </p>
            </CardHeader>
            <CardContent>
              {effective.length ? (
                <div className="space-y-3">
                  {Object.entries(grouped)
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([area, actions]) => (
                      <div key={area} className="flex flex-wrap items-baseline gap-2">
                        <span className="w-32 shrink-0 text-sm capitalize text-muted-foreground">
                          {area.replace(/_/g, " ")}
                        </span>
                        <div className="flex flex-wrap gap-1">
                          {actions.sort().map((action) => (
                            <Badge
                              key={action}
                              variant={
                                overrides[`${area}:${action}`] === true
                                  ? "success"
                                  : "outline"
                              }
                            >
                              {action}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Nothing. This account can sign in and see nothing else.
                </p>
              )}
            </CardContent>
          </Card>

          {overrideKeys.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Set for them personally</CardTitle>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  These differ from what the role alone would give, which is usually the
                  answer to why somebody can or cannot see something.
                </p>
              </CardHeader>
              <CardContent className="space-y-1.5 text-sm">
                {overrideKeys.sort().map((permission) => (
                  <div key={permission} className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs">{permission}</span>
                    <Badge variant={overrides[permission] ? "success" : "destructive"}>
                      {overrides[permission] ? "Granted" : "Withdrawn"}
                    </Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <UserIcon /> Account
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row label="Role" value={ROLE_LABELS[user.role] ?? user.role} />
              <Row label="Status" value={user.is_active ? "Active" : "Suspended"} />
              <Row
                label="Last signed in"
                value={
                  user.last_login_at
                    ? fmtDate(user.last_login_at.slice(0, 10))
                    : "Never signed in"
                }
              />
              <Row label="Permissions" value={String(effective.length)} />
            </CardContent>
          </Card>

          {permsQuery.isError && (
            <Card>
              <CardContent className="py-4 text-xs text-muted-foreground">
                Their permissions could not be loaded. Only an administrator can read
                them, so this is expected unless you are one.
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className="truncate text-right font-medium">{value}</span>
    </div>
  );
}
