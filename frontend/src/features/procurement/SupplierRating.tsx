import { useQueryClient } from "@tanstack/react-query";
import { Star, ThumbsUp, Warning } from "@phosphor-icons/react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { errDetail } from "@/lib/api/errors";
import { useAssessDelivery, useGetSupplierRating } from "@/lib/api/generated/endpoints";
import { cn } from "@/lib/utils";
import { toast } from "@/lib/toast";

/** Five dots rather than five stars, because a star implies a review and this
 *  is an assessment. Unknown is drawn as absent, never as zero. */
export function Score({
  value,
  label,
}: {
  value: string | number | null | undefined;
  label: string;
}) {
  const score = value == null ? null : Number(value);
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      {score == null ? (
        <span className="text-xs text-muted-foreground">Not known yet</span>
      ) : (
        <span className="flex items-center gap-2">
          <span className="flex gap-0.5">
            {[1, 2, 3, 4, 5].map((step) => (
              <span
                key={step}
                className={cn(
                  "h-1.5 w-4 rounded-sm",
                  step <= Math.round(score)
                    ? score >= 4
                      ? "bg-success"
                      : score >= 3
                        ? "bg-warning"
                        : "bg-destructive"
                    : "bg-muted",
                )}
              />
            ))}
          </span>
          <span className="w-7 text-right text-sm font-medium tabular-nums">
            {score.toFixed(1)}
          </span>
        </span>
      )}
    </div>
  );
}

/** How a supplier has actually behaved, across the four things that decide
 *  whether to use them again. */
export function SupplierRatingCard({ supplierId }: { supplierId: string }) {
  const { data: rating } = useGetSupplierRating(supplierId);
  if (!rating) return null;

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            Track record
            {rating.provisional && <Badge variant="outline">Provisional</Badge>}
          </CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {rating.assessments === 0
              ? "No delivery has been judged yet."
              : `From ${rating.assessments} judged ${
                  rating.assessments === 1 ? "delivery" : "deliveries"
                }${
                  rating.contested_enquiries
                    ? ` and ${rating.contested_enquiries} contested enquiries`
                    : ""
                }.`}
          </p>
        </div>
        {rating.overall != null && (
          <div className="text-right">
            <div className="text-2xl font-semibold tabular-nums">
              {Number(rating.overall).toFixed(1)}
            </div>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
              overall
            </div>
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-2.5 text-sm">
        <Score label="Quality" value={rating.quality} />
        <Score label="Professionalism" value={rating.professionalism} />
        <Score label="Delivery" value={rating.delivery} />
        <Score label="Price" value={rating.price} />

        <div className="space-y-1 border-t pt-2 text-xs text-muted-foreground">
          {rating.on_time_pct != null && (
            <div className="flex justify-between">
              <span>Delivered on time</span>
              <span className="tabular-nums">{Number(rating.on_time_pct).toFixed(0)}%</span>
            </div>
          )}
          {rating.avg_above_lowest_pct != null && (
            <div className="flex justify-between">
              <span>Above the cheapest bid, on average</span>
              <span className="tabular-nums">
                {Number(rating.avg_above_lowest_pct).toFixed(1)}%
              </span>
            </div>
          )}
          {(rating.contested_enquiries ?? 0) > 0 && (
            <div className="flex justify-between">
              <span>Cheapest bid</span>
              <span className="tabular-nums">
                {rating.lowest_bid_count} of {rating.contested_enquiries}
              </span>
            </div>
          )}
          {rating.would_use_again_pct != null && (
            <div className="flex justify-between">
              <span>Would use again</span>
              <span className="tabular-nums">
                {Number(rating.would_use_again_pct).toFixed(0)}%
              </span>
            </div>
          )}
        </div>

        {rating.overall == null && (rating.assessments ?? 0) > 0 && (
          <p className="text-xs text-muted-foreground">
            No overall score: it is only given once quality, professionalism, delivery and
            price are all known. Averaging around a gap would look like a verdict.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/** Judging a delivery. The only two things here that cannot be derived from
 *  what the system already knows. */
export function AssessDeliveryDialog({
  purchaseOrderId,
  supplierName,
  open,
  onOpenChange,
}: {
  purchaseOrderId: string;
  supplierName?: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const assess = useAssessDelivery();
  const [quality, setQuality] = useState<number | null>(null);
  const [professionalism, setProfessionalism] = useState<number | null>(null);
  const [again, setAgain] = useState<boolean | null>(null);
  const [notes, setNotes] = useState("");

  const submit = async () => {
    try {
      await assess.mutateAsync({
        poId: purchaseOrderId,
        data: {
          quality,
          professionalism,
          would_use_again: again,
          notes: notes || null,
        },
      });
      await queryClient.invalidateQueries();
      onOpenChange(false);
      toast.success("Assessment recorded");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>How did {supplierName ?? "this supplier"} do?</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <Picker label="Quality of what arrived" value={quality} onChange={setQuality} />
          <Picker
            label="Professionalism"
            value={professionalism}
            onChange={setProfessionalism}
          />

          <div className="space-y-1.5">
            <Label>Would you use them again?</Label>
            <div className="flex gap-2">
              <Button
                variant={again === true ? "default" : "outline"}
                size="sm"
                onClick={() => setAgain(again === true ? null : true)}
              >
                <ThumbsUp /> Yes
              </Button>
              <Button
                variant={again === false ? "default" : "outline"}
                size="sm"
                onClick={() => setAgain(again === false ? null : false)}
              >
                <Warning /> No
              </Button>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="assess-notes">Anything worth remembering</Label>
            <Textarea
              id="assess-notes"
              rows={2}
              placeholder="Short delivery, driver sorted it the same afternoon"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
            Leave anything blank you have no view on. A blank is kept apart from a middling
            score rather than averaged in as one. Whether they were late and what they charged
            is already known — this is the part only you saw.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={
              assess.isPending ||
              (quality == null && professionalism == null && again == null)
            }
            onClick={() => void submit()}
          >
            Record
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Picker({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <div className="flex gap-1.5">
        {[1, 2, 3, 4, 5].map((score) => (
          <Button
            key={score}
            variant={value === score ? "default" : "outline"}
            size="icon"
            aria-label={`${label}: ${score}`}
            // Clicking the same score again clears it, so a misclick does not
            // become a permanent opinion.
            onClick={() => onChange(value === score ? null : score)}
          >
            {score}
          </Button>
        ))}
        <Button
          variant="ghost"
          size="sm"
          className="ml-1 text-xs text-muted-foreground"
          onClick={() => onChange(null)}
        >
          <Star /> No view
        </Button>
      </div>
    </div>
  );
}
