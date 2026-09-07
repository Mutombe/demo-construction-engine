import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { useGetLeaderboard } from "@/lib/api/generated/endpoints";

export interface Reputation {
  supplier_id: string;
  overall?: string | number | null;
  quality?: string | number | null;
  delivery?: string | number | null;
  on_time_pct?: string | number | null;
  avg_above_lowest_pct?: string | number | null;
  assessments?: number;
  provisional?: boolean;
}

/** Every supplier's record in one request, keyed for a list to read.
 *
 *  Fetched once for the whole table rather than per row: a rating badge on
 *  forty suppliers should not be forty requests. */
export function useReputations(): Map<string, Reputation> {
  const { data } = useGetLeaderboard();
  return new Map((data ?? []).map((row) => [row.supplier_id, row as Reputation]));
}

function toneFor(score: number) {
  if (score >= 4) return "success" as const;
  if (score >= 3) return "warning" as const;
  return "destructive" as const;
}

function wordFor(score: number) {
  if (score >= 4.5) return "Excellent";
  if (score >= 4) return "Good";
  if (score >= 3) return "Mixed";
  if (score >= 2) return "Poor";
  return "Bad";
}

/** A supplier's standing, short enough to sit in a table cell or an option.
 *
 *  Never traded with is drawn differently from badly rated, because they are
 *  different facts and treating an unknown as a warning would push people away
 *  from anyone new. */
export function ReputationTag({
  reputation,
  showDetail = true,
}: {
  reputation?: Reputation;
  showDetail?: boolean;
}) {
  if (!reputation) {
    return (
      <Tooltip content="Never traded with. Not a mark against them — there is simply no history yet.">
        <Badge variant="outline">New</Badge>
      </Tooltip>
    );
  }

  const overall = reputation.overall == null ? null : Number(reputation.overall);
  const onTime =
    reputation.on_time_pct == null ? null : Number(reputation.on_time_pct);
  const above =
    reputation.avg_above_lowest_pct == null
      ? null
      : Number(reputation.avg_above_lowest_pct);

  const detail = [
    onTime != null ? `${onTime.toFixed(0)}% on time` : null,
    above != null ? `${above.toFixed(1)}% over the cheapest bid` : null,
    reputation.assessments ? `${reputation.assessments} judged` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  if (overall == null) {
    // Some history, but not enough of it to put a single number on.
    return (
      <Tooltip
        content={
          detail
            ? `Not enough to score overall. ${detail}`
            : "Traded with, but nothing judged yet."
        }
      >
        <Badge variant="outline">Unrated</Badge>
      </Tooltip>
    );
  }

  return (
    <Tooltip content={detail || "Rated across quality, price, delivery and professionalism."}>
      <span className="inline-flex items-center gap-1.5">
        <Badge variant={toneFor(overall)}>
          {wordFor(overall)} {overall.toFixed(1)}
        </Badge>
        {showDetail && reputation.provisional && (
          <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
            provisional
          </span>
        )}
      </span>
    </Tooltip>
  );
}

/** The same standing, compressed to something that survives inside an
 *  `<option>` — which can carry no markup at all. */
export function reputationLabel(reputation?: Reputation): string {
  if (!reputation) return "new";
  const overall = reputation.overall == null ? null : Number(reputation.overall);
  if (overall == null) return "unrated";
  const onTime = reputation.on_time_pct == null ? null : Number(reputation.on_time_pct);
  const parts = [`${wordFor(overall).toLowerCase()} ${overall.toFixed(1)}`];
  if (onTime != null) parts.push(`${onTime.toFixed(0)}% on time`);
  return parts.join(", ");
}
