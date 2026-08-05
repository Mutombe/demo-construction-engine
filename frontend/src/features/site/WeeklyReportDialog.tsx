import { Copy } from "@phosphor-icons/react";
import { ClaudeIcon } from "@/components/ui/claude-icon";
import { useEffect, useState } from "react";
import { toast } from "@/lib/toast";
import { FilePdf } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { downloadFile } from "@/lib/api/download";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RichMarkdown } from "@/components/ui/markdown";
import { useAiStatus } from "@/features/ai/useAiStatus";
import { useGenerateWeeklyReport } from "@/lib/api/generated/endpoints";
import { fmtDate } from "@/lib/format";

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

function lastMonday(): string {
  const today = new Date();
  const day = today.getDay();
  const diff = (day + 6) % 7; // days since Monday
  const monday = new Date(today);
  monday.setDate(today.getDate() - diff - 7); // previous full week
  return monday.toISOString().slice(0, 10);
}

export function WeeklyReportDialog({
  open,
  onOpenChange,
  projectId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
}) {
  const { aiAvailable } = useAiStatus();
  const generateMutation = useGenerateWeeklyReport();
  const [weekStart, setWeekStart] = useState(lastMonday());
  const [markdown, setMarkdown] = useState("");
  const [period, setPeriod] = useState<{ start: string; end: string } | null>(null);

  useEffect(() => {
    if (open) {
      setMarkdown("");
      setPeriod(null);
      setWeekStart(lastMonday());
    }
  }, [open]);

  const generate = async () => {
    try {
      const draft = await generateMutation.mutateAsync({
        data: { project_id: projectId, week_start: weekStart },
      });
      setMarkdown(draft.markdown);
      setPeriod({ start: draft.period_start, end: draft.period_end });
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const [downloading, setDownloading] = useState(false);

  /** Rebuilt from the week's data rather than from the text on screen: a PDF
   *  that says it covers a week has to be produced from that week. */
  const download = async () => {
    setDownloading(true);
    try {
      await downloadFile(
        "/api/v1/ai/site/weekly-report/pdf",
        `weekly_report_${period?.end ?? weekStart}.pdf`,
        { method: "POST", body: { project_id: projectId, week_start: weekStart } },
      );
    } catch {
      toast.error("Could not build the report");
    } finally {
      setDownloading(false);
    }
  };

  const copy = async () => {
    await navigator.clipboard.writeText(markdown);
    toast.success("Report copied to clipboard");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Weekly Site Report</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="flex items-end gap-3">
            <div className="space-y-1.5">
              <Label>Week Starting</Label>
              <Input
                type="date"
                className="w-44"
                value={weekStart}
                onChange={(e) => setWeekStart(e.target.value)}
              />
            </div>
            <Button
              disabled={!aiAvailable || generateMutation.isPending}
              title={aiAvailable ? undefined : "AI not configured. Add ANTHROPIC_API_KEY"}
              onClick={() => void generate()}
            >
              <ClaudeIcon />
              {generateMutation.isPending ? "Writing report…" : markdown ? "Regenerate" : "Generate"}
            </Button>
            {markdown && (
              <Button
                variant="outline"
                disabled={downloading}
                title="A copy you can send to the client"
                onClick={() => void download()}
              >
                <FilePdf /> {downloading ? "Preparing…" : "PDF"}
              </Button>
            )}
            {markdown && (
              <Button variant="outline" onClick={() => void copy()}>
                <Copy /> Copy
              </Button>
            )}
          </div>

          {generateMutation.isPending && (
            <p className="text-sm text-muted-foreground">
              Claude is reading the site diaries, issues and costs for the period…
            </p>
          )}

          {markdown && (
            <div className="max-h-[55vh] overflow-y-auto rounded-md border bg-secondary/30 p-4">
              {period && (
                <p className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
                  Period {fmtDate(period.start)} · {fmtDate(period.end)} · draft, review before
                  sending
                </p>
              )}
              <RichMarkdown content={markdown} variant="document" />
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
