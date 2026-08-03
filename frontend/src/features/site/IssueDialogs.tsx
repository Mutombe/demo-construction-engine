import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "@/lib/toast";
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
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useCreateSiteIssue, useResolveSiteIssue } from "@/lib/api/generated/endpoints";

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

export function RaiseIssueDialog({
  open,
  onOpenChange,
  projectId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
}) {
  const queryClient = useQueryClient();
  const createMutation = useCreateSiteIssue();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState("medium");

  useEffect(() => {
    if (open) {
      setTitle("");
      setDescription("");
      setSeverity("medium");
    }
  }, [open]);

  const save = async () => {
    if (!title.trim()) {
      toast.error("Give the issue a title");
      return;
    }
    try {
      await createMutation.mutateAsync({
        projectId,
        data: { title, description: description || null, severity: severity as never },
      });
      await queryClient.invalidateQueries();
      toast.success("Issue raised");
      onOpenChange(false);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Raise site issue</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2 space-y-1.5">
              <Label>Title</Label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Severity</Label>
              <Select value={severity} onChange={(e) => setSeverity(e.target.value)}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Description</Label>
            <Textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button disabled={createMutation.isPending} onClick={() => void save()}>
              Raise issue
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function ResolveIssueDialog({
  issueId,
  onClose,
}: {
  issueId: string | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const resolveMutation = useResolveSiteIssue();
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (issueId) setNotes("");
  }, [issueId]);

  const resolve = async () => {
    if (!issueId) return;
    try {
      await resolveMutation.mutateAsync({
        issueId,
        data: { resolution_notes: notes || null },
      });
      await queryClient.invalidateQueries();
      toast.success("Issue resolved");
      onClose();
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={issueId !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Resolve issue</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Textarea
            rows={3}
            placeholder="How was it resolved? (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button disabled={resolveMutation.isPending} onClick={() => void resolve()}>
              Mark resolved
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
