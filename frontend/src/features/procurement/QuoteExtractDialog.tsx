import { useQueryClient } from "@tanstack/react-query";
import { Warning } from "@phosphor-icons/react";
import { ClaudeIcon } from "@/components/ui/claude-icon";
import { useEffect, useState } from "react";
import { toast } from "@/lib/toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAiStatus } from "@/features/ai/useAiStatus";
import {
  useCreateQuote,
  useExtractQuote,
  useListSuppliers,
} from "@/lib/api/generated/endpoints";
import type { RfqDetail } from "@/lib/api/generated/model";

interface DraftLine {
  rfq_item_id: string | null;
  description: string;
  unit: string;
  quantity: string;
  unit_price: string;
  confidence?: string;
  unit_mismatch?: boolean;
  quantity_mismatch?: boolean;
}

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

export function QuoteExtractDialog({
  open,
  onOpenChange,
  rfq,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rfq: RfqDetail;
}) {
  const queryClient = useQueryClient();
  const { aiAvailable } = useAiStatus();
  const { data: suppliers } = useListSuppliers(
    { page_size: 200, active_only: true },
    { query: { enabled: open } },
  );
  const extractMutation = useExtractQuote();
  const createMutation = useCreateQuote();

  const [supplierId, setSupplierId] = useState("");
  const [rawText, setRawText] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [paymentTerms, setPaymentTerms] = useState("");
  const [deliveryTerms, setDeliveryTerms] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [detectedName, setDetectedName] = useState<string | null>(null);
  const [aiUsed, setAiUsed] = useState(false);

  useEffect(() => {
    if (open) {
      setSupplierId("");
      setRawText("");
      setLines([]);
      setPaymentTerms("");
      setDeliveryTerms("");
      setValidUntil("");
      setDetectedName(null);
      setAiUsed(false);
    }
  }, [open]);

  const addManualLine = () => {
    setLines((prev) => [
      ...prev,
      { rfq_item_id: null, description: "", unit: "", quantity: "1", unit_price: "0" },
    ]);
  };

  const updateLine = (index: number, patch: Partial<DraftLine>) => {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  };

  const extract = async () => {
    try {
      const result = await extractMutation.mutateAsync({
        rfqId: rfq.id,
        data: { raw_text: rawText },
      });
      setLines(
        result.lines.map((l) => ({
          rfq_item_id: l.rfq_item_id,
          description: l.description,
          unit: l.unit ?? "",
          quantity: String(l.quantity),
          unit_price: String(l.unit_price),
          confidence: l.match_confidence,
          unit_mismatch: l.unit_mismatch,
          quantity_mismatch: l.quantity_mismatch,
        })),
      );
      setPaymentTerms(result.payment_terms ?? "");
      setDeliveryTerms(result.delivery_terms ?? "");
      setValidUntil(result.valid_until ?? "");
      setDetectedName(result.supplier_name ?? null);
      setAiUsed(true);
      if (result.currency_warning) {
        toast.warning(`Quote appears to be in ${result.currency} — check before saving`);
      }
      if (result.notes) toast.info(result.notes);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const save = async () => {
    if (!supplierId) {
      toast.error("Select the supplier");
      return;
    }
    if (!lines.length) {
      toast.error("Add at least one line");
      return;
    }
    try {
      await createMutation.mutateAsync({
        rfqId: rfq.id,
        data: {
          supplier_id: supplierId,
          payment_terms: paymentTerms || null,
          delivery_terms: deliveryTerms || null,
          valid_until: validUntil || null,
          raw_text: aiUsed ? rawText : null,
          ai_extracted: aiUsed,
          items: lines.map((l) => ({
            rfq_item_id: l.rfq_item_id,
            description: l.description || "(no description)",
            unit: l.unit || null,
            quantity: l.quantity || "0",
            unit_price: l.unit_price || "0",
          })),
        },
      });
      await queryClient.invalidateQueries();
      toast.success("Quote recorded");
      onOpenChange(false);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const confidenceBadge = (line: DraftLine) => {
    if (!line.confidence) return null;
    if (line.rfq_item_id === null || line.confidence === "unmatched")
      return <Badge variant="warning">unmatched</Badge>;
    if (line.confidence === "probable") return <Badge variant="secondary">probable</Badge>;
    return <Badge variant="success">matched</Badge>;
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>Record Quote — {rfq.doc_number}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Supplier</Label>
              <Select value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
                <option value="">Select supplier…</option>
                {suppliers?.items.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </Select>
              {detectedName && !supplierId && (
                <p className="text-xs text-muted-foreground">
                  AI detected: <span className="font-medium">{detectedName}</span> — pick the
                  matching registry entry.
                </p>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Valid Until</Label>
                <Input
                  type="date"
                  value={validUntil}
                  onChange={(e) => setValidUntil(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Payment Terms</Label>
                <Input
                  value={paymentTerms}
                  onChange={(e) => setPaymentTerms(e.target.value)}
                  placeholder="30 days net"
                />
              </div>
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label>Paste the supplier's quote (email / PDF text)</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!aiAvailable || rawText.length < 10 || extractMutation.isPending}
                title={aiAvailable ? undefined : "AI not configured — add ANTHROPIC_API_KEY"}
                onClick={() => void extract()}
              >
                <ClaudeIcon className="h-3.5 w-3.5" />
                {extractMutation.isPending ? "Extracting…" : "Extract with AI"}
              </Button>
            </div>
            <Textarea
              rows={5}
              className="font-mono text-xs"
              placeholder="Dear Sir, further to your RFQ we are pleased to quote as follows…"
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label>Quote Lines</Label>
              <Button type="button" variant="ghost" size="sm" onClick={addManualLine}>
                + Add Line Manually
              </Button>
            </div>
            <div className="max-h-64 space-y-1.5 overflow-y-auto pr-1">
              {!lines.length && (
                <p className="rounded-md border border-dashed p-4 text-center text-sm text-muted-foreground">
                  Extract from pasted text, or add lines manually.
                </p>
              )}
              {lines.map((line, i) => (
                <div key={i} className="grid grid-cols-[1fr_150px_70px_80px_90px_90px] items-center gap-1.5 rounded-md border p-1.5">
                  <Input
                    className="h-8 text-xs"
                    placeholder="Description"
                    value={line.description}
                    onChange={(e) => updateLine(i, { description: e.target.value })}
                  />
                  <Select
                    className="h-8 text-xs"
                    value={line.rfq_item_id ?? ""}
                    onChange={(e) => updateLine(i, { rfq_item_id: e.target.value || null })}
                  >
                    <option value="">— no RFQ line —</option>
                    {(rfq.items ?? []).map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.description.slice(0, 30)}
                      </option>
                    ))}
                  </Select>
                  <Input
                    className="h-8 text-xs"
                    placeholder="unit"
                    value={line.unit}
                    onChange={(e) => updateLine(i, { unit: e.target.value })}
                  />
                  <Input
                    className="h-8 text-right text-xs"
                    type="number"
                    value={line.quantity}
                    onChange={(e) => updateLine(i, { quantity: e.target.value })}
                  />
                  <Input
                    className="h-8 text-right text-xs"
                    type="number"
                    step="0.01"
                    value={line.unit_price}
                    onChange={(e) => updateLine(i, { unit_price: e.target.value })}
                  />
                  <div className="flex items-center justify-end gap-1">
                    {(line.unit_mismatch || line.quantity_mismatch) && (
                      <span title="Unit or quantity differs from the RFQ line">
                        <Warning className="h-3.5 w-3.5 text-warning" />
                      </span>
                    )}
                    {confidenceBadge(line)}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button disabled={createMutation.isPending} onClick={() => void save()}>
              {createMutation.isPending ? "Saving…" : "Save Quote"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
