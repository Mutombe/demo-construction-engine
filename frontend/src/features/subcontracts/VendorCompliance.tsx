import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle, Plus, Trash, WarningCircle } from "@phosphor-icons/react";
import { useState } from "react";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { confirmDialog } from "@/components/ui/confirm";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
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
  useAddDocument,
  useGetCompliance,
  useRemoveDocument,
  useSetStatus,
} from "@/lib/api/generated/endpoints";
import type { ComplianceDocType, ComplianceItem, VendorStatus } from "@/lib/api/generated/model";
import { fmtDate } from "@/lib/format";
import { toast } from "@/lib/toast";

const DOC_LABELS: Record<string, string> = {
  tax_clearance: "Tax Clearance",
  vat_registration: "VAT Registration",
  company_registration: "Company Registration",
  public_liability: "Public Liability",
  workmans_compensation: "Workman's Compensation",
  safety_certificate: "Safety Certificate",
  bank_confirmation: "Bank Confirmation",
  trade_licence: "Trade Licence",
  other: "Other",
};

const VENDOR_STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  approved: "Approved",
  suspended: "Suspended",
  blacklisted: "Blacklisted",
};

function stateBadge(item: ComplianceItem) {
  const days = item.days_to_expiry;
  switch (item.state) {
    case "valid":
      return <Badge variant="success">In date</Badge>;
    case "expiring":
      return <Badge variant="warning">{days === 0 ? "Expires today" : `${days} days left`}</Badge>;
    case "expired":
      return <Badge variant="destructive">Expired</Badge>;
    default:
      return <Badge variant="outline">Never supplied</Badge>;
  }
}

/** What a vendor is actually allowed to be awarded, and why not.
 *
 *  Approval and paperwork are shown separately because they are separate:
 *  an approved vendor whose insurance lapsed is still blocked, and the
 *  panel has to make that legible rather than showing one merged verdict. */
export function VendorCompliance({ supplierId }: { supplierId: string }) {
  const queryClient = useQueryClient();
  const { data: compliance } = useGetCompliance(supplierId);
  const setStatus = useSetStatus();
  const removeDoc = useRemoveDocument();
  const [addOpen, setAddOpen] = useState(false);

  if (!compliance) return null;

  const changeStatus = async (vendor_status: string) => {
    try {
      await setStatus.mutateAsync({
        supplierId,
        data: { vendor_status: vendor_status as VendorStatus },
      });
      await queryClient.invalidateQueries();
      toast.success("Vendor status updated");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const drop = async (item: ComplianceItem) => {
    const ok = await confirmDialog({
      title: `Remove the ${DOC_LABELS[item.doc_type] ?? item.doc_type}?`,
      message: "The vendor goes back to having never supplied it.",
      confirmLabel: "Remove",
      tone: "danger",
    });
    if (!ok) return;
    try {
      await removeDoc.mutateAsync({ documentId: item.document_id as string });
      await queryClient.invalidateQueries();
      toast.success("Document removed");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="text-base">Compliance</CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Checked again every time a subcontract is awarded.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Can perm="procurement:write">
            <Select
              aria-label="Vendor status"
              value={compliance.vendor_status}
              onChange={(e) => void changeStatus(e.target.value)}
              className="h-8 w-36"
            >
              {Object.entries(VENDOR_STATUS_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
            <Button variant="outline" size="sm" onClick={() => setAddOpen(true)}>
              <Plus /> Document
            </Button>
          </Can>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {compliance.is_compliant ? (
          <div className="flex items-center gap-2 rounded-md border border-success/30 bg-success/5 px-3 py-2 text-sm text-success">
            <CheckCircle weight="fill" className="h-4 w-4 shrink-0" />
            Every mandatory document is in date. This vendor can be awarded work.
          </div>
        ) : (
          <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            <WarningCircle weight="fill" className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              Cannot be awarded a subcontract:{" "}
              {(compliance.blocking ?? []).map((d) => DOC_LABELS[d] ?? d).join(", ")}.
            </span>
          </div>
        )}

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Document</TableHead>
              <TableHead>Reference</TableHead>
              <TableHead>Expires</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {(compliance.documents ?? []).map((item) => (
              <TableRow key={item.doc_type}>
                <TableCell className="font-medium">
                  {DOC_LABELS[item.doc_type] ?? item.doc_type}
                  {!item.is_mandatory && (
                    <span className="ml-1.5 text-xs font-normal text-muted-foreground">
                      optional
                    </span>
                  )}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {item.reference ?? "—"}
                </TableCell>
                <TableCell className="text-sm">
                  {item.expires_on ? fmtDate(item.expires_on) : item.state === "valid" ? (
                    <span className="text-muted-foreground">Does not expire</span>
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell>{stateBadge(item)}</TableCell>
                <TableCell>
                  {item.document_id && (
                    <Can perm="procurement:write">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label="Remove document"
                        onClick={() => void drop(item)}
                      >
                        <Trash />
                      </Button>
                    </Can>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>

      <AddDocumentDialog supplierId={supplierId} open={addOpen} onOpenChange={setAddOpen} />
    </Card>
  );
}

function AddDocumentDialog({
  supplierId,
  open,
  onOpenChange,
}: {
  supplierId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const add = useAddDocument();
  const [form, setForm] = useState({
    doc_type: "tax_clearance",
    reference: "",
    issued_on: "",
    expires_on: "",
  });

  const submit = async () => {
    try {
      await add.mutateAsync({
        supplierId,
        data: {
          doc_type: form.doc_type as ComplianceDocType,
          reference: form.reference || null,
          issued_on: form.issued_on || null,
          expires_on: form.expires_on || null,
        },
      });
      await queryClient.invalidateQueries();
      setForm({ doc_type: "tax_clearance", reference: "", issued_on: "", expires_on: "" });
      onOpenChange(false);
      toast.success("Document recorded");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Record a document</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="doc-type">Document</Label>
            <Select
              id="doc-type"
              value={form.doc_type}
              onChange={(e) => setForm({ ...form, doc_type: e.target.value })}
            >
              {Object.entries(DOC_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="doc-ref">Reference</Label>
            <Input
              id="doc-ref"
              value={form.reference}
              onChange={(e) => setForm({ ...form, reference: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="issued">Issued</Label>
            <Input
              id="issued"
              type="date"
              value={form.issued_on}
              onChange={(e) => setForm({ ...form, issued_on: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="expires">Expires</Label>
            <Input
              id="expires"
              type="date"
              value={form.expires_on}
              onChange={(e) => setForm({ ...form, expires_on: e.target.value })}
            />
            <p className="text-xs text-muted-foreground">
              Leave blank for something that does not expire, like a company registration.
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={add.isPending} onClick={() => void submit()}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
