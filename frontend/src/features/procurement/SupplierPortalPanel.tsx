import { useQueryClient } from "@tanstack/react-query";
import { Copy, LinkSimple, Trash } from "@phosphor-icons/react";
import { useState } from "react";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { confirmDialog } from "@/components/ui/confirm";
import { errDetail } from "@/lib/api/errors";
import { useIssueLink, useListLinks, useRevokeLink } from "@/lib/api/generated/endpoints";
import { fmtDate } from "@/lib/format";
import { toast } from "@/lib/toast";

/** Issuing and withdrawing a supplier's own door into the system.
 *
 *  The URL is shown once and never again, because only its hash is stored.
 *  That is the point — a leaked database hands nobody a working link — but it
 *  does mean the copy button here is the only chance to take it. */
export function SupplierPortalPanel({ supplierId }: { supplierId: string }) {
  const queryClient = useQueryClient();
  const { data: links } = useListLinks(supplierId);
  const issue = useIssueLink();
  const revoke = useRevokeLink();
  const [fresh, setFresh] = useState<string | null>(null);

  const rows = links ?? [];
  const live = rows.filter((row) => !row.revoked_at);

  const create = async () => {
    try {
      const result = await issue.mutateAsync({ supplierId, data: { days: 365 } });
      await queryClient.invalidateQueries();
      setFresh(result.url);
      toast.success("Link created");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const withdraw = async (tokenId: string) => {
    const ok = await confirmDialog({
      title: "Withdraw this link?",
      message: "It stops working immediately and cannot be reinstated.",
      confirmLabel: "Withdraw",
      tone: "danger",
    });
    if (!ok) return;
    try {
      await revoke.mutateAsync({ tokenId });
      await queryClient.invalidateQueries();
      toast.success("Link withdrawn");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <LinkSimple /> Supplier portal
          </CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Lets them see their own orders and send invoices without ringing anybody.
          </p>
        </div>
        <Can perm="procurement:write">
          <Button variant="outline" size="sm" disabled={issue.isPending} onClick={() => void create()}>
            New Link
          </Button>
        </Can>
      </CardHeader>
      <CardContent className="space-y-3">
        {fresh && (
          <div className="space-y-1.5 rounded-md border border-success/30 bg-success/5 p-3">
            <p className="text-xs font-medium text-success">
              Copy this now — it is not stored and cannot be shown again.
            </p>
            <div className="flex gap-2">
              <code className="flex-1 truncate rounded bg-background px-2 py-1 text-xs">
                {fresh}
              </code>
              <Button
                variant="outline"
                size="icon"
                aria-label="Copy link"
                onClick={() => {
                  void navigator.clipboard.writeText(fresh);
                  toast.success("Copied");
                }}
              >
                <Copy />
              </Button>
            </div>
          </div>
        )}

        {rows.length ? (
          <div className="space-y-2">
            {rows.map((row) => (
              <div key={row.id} className="flex items-center gap-2 text-sm">
                <Badge variant={row.revoked_at ? "outline" : "success"}>
                  {row.revoked_at ? "Withdrawn" : "Live"}
                </Badge>
                <span className="flex-1 truncate">{row.label}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {row.last_used_at
                    ? `used ${fmtDate(row.last_used_at.slice(0, 10))}`
                    : "never used"}
                </span>
                {!row.revoked_at && (
                  <Can perm="procurement:write">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Withdraw link"
                      onClick={() => void withdraw(row.id)}
                    >
                      <Trash />
                    </Button>
                  </Can>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No link issued. They have to ring or email for everything.
          </p>
        )}

        {live.length > 1 && (
          <p className="text-xs text-muted-foreground">
            More than one link is live. Each works independently, so withdraw the ones that are
            no longer needed.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
