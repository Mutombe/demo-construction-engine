import {
  ArrowCounterClockwise,
  CheckCircle,
  CircleNotch,
  FileText,
  Warning,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tooltip } from "@/components/ui/tooltip";
import { actionOf, DOC_TYPE_LABELS, type ProposedAction } from "@/features/ingestion/types";
import type { PumpCard } from "@/features/ingestion/useUploadPump";
import { fmtDate, money } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Confidence is the number the reviewer is actually deciding on, so it says
 *  what to do rather than only what it is. The bands match the pipeline gate:
 *  below 0.95 nothing posts automatically. */
function confidenceTone(score: number): { label: string; className: string } {
  if (score >= 0.95)
    return { label: "High confidence", className: "bg-success/10 text-success" };
  if (score >= 0.7)
    return { label: "Check before posting", className: "bg-warning/15 text-warning" };
  return { label: "Low confidence", className: "bg-destructive/10 text-destructive" };
}

/** The handful of facts a person scans for, in the order they scan them.
 *  Pulled from the pipeline's own display payload rather than re-derived. */
function keyFacts(docType: string | null | undefined, display: Record<string, unknown>) {
  const text = (key: string) => {
    const value = display[key];
    return typeof value === "string" && value.trim() ? value : null;
  };
  const facts: { label: string; value: string; strong?: boolean }[] = [];

  const amount = text("amount") ?? text("total_amount");
  if (amount) facts.push({ label: "Amount", value: money(amount), strong: true });

  const who = text("supplier_name") ?? text("supplier") ?? text("vendor_name");
  if (who) facts.push({ label: "From", value: who });

  const reference = text("invoice_number") ?? text("po");
  if (reference) {
    facts.push({
      label: docType === "delivery_note" ? "Order" : "Number",
      value: reference,
    });
  }

  const when = text("entry_date") ?? text("expense_date") ?? text("received_date");
  if (when) facts.push({ label: "Dated", value: fmtDate(when) });

  const project = text("project");
  if (project) facts.push({ label: "Project", value: project });

  return facts;
}

/** Only shown while the document is still moving. Once it has landed, the
 *  status and the reason say everything the stepper was repeating. */
function InFlight({ phase }: { phase: string }) {
  const label =
    phase === "processing" ? "Reading the document" : phase === "queued" ? "Queued" : "Uploading";
  return (
    <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <CircleNotch className="h-3.5 w-3.5 animate-spin" />
      {label}…
    </span>
  );
}

function Blockers({ action }: { action: ProposedAction }) {
  const reasons = [
    ...action.problems,
    ...action.missing_fields.map((field) => `Missing ${field.replace(/_/g, " ")}`),
  ];
  if (reasons.length === 0) return null;
  return (
    <ul className="space-y-0.5">
      {reasons.slice(0, 3).map((reason) => (
        <li key={reason} className="flex items-start gap-1.5 text-xs text-warning">
          <Warning className="mt-0.5 h-3 w-3 shrink-0" />
          <span>{reason}</span>
        </li>
      ))}
      {reasons.length > 3 && (
        <li className="pl-4.5 text-xs text-muted-foreground">
          and {reasons.length - 3} more
        </li>
      )}
    </ul>
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
  const failed = card.phase === "error" || item?.status === "failed";
  const posted = item?.status === "posted";
  const display = (action?.display ?? {}) as Record<string, unknown>;
  const facts = keyFacts(item?.doc_type, display);
  const summary = typeof display.summary === "string" ? display.summary : null;
  const confidence = action?.confidence_score;
  const tone = confidence != null ? confidenceTone(confidence) : null;

  const title = item?.doc_type ? DOC_TYPE_LABELS[item.doc_type] : "Unrecognised document";

  return (
    <Card className={cn(failed && "border-destructive/40")}>
      <CardContent className="flex gap-3.5 p-3.5">
        <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted">
          {card.objectUrl ? (
            <img src={card.objectUrl} alt="" className="h-full w-full object-cover" />
          ) : (
            <FileText className="h-6 w-6 text-muted-foreground" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          {/* What it is leads; the filename is metadata and sits underneath. */}
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="truncate text-sm font-semibold">
                {busy ? card.filename : title}
              </h3>
              {!busy && (
                <Tooltip content={card.filename}>
                  <p className="truncate text-xs text-muted-foreground">{card.filename}</p>
                </Tooltip>
              )}
            </div>
            {busy ? (
              <InFlight phase={card.phase} />
            ) : posted ? (
              <span className="flex shrink-0 items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-xs font-medium text-success">
                <CheckCircle className="h-3.5 w-3.5" weight="fill" /> Posted
              </span>
            ) : (
              tone && (
                <Tooltip
                  content={`The weakest extracted field scored ${((confidence ?? 0) * 100).toFixed(0)}%. Anything under 95% needs a person.`}
                >
                  <span
                    className={cn(
                      "shrink-0 rounded-full px-2 py-0.5 text-xs font-medium tabular-nums",
                      tone.className,
                    )}
                  >
                    {((confidence ?? 0) * 100).toFixed(0)}% · {tone.label}
                  </span>
                </Tooltip>
              )
            )}
          </div>

          {facts.length > 0 && (
            <dl className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
              {facts.map((fact) => (
                <div key={fact.label} className="flex items-baseline gap-1.5">
                  <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    {fact.label}
                  </dt>
                  <dd
                    className={cn(
                      "text-sm",
                      fact.strong ? "font-semibold tabular-nums" : "text-foreground",
                    )}
                  >
                    {fact.value}
                  </dd>
                </div>
              ))}
            </dl>
          )}

          {summary && (
            <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
              {summary}
            </p>
          )}

          {action && !posted && (
            <div className="mt-2">
              <Blockers action={action} />
            </div>
          )}

          {card.duplicateIds.length > 0 && (
            <p className="mt-2 flex items-center gap-1.5 text-xs text-warning">
              <Warning className="h-3 w-3 shrink-0" />
              This exact file was uploaded before
            </p>
          )}

          {(card.error || item?.error) && (
            <p className="mt-2 text-xs text-destructive">{card.error ?? item?.error}</p>
          )}

          {!busy && (
            <div className="mt-2.5 flex gap-2">
              {failed && card.itemId && (
                <Button size="sm" variant="outline" onClick={() => onRetry(card.localId)}>
                  <ArrowCounterClockwise /> Try Again
                </Button>
              )}
              {item &&
                (item.status === "drafted" ||
                  item.status === "needs_info" ||
                  item.status === "posted") && (
                  <Button
                    size="sm"
                    variant={item.status === "drafted" ? "default" : "outline"}
                    title={
                      item.status === "drafted"
                        ? "Check the extracted values and post it"
                        : item.status === "needs_info"
                          ? "Fill in what is missing, then post"
                          : "See what was posted"
                    }
                    onClick={() => onReview(item.id)}
                  >
                    {item.status === "posted"
                      ? "View"
                      : item.status === "drafted"
                        ? "Review & Post"
                        : "Fix & Post"}
                  </Button>
                )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
