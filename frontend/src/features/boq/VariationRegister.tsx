import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle, ClipboardText, Prohibit } from "@phosphor-icons/react";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { confirmDialog } from "@/components/ui/confirm";
import { EmptyState } from "@/components/ui/empty-state";
import { EntityLink } from "@/components/ui/linked-row";
import { CardListSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { errDetail } from "@/lib/api/errors";
import {
  useDecideVariation,
  useGetVariationRegister,
} from "@/lib/api/generated/endpoints";
import type { VariationRow } from "@/lib/api/generated/model";
import { fmtDate, money, moneyExact } from "@/lib/format";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

const STATUS_VARIANT = {
  proposed: "warning",
  approved: "success",
  rejected: "outline",
} as const;

function Total({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "good" | "muted";
}) {
  return (
    <div className="rounded-md border p-3">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div
        className={cn(
          "mt-0.5 text-lg font-semibold tabular-nums",
          tone === "good" && "text-success",
          tone === "muted" && "text-muted-foreground",
        )}
      >
        {value}
      </div>
      {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}

/** Variations and omissions with their approval state. Only approved work
 *  moves the certifiable contract value, so the register is where a variation
 *  becomes money rather than a proposal. */
export function VariationRegister({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const { data, isLoading } = useGetVariationRegister(projectId);
  const decide = useDecideVariation();

  const act = async (row: VariationRow, status: "approved" | "rejected") => {
    const verb = status === "approved" ? "Approve" : "Reject";
    if (
      !(await confirmDialog({
        title: `${verb} ${row.variation_ref ?? row.item_code}`,
        message:
          status === "approved"
            ? `Approving adds ${moneyExact(row.amount)} to what can be certified on this contract.`
            : `Rejecting keeps ${moneyExact(row.amount)} out of the contract value.`,
        tone: status === "approved" ? "default" : "danger",
      }))
    )
      return;
    try {
      await decide.mutateAsync({ itemId: row.id, data: { status } });
      await queryClient.invalidateQueries({ queryKey: ["/api/v1/projects"] });
      toast.success(`${row.variation_ref ?? row.item_code} ${status}`);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  if (isLoading || !data) {
    return <CardListSkeleton count={3} />;
  }
  if (data.rows.length === 0) {
    return (
      <div className="rounded-lg border">
        <EmptyState
          icon={<ClipboardText />}
          title="No variations raised"
          hint="Extra or omitted scope added to the BOQ as a variation appears here for client approval before it can be certified."
        />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Total
          label="Approved additions"
          value={money(data.approved_additions)}
          tone="good"
          hint="certifiable"
        />
        <Total
          label="Approved omissions"
          value={money(data.approved_omissions)}
          hint="deducted from the contract"
        />
        <Total
          label="Awaiting approval"
          value={money(data.proposed_additions)}
          hint={
            Number(data.proposed_omissions) > 0
              ? `plus ${money(data.proposed_omissions)} of omissions`
              : "not yet certifiable"
          }
        />
        <Total
          label="Adjusted contract"
          value={money(data.effective_contract_value)}
          hint={`from ${money(data.contract_value)} original`}
        />
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Ref</TableHead>
                <TableHead>Item</TableHead>
                <TableHead>Description</TableHead>
                <TableHead className="text-right">Qty</TableHead>
                <TableHead className="text-right">Rate</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="font-mono text-xs">
                    {row.variation_ref ?? "—"}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    <EntityLink
                      to="/projects/$projectId/boq"
                      params={{ projectId }}
                      title="Open this line in the bill of quantities"
                    >
                      {row.section_code}·{row.item_code}
                    </EntityLink>
                  </TableCell>
                  <TableCell
                    className={cn(
                      "max-w-72 truncate",
                      row.item_type === "omission" && "line-through text-muted-foreground",
                    )}
                    title={row.description}
                  >
                    {row.description}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {Number(row.quantity).toLocaleString()} {row.unit}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {moneyExact(row.rate)}
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right font-medium tabular-nums",
                      row.item_type === "omission" && "text-destructive",
                    )}
                  >
                    {row.item_type === "omission" ? "− " : ""}
                    {moneyExact(row.amount)}
                  </TableCell>
                  <TableCell>
                    <Badge variant={STATUS_VARIANT[row.variation_status ?? "proposed"]}>
                      {row.variation_status}
                    </Badge>
                    {row.variation_approved_date && (
                      <div className="text-[10px] text-muted-foreground">
                        {fmtDate(row.variation_approved_date)}
                      </div>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Can perm="boq:write">
                        {row.variation_status !== "approved" && (
                          <Button
                            variant="outline"
                            size="sm"
                            title="Client approved this variation"
                            onClick={() => void act(row, "approved")}
                          >
                            <CheckCircle /> Approve
                          </Button>
                        )}
                        {row.variation_status !== "rejected" && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="text-destructive"
                            title="Reject"
                            onClick={() => void act(row, "rejected")}
                          >
                            <Prohibit />
                          </Button>
                        )}
                      </Can>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
