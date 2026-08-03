import { AlertTriangle, Check, FileText, Loader2, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { IngestionStatusBadge } from "@/features/ingestion/StatusBadge";
import { actionOf, DOC_TYPE_LABELS } from "@/features/ingestion/types";
import type { PumpCard } from "@/features/ingestion/useUploadPump";
import { cn } from "@/lib/utils";

const STEPS = ["Parsed", "Validated", "Review", "Posted"] as const;

function stepIndex(card: PumpCard): number {
  if (card.phase === "uploading" || card.phase === "queued" || card.phase === "processing")
    return 0;
  const status = card.item?.status;
  if (status === "posted") return 4;
  if (status === "drafted" || status === "needs_info" || status === "rejected") return 3;
  return 1;
}

function PipelineStepper({ card }: { card: PumpCard }) {
  const reached = stepIndex(card);
  const failed = card.phase === "error" || card.item?.status === "failed";
  const amber = card.item?.status === "needs_info";
  return (
    <div className="flex items-center gap-1">
      {STEPS.map((step, i) => {
        const done = reached > i;
        const active = reached === i && !failed;
        return (
          <div key={step} className="flex items-center gap-1">
            {i > 0 && <div className={cn("h-px w-3", done ? "bg-primary" : "bg-border")} />}
            <div
              className={cn(
                "flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium",
                done && "bg-primary/10 text-primary",
                active && "bg-muted text-foreground",
                !done && !active && "text-muted-foreground",
                failed && i === reached && "bg-destructive/10 text-destructive",
                amber && step === "Review" && "bg-amber-500/15 text-amber-600",
              )}
            >
              {done ? <Check className="h-2.5 w-2.5" /> : null}
              {step}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function IngestionCard({
  card,
  onRetry,
  onReview,
}: {
  card: PumpCard;
  onRetry: (localId: string) => void;
  onReview: (itemId: string) => void;
}) {
  const item = card.item;
  const action = item ? actionOf(item) : null;
  const busy =
    card.phase === "uploading" || card.phase === "queued" || card.phase === "processing";

  return (
    <Card>
      <CardContent className="flex gap-3 p-3">
        <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted">
          {card.objectUrl ? (
            <img src={card.objectUrl} alt="" className="h-full w-full object-cover" />
          ) : (
            <FileText className="h-6 w-6 text-muted-foreground" />
          )}
        </div>
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-sm font-medium">{card.filename}</span>
            {busy ? (
              <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                {card.phase === "processing" ? "Extracting…" : "Uploading…"}
              </span>
            ) : (
              item && <IngestionStatusBadge status={item.status} />
            )}
          </div>
          <PipelineStepper card={card} />
          {item?.doc_type && (
            <div className="text-xs text-muted-foreground">
              {DOC_TYPE_LABELS[item.doc_type]}
              {action?.confidence_score != null && (
                <> · confidence {(action.confidence_score * 100).toFixed(0)}%</>
              )}
              {typeof action?.display?.summary === "string" && (
                <span className="block truncate">{action.display.summary}</span>
              )}
            </div>
          )}
          {card.duplicateIds.length > 0 && (
            <div className="flex items-center gap-1 text-xs text-amber-600">
              <AlertTriangle className="h-3 w-3" /> Identical file uploaded before — check the
              history below.
            </div>
          )}
          {(card.error || item?.error) && (
            <div className="text-xs text-destructive">{card.error ?? item?.error}</div>
          )}
          <div className="flex gap-2 pt-0.5">
            {(card.phase === "error" || item?.status === "failed") && card.itemId && (
              <Button size="sm" variant="outline" onClick={() => onRetry(card.localId)}>
                <RotateCcw /> Retry
              </Button>
            )}
            {item &&
              (item.status === "drafted" ||
                item.status === "needs_info" ||
                item.status === "posted") && (
                <Button
                  size="sm"
                  variant={item.status === "drafted" ? "default" : "outline"}
                  onClick={() => onReview(item.id)}
                >
                  {item.status === "posted" ? "View" : "Review"}
                </Button>
              )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
