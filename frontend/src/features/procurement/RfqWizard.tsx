import { useQueryClient } from "@tanstack/react-query";
import { ClaudeIcon } from "@/components/ui/claude-icon";
import { useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { toast } from "@/lib/toast";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAiStatus } from "@/features/ai/useAiStatus";
import {
  useCreateRfq,
  useGenerateRfqDraft,
  useGetBoq,
} from "@/lib/api/generated/endpoints";
import { money } from "@/lib/format";
import { cn } from "@/lib/utils";

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

export function RfqWizard({
  open,
  onOpenChange,
  projectId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { aiAvailable } = useAiStatus();
  const { data: boq } = useGetBoq(projectId, { query: { enabled: open } });
  const generateMutation = useGenerateRfqDraft();
  const createMutation = useCreateRfq();

  const [step, setStep] = useState<1 | 2>(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [instructions, setInstructions] = useState("");
  const [aiUsed, setAiUsed] = useState(false);

  useEffect(() => {
    if (open) {
      setStep(1);
      setSelected(new Set());
      setTitle("");
      setBody("");
      setDueDate("");
      setInstructions("");
      setAiUsed(false);
    }
  }, [open]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const draftWithAi = async () => {
    try {
      const draft = await generateMutation.mutateAsync({
        data: {
          project_id: projectId,
          boq_item_ids: [...selected],
          title: title || null,
          instructions: instructions || null,
        },
      });
      setTitle(draft.title);
      setBody(draft.body);
      setAiUsed(true);
      toast.success("Draft ready. Review and edit before saving");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const save = async () => {
    if (!title.trim()) {
      toast.error("Give the RFQ a title");
      return;
    }
    try {
      const rfq = await createMutation.mutateAsync({
        projectId,
        data: {
          title,
          body: body || null,
          due_date: dueDate || null,
          ai_generated: aiUsed,
          items: [...selected].map((id) => ({ boq_item_id: id })),
        },
      });
      await queryClient.invalidateQueries();
      onOpenChange(false);
      toast.success(`${rfq.doc_number} created as draft`);
      await navigate({ to: "/procurement/rfqs/$rfqId", params: { rfqId: rfq.id } });
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>
            {step === 1 ? "New RFQ: Select BOQ Items" : "New RFQ: Document"}
          </DialogTitle>
        </DialogHeader>

        {step === 1 && (
          <div className="space-y-4">
            <div className="max-h-96 space-y-3 overflow-y-auto pr-1">
              {!boq?.sections.length && (
                <p className="text-sm text-muted-foreground">
                  This project has no BOQ items yet. Add them in the BOQ tab first.
                </p>
              )}
              {boq?.sections.map((section) => (
                <div key={section.id}>
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {section.code} · {section.title}
                  </div>
                  <div className="space-y-1">
                    {(section.items ?? []).map((item) => (
                      <label
                        key={item.id}
                        className={cn(
                          "flex cursor-pointer items-center gap-3 rounded-md border p-2 text-sm transition-colors",
                          selected.has(item.id) ? "border-primary bg-accent" : "hover:bg-accent/50",
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={selected.has(item.id)}
                          onChange={() => toggle(item.id)}
                        />
                        <span className="font-mono text-xs text-muted-foreground">
                          {item.item_code}
                        </span>
                        <span className="flex-1 truncate">{item.description}</span>
                        <span className="shrink-0 text-xs text-muted-foreground">
                          {Number(item.quantity).toLocaleString()} {item.unit} ·{" "}
                          {money(item.amount)}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-muted-foreground">
                {selected.size} item{selected.size === 1 ? "" : "s"} selected
              </span>
              <Button disabled={selected.size === 0} onClick={() => setStep(2)}>
                Continue
              </Button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <div className="col-span-2 space-y-1.5">
                <Label htmlFor="rfq-title">Title</Label>
                <Input
                  id="rfq-title"
                  placeholder="Supply of cement and reinforcement"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="rfq-due">Quotes Due</Label>
                <Input
                  id="rfq-due"
                  type="date"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="rfq-body">RFQ Document Body</Label>
                <div className="flex items-center gap-2">
                  <Input
                    className="h-8 w-64 text-xs"
                    placeholder="Optional instructions for the AI…"
                    value={instructions}
                    onChange={(e) => setInstructions(e.target.value)}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!aiAvailable || generateMutation.isPending}
                    title={aiAvailable ? undefined : "AI not configured. Add ANTHROPIC_API_KEY"}
                    onClick={() => void draftWithAi()}
                  >
                    <ClaudeIcon className="h-3.5 w-3.5" />
                    {generateMutation.isPending
                      ? "Drafting…"
                      : aiUsed
                        ? "Regenerate"
                        : "Draft with AI"}
                  </Button>
                </div>
              </div>
              <Textarea
                id="rfq-body"
                rows={14}
                className="font-mono text-xs"
                placeholder={
                  aiAvailable
                    ? "Write the RFQ text, or let Claude draft it for you…"
                    : "Write the RFQ text…"
                }
                value={body}
                onChange={(e) => setBody(e.target.value)}
              />
            </div>

            <div className="flex justify-between">
              <Button variant="outline" onClick={() => setStep(1)}>
                Back
              </Button>
              <Button disabled={createMutation.isPending} onClick={() => void save()}>
                {createMutation.isPending ? "Saving…" : "Create RFQ Draft"}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
