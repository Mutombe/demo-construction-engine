import { useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowSquareOut, CheckCircle, Warning, XCircle } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { toast } from "@/lib/toast";
import { Can } from "@/components/layout/Can";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { IngestionStatusBadge } from "@/features/ingestion/StatusBadge";
import {
  ACTION_LABELS,
  actionOf,
  DOC_TYPE_LABELS,
  fieldValue,
  type ProposedAction,
} from "@/features/ingestion/types";
import { useAuthedFile } from "@/features/ingestion/useAuthedFile";
import {
  useApproveIngestionItem,
  useGetIngestionItem,
  useRedraftIngestionItem,
  useRejectIngestionItem,
} from "@/lib/api/generated/endpoints";
import type { IngestionItemRead } from "@/lib/api/generated/model";
import { cn } from "@/lib/utils";

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

/** The posted record is a destination — link straight to it from the lineage. */
function LineageLink({
  item,
  action,
}: {
  item: IngestionItemRead;
  action: ProposedAction;
}) {
  const lineage = action.lineage;
  if (!lineage?.posted_type) return null;
  const label = (
    <>
      Posted as {lineage.posted_type.replace("_", " ")}
      {lineage.reference && <> — {lineage.reference}</>}
    </>
  );
  const id = lineage.posted_id;
  const linkClass = "font-medium underline underline-offset-2 hover:opacity-80";
  if (lineage.posted_type === "purchase_order" && id) {
    return (
      <Link to="/procurement/pos/$poId" params={{ poId: id }} className={linkClass}>
        {label}
      </Link>
    );
  }
  if (lineage.posted_type === "expense_claim" && id) {
    return (
      <Link to="/expenses/$claimId" params={{ claimId: id }} className={linkClass}>
        {label}
      </Link>
    );
  }
  if (lineage.posted_type === "cost_entry" && item.project_id) {
    return (
      <Link
        to="/projects/$projectId/boq"
        params={{ projectId: item.project_id }}
        className={linkClass}
      >
        {label}
      </Link>
    );
  }
  return <span>{label}</span>;
}

const FIELD_LABELS: Record<string, string> = {
  supplier_name: "Supplier",
  invoice_number: "Invoice Number",
  invoice_date: "Invoice Date",
  total_amount: "Total Amount",
  project_match: "Project",
  vendor_name: "Vendor",
  receipt_date: "Receipt Date",
  description: "Description",
  po_match: "Purchase Order",
  delivery_date: "Delivery Date",
  rfq_match: "RFQ",
};

function ConfidenceDot({ score }: { score: number }) {
  return (
    <span
      className={cn(
        "inline-block h-2 w-2 shrink-0 rounded-full",
        score >= 0.95 ? "bg-emerald-500" : score >= 0.8 ? "bg-amber-500" : "bg-red-500",
      )}
      title={`${(score * 100).toFixed(0)}% confidence`}
    />
  );
}

function FieldRow({
  item,
  field,
  score,
  edited,
  onEdit,
}: {
  item: IngestionItemRead;
  field: string;
  score: number;
  edited: string | undefined;
  onEdit: (field: string, value: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const value = edited ?? fieldValue(item, field);
  const missing = actionOf(item)?.missing_fields.includes(field);

  return (
    <div className="flex items-center gap-2 py-1 text-sm">
      <ConfidenceDot score={edited !== undefined ? 1 : score} />
      <span className="w-32 shrink-0 text-muted-foreground">
        {FIELD_LABELS[field] ?? field}
      </span>
      {editing ? (
        <Input
          autoFocus
          className="h-7"
          defaultValue={value}
          onBlur={(e) => {
            setEditing(false);
            if (e.target.value !== value) onEdit(field, e.target.value);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
            if (e.key === "Escape") setEditing(false);
          }}
        />
      ) : (
        <button
          type="button"
          className={cn(
            "flex-1 truncate rounded px-1 py-0.5 text-left hover:bg-muted",
            !value && "italic text-muted-foreground",
            missing && "text-destructive",
          )}
          title="Click to correct"
          onClick={() => setEditing(true)}
        >
          {value || (missing ? "missing — click to fill in" : "—")}
        </button>
      )}
      {edited !== undefined && (
        <span className="shrink-0 text-[10px] uppercase text-primary">edited</span>
      )}
    </div>
  );
}

export function ReviewPanel({
  itemId,
  onOpenChange,
  onUpdated,
}: {
  itemId: string | null;
  onOpenChange: (open: boolean) => void;
  onUpdated?: (item: IngestionItemRead) => void;
}) {
  const queryClient = useQueryClient();
  const { data: item } = useGetIngestionItem(itemId ?? "", {
    query: { enabled: !!itemId },
  });
  const fileUrl = useAuthedFile(itemId ?? undefined);
  const approveMutation = useApproveIngestionItem();
  const rejectMutation = useRejectIngestionItem();
  const redraftMutation = useRedraftIngestionItem();

  const [edits, setEdits] = useState<Record<string, string>>({});
  const [rejecting, setRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  useEffect(() => {
    setEdits({});
    setRejecting(false);
    setRejectReason("");
  }, [itemId]);

  if (!itemId) return null;
  const action = item ? actionOf(item) : null;
  const finalized = item?.status === "posted" || item?.status === "rejected";
  const hasEdits = Object.keys(edits).length > 0;

  const finish = async (updated: IngestionItemRead, message: string) => {
    onUpdated?.(updated);
    await queryClient.invalidateQueries();
    toast.success(message);
  };

  const recheck = async () => {
    try {
      const updated = await redraftMutation.mutateAsync({
        itemId,
        data: { corrections: edits },
      });
      setEdits({});
      await finish(
        updated,
        updated.status === "drafted"
          ? "Corrections applied — ready to approve"
          : "Corrections applied — still needs attention",
      );
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const approve = async () => {
    try {
      const updated = await approveMutation.mutateAsync({ itemId });
      await finish(updated, "Approved — record posted");
      onOpenChange(false);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const reject = async () => {
    if (!rejectReason.trim()) {
      toast.error("Give a short reason for rejecting");
      return;
    }
    try {
      const updated = await rejectMutation.mutateAsync({
        itemId,
        data: { reason: rejectReason },
      });
      await finish(updated, "Item rejected");
      onOpenChange(false);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={!!itemId} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {item?.doc_type ? DOC_TYPE_LABELS[item.doc_type] : "Document"}
            {item && <IngestionStatusBadge status={item.status} />}
          </DialogTitle>
        </DialogHeader>
        {!item ? (
          <div className="p-8 text-center text-muted-foreground">Loading…</div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="max-h-96 overflow-hidden rounded-md border bg-muted/40">
              {fileUrl ? (
                item.media_type === "application/pdf" ? (
                  <iframe src={fileUrl} title="document" className="h-96 w-full" />
                ) : (
                  <img src={fileUrl} alt="document" className="h-full w-full object-contain" />
                )
              ) : (
                <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
                  Loading preview…
                </div>
              )}
            </div>

            <div className="space-y-3">
              {typeof action?.display?.summary === "string" && (
                <p className="text-sm text-muted-foreground">{action.display.summary}</p>
              )}

              {action && action.problems.length > 0 && (
                <div className="space-y-1 rounded-md border border-amber-300 bg-amber-500/10 p-2.5">
                  {action.problems.map((p) => (
                    <div key={p} className="flex items-start gap-1.5 text-xs text-amber-700">
                      <Warning className="mt-0.5 h-3 w-3 shrink-0" /> {p}
                    </div>
                  ))}
                </div>
              )}

              {action && Object.keys(action.field_confidence).length > 0 && (
                <div className="rounded-md border p-2.5">
                  {Object.entries(action.field_confidence).map(([field, score]) => (
                    <FieldRow
                      key={field}
                      item={item}
                      field={field}
                      score={score}
                      edited={edits[field]}
                      onEdit={(f, v) => setEdits((prev) => ({ ...prev, [f]: v }))}
                    />
                  ))}
                </div>
              )}

              {action?.action && (
                <div className="text-xs text-muted-foreground">
                  On approval: <span className="font-medium">{ACTION_LABELS[action.action]}</span>
                  {Object.entries(action.display)
                    .filter(([k]) => k !== "summary")
                    .map(([k, v]) => (
                      <span key={k}>
                        {" "}
                        · {k.replace("_", " ")}: {String(v)}
                      </span>
                    ))}
                </div>
              )}

              {action?.lineage?.posted_type && (
                <div className="flex items-center gap-1.5 rounded-md border border-emerald-300 bg-emerald-500/10 p-2.5 text-xs text-emerald-700">
                  <ArrowSquareOut className="h-3 w-3" />
                  <LineageLink item={item} action={action} />
                </div>
              )}
              {item.rejection_reason && (
                <div className="rounded-md border border-destructive/40 bg-destructive/10 p-2.5 text-xs text-destructive">
                  Rejected: {item.rejection_reason}
                </div>
              )}

              {rejecting && !finalized && (
                <Textarea
                  rows={2}
                  autoFocus
                  placeholder="Why is this document being rejected?"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                />
              )}
            </div>
          </div>
        )}

        {item && !finalized && (
          <DialogFooter>
            {rejecting ? (
              <>
                <Button variant="outline" onClick={() => setRejecting(false)}>
                  Back
                </Button>
                <Button
                  variant="destructive"
                  disabled={rejectMutation.isPending}
                  onClick={() => void reject()}
                >
                  <XCircle /> Confirm Reject
                </Button>
              </>
            ) : (
              <>
                <Button variant="outline" onClick={() => setRejecting(true)}>
                  Reject
                </Button>
                {hasEdits && (
                  <Button
                    variant="secondary"
                    disabled={redraftMutation.isPending}
                    onClick={() => void recheck()}
                  >
                    {redraftMutation.isPending ? "Re-checking…" : "Apply Corrections"}
                  </Button>
                )}
                <Can perm="ingestion:approve">
                  <Button
                    disabled={
                      approveMutation.isPending || item.status !== "drafted" || hasEdits
                    }
                    title={
                      hasEdits
                        ? "Apply your corrections first"
                        : item.status !== "drafted"
                          ? "Resolve the highlighted issues first"
                          : undefined
                    }
                    onClick={() => void approve()}
                  >
                    <CheckCircle /> Approve &amp; Post
                  </Button>
                </Can>
              </>
            )}
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
