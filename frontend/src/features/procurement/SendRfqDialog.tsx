import { useQueryClient } from "@tanstack/react-query";
import { Copy, PaperPlaneTilt, Prohibit } from "@phosphor-icons/react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { confirmDialog } from "@/components/ui/confirm";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errDetail } from "@/lib/api/errors";
import {
  useListRfqInvites,
  useListSuppliers,
  useRevokeRfqInvite,
  useSendRfq,
} from "@/lib/api/generated/endpoints";
import { fmtDate } from "@/lib/format";
import { toast } from "@/lib/toast";
import { ReputationTag, useReputations } from "@/features/procurement/ReputationTag";

const STATUS_TONE: Record<string, "secondary" | "warning" | "success" | "outline"> = {
  sent: "secondary",
  opened: "warning",
  responded: "success",
  revoked: "outline",
  expired: "outline",
};

export function SendRfqDialog({
  rfqId,
  open,
  onOpenChange,
}: {
  rfqId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const reputations = useReputations();
  const queryClient = useQueryClient();
  const { data: suppliers } = useListSuppliers({ page: 1, page_size: 200 });
  const { data: invites } = useListRfqInvites(rfqId, { query: { enabled: open } });
  const send = useSendRfq();
  const revoke = useRevokeRfqInvite();

  const [selected, setSelected] = useState<string[]>([]);
  const [days, setDays] = useState("21");
  const [issued, setIssued] = useState<{ supplier_name?: string | null; url: string }[]>([]);

  const refresh = () => queryClient.invalidateQueries();

  const alreadyInvited = new Set((invites ?? []).map((invite) => invite.supplier_id));

  const submit = async () => {
    try {
      const result = await send.mutateAsync({
        rfqId,
        data: { supplier_ids: selected, expires_in_days: Number(days) || 21 },
      });
      setIssued(result);
      setSelected([]);
      await refresh();
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const withdraw = async (invite: { id: string; supplier_name?: string | null }) => {
    if (
      !(await confirmDialog({
        title: "Withdraw link",
        message: `${invite.supplier_name} will no longer be able to open this request or send a price.`,
        confirmLabel: "Withdraw",
        tone: "danger",
      }))
    )
      return;
    try {
      await revoke.mutateAsync({ inviteId: invite.id });
      await refresh();
      toast.success("Link withdrawn");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Send to Suppliers</DialogTitle>
        </DialogHeader>

        {issued.length > 0 ? (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              Send each supplier their own link. They are shown once and cannot be recovered,
              because only a hash of each is stored.
            </p>
            {issued.map((row) => (
              <div key={row.url} className="space-y-1">
                <Label>{row.supplier_name}</Label>
                <div className="flex gap-2">
                  <Input readOnly value={row.url} className="font-mono text-xs" />
                  <Button
                    variant="outline"
                    title="Copy this link"
                    onClick={() => {
                      void navigator.clipboard.writeText(row.url);
                      toast.success("Link copied");
                    }}
                  >
                    <Copy />
                  </Button>
                </div>
              </div>
            ))}
            <DialogFooter>
              <Button
                onClick={() => {
                  setIssued([]);
                  onOpenChange(false);
                }}
              >
                Done
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="space-y-4">
            {invites && invites.length > 0 && (
              <div className="space-y-1.5">
                <Label>Already sent</Label>
                <div className="space-y-1">
                  {invites.map((invite) => (
                    <div
                      key={invite.id}
                      className="flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-sm"
                    >
                      <span className="flex-1 truncate">{invite.supplier_name}</span>
                      <Badge variant={STATUS_TONE[invite.status ?? "sent"] ?? "secondary"}>
                        {invite.status}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        expires {fmtDate(invite.expires_at)}
                      </span>
                      {invite.status !== "responded" && invite.status !== "revoked" && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive"
                          title="Withdraw this link"
                          onClick={() => void withdraw(invite)}
                        >
                          <Prohibit />
                        </Button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="space-y-1.5">
              <Label>Suppliers</Label>
              <div className="max-h-56 space-y-0.5 overflow-y-auto rounded-md border p-1.5">
                {suppliers?.items.map((supplier) => {
                  const invited = alreadyInvited.has(supplier.id);
                  return (
                    <label
                      key={supplier.id}
                      className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-accent"
                    >
                      <input
                        type="checkbox"
                        checked={selected.includes(supplier.id)}
                        onChange={(e) =>
                          setSelected((prev) =>
                            e.target.checked
                              ? [...prev, supplier.id]
                              : prev.filter((id) => id !== supplier.id),
                          )
                        }
                      />
                      <span className="flex-1 truncate">{supplier.name}</span>
                      <ReputationTag
                        reputation={reputations.get(supplier.id)}
                        showDetail={false}
                      />
                      {invited && (
                        <span className="text-xs text-muted-foreground">already sent</span>
                      )}
                    </label>
                  );
                })}
              </div>
            </div>

            <div className="w-40 space-y-1.5">
              <Label htmlFor="expiry">Link valid for</Label>
              <Input
                id="expiry"
                type="number"
                min={1}
                max={120}
                value={days}
                onChange={(e) => setDays(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">days</p>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button disabled={selected.length === 0 || send.isPending} onClick={() => void submit()}>
                <PaperPlaneTilt />
                {send.isPending ? "Sending…" : `Send to ${selected.length || ""}`.trim()}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
