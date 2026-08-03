import { useQueryClient } from "@tanstack/react-query";
import { Check } from "@phosphor-icons/react";
import { ClaudeIcon } from "@/components/ui/claude-icon";
import { useState } from "react";
import { toast } from "@/lib/toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { confirmDialog } from "@/components/ui/confirm";
import { RichMarkdown } from "@/components/ui/markdown";
import { Can } from "@/components/layout/Can";
import { useAiStatus } from "@/features/ai/useAiStatus";
import { useAcceptQuote, useCompareQuotes } from "@/lib/api/generated/endpoints";
import type { QuoteComparisonResponse, RfqDetail } from "@/lib/api/generated/model";
import { moneyExact } from "@/lib/format";
import { cn } from "@/lib/utils";

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

export function QuoteCompare({
  rfq,
  onAccepted,
}: {
  rfq: RfqDetail;
  onAccepted?: (quoteId: string) => void;
}) {
  const queryClient = useQueryClient();
  const { aiAvailable } = useAiStatus();
  const compareMutation = useCompareQuotes();
  const acceptMutation = useAcceptQuote();
  const [result, setResult] = useState<QuoteComparisonResponse | null>(null);

  const analyze = async () => {
    try {
      setResult(await compareMutation.mutateAsync({ rfqId: rfq.id }));
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const accept = async (quoteId: string) => {
    if (
      !(await confirmDialog({
        title: "Accept quote",
        message:
          "Accept this quote? All other quotes on this RFQ will be rejected and the RFQ closed.",
      }))
    )
      return;
    try {
      await acceptMutation.mutateAsync({ quoteId });
      await queryClient.invalidateQueries();
      toast.success("Quote accepted");
      onAccepted?.(quoteId);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const matrix = result?.matrix;
  const analysis = result?.analysis;
  const recommendedQuoteId = analysis
    ? matrix?.suppliers.find((s) => s.supplier_id === analysis.recommendation.supplier_id)
        ?.quote_id
    : undefined;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>Compare Quotes</CardTitle>
        <Button
          size="sm"
          disabled={!aiAvailable || compareMutation.isPending}
          title={aiAvailable ? undefined : "AI not configured — add ANTHROPIC_API_KEY"}
          onClick={() => void analyze()}
        >
          <ClaudeIcon className="h-3.5 w-3.5" />
          {compareMutation.isPending ? "Analyzing…" : "Analyze & Recommend"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {!matrix && (
          <p className="text-sm text-muted-foreground">
            Run the analysis to see a line-by-line price matrix and Claude's recommendation.
          </p>
        )}

        {matrix && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="px-2 py-2 text-left">Line</th>
                  {matrix.suppliers.map((s) => (
                    <th key={s.quote_id} className="px-2 py-2 text-right">
                      {s.supplier_name}
                      {String(s.quote_id) === String(recommendedQuoteId) && (
                        <Badge variant="success" className="ml-1.5">
                          AI Pick
                        </Badge>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {matrix.rows.map((row) => (
                  <tr key={row.rfq_item_id} className="border-b">
                    <td className="px-2 py-1.5">
                      <div className="max-w-64 truncate">{row.description}</div>
                      <div className="text-xs text-muted-foreground">
                        {Number(row.quantity).toLocaleString()} {row.unit}
                      </div>
                    </td>
                    {matrix.suppliers.map((s) => {
                      const cell = row.cells[String(s.quote_id)];
                      return (
                        <td
                          key={s.quote_id}
                          className={cn(
                            "px-2 py-1.5 text-right tabular-nums",
                            cell?.is_cheapest && "font-semibold text-success",
                          )}
                        >
                          {cell?.unit_price != null ? (
                            <>
                              {moneyExact(cell.unit_price)}
                              {(cell.unit_mismatch || cell.quantity_mismatch) && (
                                <span
                                  className="ml-1 text-warning"
                                  title="Unit or quantity differs from the RFQ"
                                >
                                  ⚠
                                </span>
                              )}
                            </>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
                <tr className="border-b bg-secondary/40 text-xs">
                  <td className="px-2 py-1.5 font-medium">Coverage of RFQ Lines</td>
                  {matrix.suppliers.map((s) => (
                    <td key={s.quote_id} className="px-2 py-1.5 text-right">
                      {s.coverage_pct}%
                    </td>
                  ))}
                </tr>
                <tr className="border-b text-xs">
                  <td className="px-2 py-1.5 font-medium">Comparable Basis Total</td>
                  {matrix.suppliers.map((s) => (
                    <td key={s.quote_id} className="px-2 py-1.5 text-right tabular-nums">
                      {moneyExact(s.comparable_total)}
                    </td>
                  ))}
                </tr>
                <tr className="font-semibold">
                  <td className="px-2 py-2">Quoted Total</td>
                  {matrix.suppliers.map((s) => (
                    <td key={s.quote_id} className="px-2 py-2 text-right tabular-nums">
                      {moneyExact(s.total_amount)}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td />
                  {matrix.suppliers.map((s) => (
                    <td key={s.quote_id} className="px-2 py-1.5 text-right">
                      {s.status === "received" && rfq.status === "issued" && (
                        <Can perm="po:approve">
                          <Button
                            size="sm"
                            variant={
                              String(s.quote_id) === String(recommendedQuoteId)
                                ? "default"
                                : "outline"
                            }
                            disabled={acceptMutation.isPending}
                            onClick={() => void accept(String(s.quote_id))}
                          >
                            <Check className="h-3.5 w-3.5" /> Accept
                          </Button>
                        </Can>
                      )}
                      {s.status === "accepted" && <Badge variant="success">Accepted</Badge>}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {analysis && (
          <div className="space-y-3 rounded-md border bg-secondary/30 p-4">
            <RichMarkdown content={analysis.summary} variant="chat" />
            {analysis.risk_flags.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {analysis.risk_flags.map((flag, i) => (
                  <Badge key={i} variant="warning">
                    {flag}
                  </Badge>
                ))}
              </div>
            )}
            <div className="rounded-md border bg-card p-3">
              <div className="mb-1 flex items-center gap-2 text-sm font-semibold">
                <ClaudeIcon className="h-4 w-4 text-claude" />
                Recommendation: {analysis.recommendation.supplier_name}
              </div>
              <RichMarkdown
                content={analysis.recommendation.reasoning}
                variant="chat"
                className="text-muted-foreground"
              />
            </div>
            {analysis.line_analysis.length > 0 && (
              <ul className="space-y-1 text-xs text-muted-foreground">
                {analysis.line_analysis.map((finding, i) => (
                  <li key={i}>• {finding.note}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
