import { CaretDown, CaretRight, HandCoins } from "@phosphor-icons/react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Tooltip } from "@/components/ui/tooltip";
import type { Ageing as AgeingPayload } from "@/lib/api/generated/model";
import { fmtDate, moneyExact } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Fixed order: a bucket table read out of sequence is useless, and the
 *  object's key order is not something to rely on. */
const ORDER = ["Current", "31 to 60 days", "61 to 90 days", "Over 90 days"] as const;

const TONE: Record<string, string> = {
  Current: "text-foreground",
  "31 to 60 days": "text-foreground",
  "61 to 90 days": "text-warning",
  "Over 90 days": "text-destructive",
};

export function Ageing({
  data,
  emptyHint,
  onPay,
}: {
  data?: AgeingPayload;
  emptyHint: string;
  onPay?: (partyId: string, partyName: string) => void;
}) {
  const [open, setOpen] = useState<string | null>(null);

  if (!data) return <div className="h-64 animate-pulse rounded-lg border bg-muted/40" />;

  if (data.parties.length === 0) {
    return (
      <Card>
        <CardContent className="p-0">
          <EmptyState icon={<HandCoins />} title="Nothing outstanding" hint={emptyHint} />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-0">
        <table className="w-full text-sm">
          <thead className="border-b bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-4 py-2 text-left font-medium">Who</th>
              {ORDER.map((bucket) => (
                <th key={bucket} className="px-3 py-2 text-right font-medium">
                  {bucket}
                </th>
              ))}
              <th className="px-4 py-2 text-right font-medium">Total</th>
              {onPay && <th className="w-20" />}
            </tr>
          </thead>
          <tbody>
            {data.parties.map((party) => {
              const expanded = open === party.party_id;
              return (
                <>
                  <tr
                    key={party.party_id}
                    className="cursor-pointer border-b transition-colors hover:bg-accent/40"
                    onClick={() => setOpen(expanded ? null : party.party_id)}
                  >
                    <td className="px-4 py-2 font-medium">
                      <span className="flex items-center gap-1.5">
                        {expanded ? (
                          <CaretDown className="size-3 shrink-0" />
                        ) : (
                          <CaretRight className="size-3 shrink-0" />
                        )}
                        {party.party_name}
                        <span className="text-xs font-normal text-muted-foreground">
                          {party.documents.length}
                        </span>
                      </span>
                    </td>
                    {ORDER.map((bucket) => {
                      const value = Number(party.buckets[bucket] ?? 0);
                      return (
                        <td
                          key={bucket}
                          className={cn(
                            "px-3 py-2 text-right tabular-nums",
                            value > 0 ? TONE[bucket] : "text-muted-foreground/40",
                          )}
                        >
                          {value > 0 ? moneyExact(value) : "—"}
                        </td>
                      );
                    })}
                    <td className="px-4 py-2 text-right font-semibold tabular-nums">
                      {moneyExact(party.total)}
                    </td>
                    {onPay && (
                      <td className="px-2 py-2 text-right">
                        <button
                          type="button"
                          className="rounded px-2 py-1 text-xs font-medium text-primary hover:bg-primary/10"
                          onClick={(e) => {
                            e.stopPropagation();
                            onPay(party.party_id, party.party_name);
                          }}
                        >
                          Pay
                        </button>
                      </td>
                    )}
                  </tr>
                  {expanded &&
                    party.documents.map((doc) => (
                      <tr key={doc.id} className="border-b bg-muted/20 text-xs">
                        <td className="py-1.5 pl-10 pr-4">
                          <span className="font-mono">{doc.doc_number}</span>
                          <span className="ml-2 text-muted-foreground">
                            {fmtDate(doc.dated)}
                          </span>
                        </td>
                        <td colSpan={4} className="px-3 py-1.5">
                          <Tooltip content={`${doc.days} days old`}>
                            <Badge
                              variant={
                                doc.bucket === "Over 90 days"
                                  ? "destructive"
                                  : doc.bucket === "61 to 90 days"
                                    ? "warning"
                                    : "secondary"
                              }
                            >
                              {doc.days}d
                            </Badge>
                          </Tooltip>
                          {Number(doc.outstanding) !== Number(doc.amount) && (
                            <span className="ml-2 text-muted-foreground">
                              part paid of {moneyExact(doc.amount)}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-1.5 text-right tabular-nums">
                          {moneyExact(doc.outstanding)}
                        </td>
                        {onPay && <td />}
                      </tr>
                    ))}
                </>
              );
            })}
            <tr className="border-t-2 font-semibold">
              <td className="px-4 py-2">Total outstanding</td>
              {ORDER.map((bucket) => (
                <td
                  key={bucket}
                  className={cn("px-3 py-2 text-right tabular-nums", TONE[bucket])}
                >
                  {moneyExact(data.buckets[bucket] ?? 0)}
                </td>
              ))}
              <td className="px-4 py-2 text-right tabular-nums">{moneyExact(data.total)}</td>
              {onPay && <td />}
            </tr>
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
