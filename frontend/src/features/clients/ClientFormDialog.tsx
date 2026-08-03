import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { errDetail } from "@/lib/api/errors";
import { useCreateClient, useUpdateClient } from "@/lib/api/generated/endpoints";
import type { ClientRead } from "@/lib/api/generated/model";

export function ClientFormDialog({
  open,
  onOpenChange,
  client,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  client?: ClientRead | null;
}) {
  const queryClient = useQueryClient();
  const createMutation = useCreateClient();
  const updateMutation = useUpdateClient();

  const [name, setName] = useState("");
  const [contact, setContact] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");

  useEffect(() => {
    if (open) {
      setName(client?.name ?? "");
      setContact(client?.contact_person ?? "");
      setEmail(client?.email ?? "");
      setPhone(client?.phone ?? "");
      setAddress(client?.address ?? "");
    }
  }, [open, client]);

  const save = async () => {
    if (!name.trim()) {
      toast.error("Client name is required");
      return;
    }
    const payload = {
      name: name.trim(),
      contact_person: contact || null,
      email: email || null,
      phone: phone || null,
      address: address || null,
    };
    try {
      if (client) {
        await updateMutation.mutateAsync({ clientId: client.id, data: payload });
        toast.success("Client updated");
      } else {
        await createMutation.mutateAsync({ data: payload });
        toast.success("Client added");
      }
      await queryClient.invalidateQueries({ queryKey: ["/api/v1/clients"] });
      onOpenChange(false);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const pending = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{client ? client.name : "New client"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Company / client name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Contact person</Label>
              <Input value={contact} onChange={(e) => setContact(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Phone</Label>
              <Input value={phone} onChange={(e) => setPhone(e.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Email</Label>
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Address</Label>
            <Textarea rows={2} value={address} onChange={(e) => setAddress(e.target.value)} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button disabled={pending} onClick={() => void save()}>
              {pending ? "Saving…" : client ? "Save changes" : "Add client"}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
