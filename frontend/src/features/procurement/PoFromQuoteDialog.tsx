import { useQueryClient } from "@tanstack/react-query";
import { ClaudeIcon } from "@/components/ui/claude-icon";
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
import { Textarea } from "@/components/ui/textarea";
import { useAiStatus } from "@/features/ai/useAiStatus";
import {
  useCreatePurchaseOrder,
  useDraftPoTerms,
} from "@/lib/api/generated/endpoints";

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

export function PoFromQuoteDialog({
  open,
  onOpenChange,
  quoteId,
  projectId,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  quoteId: string;
  projectId: string;
  onCreated?: (poId: string) => void;
}) {
  const queryClient = useQueryClient();
  const { aiAvailable } = useAiStatus();
  const draftMutation = useDraftPoTerms();
  const createMutation = useCreatePurchaseOrder();

  const [terms, setTerms] = useState("");
  const [notes, setNotes] = useState("");
  const [expectedDelivery, setExpectedDelivery] = useState("");
  const [aiUsed, setAiUsed] = useState(false);

  useEffect(() => {
    if (open) {
      setTerms("");
      setNotes("");
      setExpectedDelivery("");
      setAiUsed(false);
    }
  }, [open]);

  const draftTerms = async () => {
    try {
      const draft = await draftMutation.mutateAsync({ data: { quote_id: quoteId } });
      setTerms(draft.terms);
      setNotes(draft.notes);
      setAiUsed(true);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const create = async () => {
    try {
      const po = await createMutation.mutateAsync({
        projectId,
        data: {
          quote_id: quoteId,
          expected_delivery: expectedDelivery || null,
          terms: terms || null,
          notes: notes || null,
          ai_generated: aiUsed,
        },
      });
      await queryClient.invalidateQueries();
      toast.success(`${po.doc_number} created as draft`);
      onOpenChange(false);
      onCreated?.(po.id);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Create Purchase Order from Quote</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Line items and pricing are copied exactly from the accepted quote — the AI only
            drafts the commercial terms text.
          </p>
          <div className="space-y-1.5">
            <Label htmlFor="po-delivery">Expected Delivery</Label>
            <Input
              id="po-delivery"
              type="date"
              className="w-48"
              value={expectedDelivery}
              onChange={(e) => setExpectedDelivery(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="po-terms">Commercial Terms</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!aiAvailable || draftMutation.isPending}
                title={aiAvailable ? undefined : "AI not configured — add ANTHROPIC_API_KEY"}
                onClick={() => void draftTerms()}
              >
                <ClaudeIcon className="h-3.5 w-3.5" />
                {draftMutation.isPending ? "Drafting…" : "Draft Terms with AI"}
              </Button>
            </div>
            <Textarea
              id="po-terms"
              rows={8}
              value={terms}
              onChange={(e) => setTerms(e.target.value)}
              placeholder="Payment terms, delivery expectations, quality requirements…"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="po-notes">Internal Notes</Label>
            <Textarea
              id="po-notes"
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button disabled={createMutation.isPending} onClick={() => void create()}>
              {createMutation.isPending ? "Creating…" : "Create PO Draft"}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
