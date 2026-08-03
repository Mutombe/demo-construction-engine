import { useQueryClient } from "@tanstack/react-query";
import { Copy, Globe, LinkSimple, ShieldSlash } from "@phosphor-icons/react";
import { useState } from "react";
import { toast } from "@/lib/toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { confirmDialog } from "@/components/ui/confirm";
import { Input } from "@/components/ui/input";
import {
  useCreatePortalLink,
  useListPortalLinks,
  useRevokePortalLink,
} from "@/lib/api/generated/endpoints";
import { fmtDate } from "@/lib/format";

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

/** PM tool: generate/revoke read-only portal links for the project's client. */
export function PortalAccessCard({
  clientId,
  clientName,
}: {
  clientId: string;
  clientName: string | null | undefined;
}) {
  const queryClient = useQueryClient();
  const { data: links } = useListPortalLinks(clientId);
  const createMutation = useCreatePortalLink();
  const revokeMutation = useRevokePortalLink();
  const [label, setLabel] = useState("");
  const [freshUrl, setFreshUrl] = useState<string | null>(null);

  const generate = async () => {
    try {
      const created = await createMutation.mutateAsync({
        clientId,
        data: { label: label.trim() || `Link for ${clientName ?? "client"}` },
      });
      setFreshUrl(created.url);
      setLabel("");
      await queryClient.invalidateQueries();
      await navigator.clipboard.writeText(created.url).then(
        () => toast.success("Portal link created — copied to clipboard"),
        () => toast.success("Portal link created"),
      );
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const revoke = async (linkId: string) => {
    if (
      !(await confirmDialog({
        title: "Revoke link",
        message: "Revoke this link? Anyone using it loses access immediately.",
        tone: "danger",
      }))
    )
      return;
    try {
      await revokeMutation.mutateAsync({ linkId });
      await queryClient.invalidateQueries();
      toast.success("Link revoked");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const active = (links ?? []).filter((l) => !l.revoked_at);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2 text-base">
          <Globe className="h-4 w-4 text-primary" /> Client Portal Access
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Share a read-only link with {clientName ?? "the client"}: live progress, phases and
          issued payment certificates. The full link is shown once — treat it like a key.
        </p>

        {freshUrl && (
          <div className="space-y-1 rounded-md border border-primary/40 bg-primary/5 p-2.5">
            <div className="text-xs font-medium text-primary">
              New link — copy it now, it won't be shown again
            </div>
            <div className="flex items-center gap-1.5">
              <Input readOnly value={freshUrl} className="h-8 font-mono text-xs" />
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8 shrink-0"
                title="Copy"
                onClick={() =>
                  void navigator.clipboard
                    .writeText(freshUrl)
                    .then(() => toast.success("Copied"))
                }
              >
                <Copy />
              </Button>
            </div>
          </div>
        )}

        {active.length > 0 && (
          <ul className="space-y-1.5">
            {active.map((link) => (
              <li key={link.id} className="flex items-center gap-2 text-sm">
                <LinkSimple className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate">{link.label}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {link.last_used_at
                    ? `used ${fmtDate(link.last_used_at.slice(0, 10))}`
                    : "never used"}{" "}
                  · expires {fmtDate(link.expires_at.slice(0, 10))}
                </span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0 text-destructive"
                  title="Revoke"
                  disabled={revokeMutation.isPending}
                  onClick={() => void revoke(link.id)}
                >
                  <ShieldSlash />
                </Button>
              </li>
            ))}
          </ul>
        )}

        <div className="flex gap-2">
          <Input
            placeholder="Label (e.g. Sent to J. Banda)"
            className="h-8"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
          <Button
            size="sm"
            disabled={createMutation.isPending}
            onClick={() => void generate()}
          >
            {createMutation.isPending ? "Creating…" : "Generate Link"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
