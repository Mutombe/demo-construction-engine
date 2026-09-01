import { useQueryClient } from "@tanstack/react-query";
import { Check, Plus, Receipt, ScalesIcon, X } from "@phosphor-icons/react";
import { useState } from "react";
import { Can } from "@/components/layout/Can";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { errDetail } from "@/lib/api/errors";
import {
  useApplyWithholding,
  useApproveVariation,
  useCreateVariation,
  useGetPaymentCertificate,
  useListBackCharges,
  useListVariations,
  useRaiseBackCharge,
  useRejectVariation,
} from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";
import { toast } from "@/lib/toast";

/** The certificate: how a claim becomes a payment, line by line.
 *
 *  Every deduction is named. A subcontractor paid a figure they cannot
 *  rebuild rings up every month, and they are right to. */
export function PaymentCertificate({ subcontractId }: { subcontractId: string }) {
  const queryClient = useQueryClient();
  const { data: cert } = useGetPaymentCertificate(subcontractId);
  const withhold = useApplyWithholding();

  if (!cert) return null;

  const applyTax = async () => {
    try {
      const result = await withhold.mutateAsync({ subcontractId, data: {} });
      await queryClient.invalidateQueries();
      toast.success(`${moneyExact(result.withheld)} withheld`);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <Receipt /> Payment certificate
          </CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            What they claimed, and every reason it is less.
          </p>
        </div>
        {Number(cert.withholding_pct) > 0 && (
          <Can perm="project:write">
            <Button variant="outline" size="sm" onClick={() => void applyTax()}>
              Withhold Tax
            </Button>
          </Can>
        )}
      </CardHeader>
      <CardContent className="space-y-1.5 text-sm">
        <Line label="Original package" value={cert.original_value} muted />
        {Number(cert.variations) !== 0 && (
          <Line label="Approved variations" value={cert.variations} muted />
        )}
        <Line label="Contract value" value={cert.contract_value} divider />

        <Line label="Certified to date" value={cert.certified} />
        <Line label="Less retention held" value={cert.retention_held} deduction />
        {Number(cert.back_charges) > 0 && (
          <Line label="Less back-charges" value={cert.back_charges} deduction />
        )}
        {Number(cert.withholding_tax) > 0 && (
          <Line
            label={`Less withholding tax at ${Number(cert.withholding_pct)}%`}
            value={cert.withholding_tax}
            deduction
          />
        )}
        <div className="flex items-baseline justify-between border-t pt-2">
          <span className="font-medium">Net payable</span>
          <span className="text-lg font-semibold tabular-nums">
            {moneyExact(cert.net_payable)}
          </span>
        </div>
        {Number(cert.withholding_pct) === 0 && (
          <p className="pt-1 text-xs text-muted-foreground">
            Withheld at zero. That is what a subcontractor holding a valid tax clearance is
            due — set a rate on the package if this one does not hold one.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function Line({
  label,
  value,
  muted,
  deduction,
  divider,
}: {
  label: string;
  value: string | number;
  muted?: boolean;
  /** Rendered with a minus sign in the destructive colour. Pass the amount
   *  itself; the sign is presentation, not data. */
  deduction?: boolean;
  divider?: boolean;
}) {
  const shown = moneyExact(value);
  return (
    <div
      className={
        divider
          ? "flex items-baseline justify-between border-b pb-1.5"
          : "flex items-baseline justify-between"
      }
    >
      <span className={muted ? "text-muted-foreground" : undefined}>{label}</span>
      <span
        className={
          deduction
            ? "tabular-nums text-destructive"
            : muted
              ? "tabular-nums text-muted-foreground"
              : "tabular-nums"
        }
      >
        {deduction ? `−${shown}` : shown}
      </span>
    </div>
  );
}

// --- Variations --------------------------------------------------------------

export function Variations({ subcontractId }: { subcontractId: string }) {
  const queryClient = useQueryClient();
  const { data: variations } = useListVariations(subcontractId);
  const approve = useApproveVariation();
  const reject = useRejectVariation();
  const [open, setOpen] = useState(false);

  const rows = variations ?? [];
  const pending = rows.filter((row) => row.status === "pending");

  const decide = async (id: string, agree: boolean) => {
    try {
      if (agree) await approve.mutateAsync({ variationId: id });
      else await reject.mutateAsync({ variationId: id });
      await queryClient.invalidateQueries();
      toast.success(agree ? "Variation approved" : "Variation rejected");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <ScalesIcon /> Variations
            {pending.length > 0 && <Badge variant="warning">{pending.length} pending</Badge>}
          </CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Instructed work. It does not move the package value until it is agreed.
          </p>
        </div>
        <Can perm="procurement:write">
          <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
            <Plus /> Instruct
          </Button>
        </Can>
      </CardHeader>
      <CardContent className="p-0">
        {rows.length ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Number</TableHead>
                <TableHead>Instruction</TableHead>
                <TableHead>Instructed</TableHead>
                <TableHead className="num">Value</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-28" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="font-mono text-xs">{row.doc_number}</TableCell>
                  <TableCell>
                    <div className="font-medium">{row.title}</div>
                    {row.instructed_by && (
                      <div className="text-xs text-muted-foreground">by {row.instructed_by}</div>
                    )}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {fmtDate(row.instructed_on)}
                  </TableCell>
                  <TableCell className="num">
                    <span className={Number(row.amount) < 0 ? "text-destructive" : undefined}>
                      {moneyExact(row.amount)}
                    </span>
                  </TableCell>
                  <TableCell>
                    {row.status === "approved" ? (
                      <Badge variant="success">In the value</Badge>
                    ) : row.status === "rejected" ? (
                      <Badge variant="outline">Rejected</Badge>
                    ) : (
                      <Badge variant="warning">Pending</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {row.status === "pending" && (
                      <Can perm="project:write">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label="Reject"
                            onClick={() => void decide(row.id, false)}
                          >
                            <X />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label="Approve"
                            onClick={() => void decide(row.id, true)}
                          >
                            <Check />
                          </Button>
                        </div>
                      </Can>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="px-4 py-6 text-center text-sm text-muted-foreground">
            Nothing instructed beyond the original scope.
          </p>
        )}
      </CardContent>

      <VariationDialog subcontractId={subcontractId} open={open} onOpenChange={setOpen} />
    </Card>
  );
}

function VariationDialog({
  subcontractId,
  open,
  onOpenChange,
}: {
  subcontractId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const create = useCreateVariation();
  const [form, setForm] = useState({
    title: "",
    description: "",
    amount: "",
    instructed_by: "",
    instructed_on: "",
  });

  const submit = async () => {
    try {
      await create.mutateAsync({
        subcontractId,
        data: {
          title: form.title,
          description: form.description || null,
          amount: form.amount,
          instructed_by: form.instructed_by || null,
          instructed_on: form.instructed_on || null,
        },
      });
      await queryClient.invalidateQueries();
      setForm({ title: "", description: "", amount: "", instructed_by: "", instructed_on: "" });
      onOpenChange(false);
      toast.success("Variation instructed");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Instruct a variation</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="v-title">What was instructed</Label>
            <Input
              id="v-title"
              placeholder="Extra ridge flashing to the north elevation"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="v-amount">Value</Label>
            <Input
              id="v-amount"
              inputMode="decimal"
              placeholder="8000"
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
            <p className="text-xs text-muted-foreground">
              Negative to omit work. Taking scope away is still an instruction.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="v-by">Instructed by</Label>
            <Input
              id="v-by"
              value={form.instructed_by}
              onChange={(e) => setForm({ ...form, instructed_by: e.target.value })}
            />
            <p className="text-xs text-muted-foreground">
              The question at the end is always who told them to.
            </p>
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="v-desc">Detail</Label>
            <Textarea
              id="v-desc"
              rows={2}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!form.title.trim() || !form.amount || create.isPending}
            onClick={() => void submit()}
          >
            Instruct
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Back-charges ------------------------------------------------------------

export function BackCharges({ subcontractId }: { subcontractId: string }) {
  const { data: charges } = useListBackCharges(subcontractId);
  const [open, setOpen] = useState(false);
  const rows = charges ?? [];

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="text-base">Back-charges</CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Their work somebody else had to put right, recovered from what they are owed.
          </p>
        </div>
        <Can perm="project:write">
          <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
            <Plus /> Raise
          </Button>
        </Can>
      </CardHeader>
      <CardContent className="p-0">
        {rows.length ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Number</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Raised</TableHead>
                <TableHead className="num">Amount</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="font-mono text-xs">{row.doc_number}</TableCell>
                  <TableCell className="text-sm">{row.reason}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {fmtDate(row.raised_on)}
                  </TableCell>
                  <TableCell className="num">{moneyExact(row.amount)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="px-4 py-6 text-center text-sm text-muted-foreground">
            Nothing charged back.
          </p>
        )}
      </CardContent>

      <BackChargeDialog subcontractId={subcontractId} open={open} onOpenChange={setOpen} />
    </Card>
  );
}

function BackChargeDialog({
  subcontractId,
  open,
  onOpenChange,
}: {
  subcontractId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const raise = useRaiseBackCharge();
  const [form, setForm] = useState({ reason: "", amount: "" });

  const submit = async () => {
    try {
      await raise.mutateAsync({
        subcontractId,
        data: { reason: form.reason, amount: form.amount },
      });
      await queryClient.invalidateQueries();
      setForm({ reason: "", amount: "" });
      onOpenChange(false);
      toast.success("Back-charge raised");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Raise a back-charge</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="bc-reason">What had to be put right</Label>
            <Textarea
              id="bc-reason"
              rows={2}
              placeholder="Blockwork damaged during installation, made good by others"
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bc-amount">Amount</Label>
            <Input
              id="bc-amount"
              inputMode="decimal"
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
          </div>
          <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
            This reduces what they are owed and gives the job back what it spent. It is not
            income — nothing was earned here, it was spent and recovered.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!form.reason.trim() || !form.amount || raise.isPending}
            onClick={() => void submit()}
          >
            Raise
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
