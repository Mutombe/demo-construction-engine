import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Handshake, Plus, Trash } from "@phosphor-icons/react";
import { useState } from "react";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { StatCard } from "@/components/ui/stat-card";
import { Textarea } from "@/components/ui/textarea";
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
  useAwardSubcontract,
  useCertifyMilestone,
  useCreateSubcontract,
  useGetSubcontract,
  useListSubcontracts,
  useListSuppliers,
  useRejectMilestone,
  useSubmitMilestone,
} from "@/lib/api/generated/endpoints";
import type { MilestoneRead, SubcontractRead } from "@/lib/api/generated/model";
import { fmtDate, money, moneyExact } from "@/lib/format";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/_app/projects/$projectId/subcontracts")({
  component: ProjectSubcontracts,
});

const STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "outline"> = {
  awarded: "success",
  draft: "outline",
  completed: "outline",
  terminated: "destructive",
};

function ProjectSubcontracts() {
  const { projectId } = Route.useParams();
  const { data: contracts } = useListSubcontracts(projectId);
  const [createOpen, setCreateOpen] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);

  const rows = contracts ?? [];
  const committed = rows.reduce((sum, c) => sum + Number(c.value), 0);
  const live = rows.filter((c) => c.status === "awarded").length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Subcontracts</h2>
          <p className="text-sm text-muted-foreground">
            Work packaged out to other firms, and what has been signed off against each.
          </p>
        </div>
        <Can perm="procurement:write">
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus /> New Package
          </Button>
        </Can>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard label="Packages" value={rows.length} icon={<Handshake />} />
        <StatCard label="Live" value={live} sub="awarded and running" />
        <StatCard label="Committed" value={money(committed)} tone="brand" />
      </div>

      <Card>
        <CardContent className="p-0">
          {rows.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Number</TableHead>
                  <TableHead>Package</TableHead>
                  <TableHead>Subcontractor</TableHead>
                  <TableHead className="text-right">Value</TableHead>
                  <TableHead className="text-right">Retention</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((contract: SubcontractRead) => (
                  <TableRow
                    key={contract.id}
                    className="cursor-pointer"
                    onClick={() => setOpenId(contract.id)}
                  >
                    <TableCell className="font-mono text-xs">{contract.doc_number}</TableCell>
                    <TableCell className="font-medium">{contract.title}</TableCell>
                    <TableCell className="text-sm">{contract.supplier_name ?? "—"}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {moneyExact(contract.value)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {Number(contract.retention_pct)}%
                    </TableCell>
                    <TableCell>
                      <Badge variant={STATUS_VARIANT[contract.status] ?? "outline"}>
                        {contract.status}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <EmptyState
              icon={<Handshake />}
              title="No packages let"
              hint="Everything on this job is being done in-house."
            />
          )}
        </CardContent>
      </Card>

      <CreateDialog projectId={projectId} open={createOpen} onOpenChange={setCreateOpen} />
      {openId && (
        <SubcontractDialog
          subcontractId={openId}
          open={!!openId}
          onOpenChange={(open) => !open && setOpenId(null)}
        />
      )}
    </div>
  );
}

/** The package itself: what is owed, what is held, and what is left to do.
 *
 *  Certified, retention and net are shown side by side because a
 *  subcontractor who reads only "certified" and gets paid the net will
 *  otherwise call about the difference every single month. */
function SubcontractDialog({
  subcontractId,
  open,
  onOpenChange,
}: {
  subcontractId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const { data: contract } = useGetSubcontract(subcontractId);
  const award = useAwardSubcontract();
  const submit = useSubmitMilestone();
  const certify = useCertifyMilestone();
  const reject = useRejectMilestone();
  const [rejecting, setRejecting] = useState<MilestoneRead | null>(null);
  const [reason, setReason] = useState("");

  const run = async (fn: () => Promise<unknown>, done: string) => {
    try {
      await fn();
      await queryClient.invalidateQueries();
      toast.success(done);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>
            {contract ? `${contract.doc_number} · ${contract.title}` : "Subcontract"}
          </DialogTitle>
        </DialogHeader>

        {contract && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Figure label="Value" value={moneyExact(contract.value)} />
              <Figure label="Certified" value={moneyExact(contract.certified)} />
              <Figure
                label="Retention held"
                value={moneyExact(contract.retention_held)}
                hint={`${Number(contract.retention_pct)}% of each stage`}
              />
              <Figure label="Net payable" value={moneyExact(contract.net_payable)} />
            </div>

            {contract.status === "draft" && (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-sm">
                <span className="text-warning">
                  Not awarded yet. Awarding checks the subcontractor's paperwork and refuses if
                  anything mandatory has lapsed.
                </span>
                <Can perm="procurement:write">
                  <Button
                    size="sm"
                    onClick={() =>
                      void run(
                        () => award.mutateAsync({ subcontractId }),
                        "Awarded",
                      )
                    }
                  >
                    Award
                  </Button>
                </Can>
              </div>
            )}

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Stage</TableHead>
                  <TableHead>Due</TableHead>
                  <TableHead className="text-right">Priced at</TableHead>
                  <TableHead className="text-right">Certified</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-40" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(contract.milestones ?? []).map((milestone) => (
                  <TableRow key={milestone.id}>
                    <TableCell className="font-medium">{milestone.name}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {milestone.due_date ? fmtDate(milestone.due_date) : "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {moneyExact(milestone.value)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {milestone.certified_amount ? moneyExact(milestone.certified_amount) : "—"}
                    </TableCell>
                    <TableCell>
                      <MilestoneBadge milestone={milestone} />
                    </TableCell>
                    <TableCell className="text-right">
                      {contract.status === "awarded" && milestone.status === "pending" && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            void run(
                              () => submit.mutateAsync({ milestoneId: milestone.id }),
                              "Sent for certification",
                            )
                          }
                        >
                          Claim
                        </Button>
                      )}
                      {contract.status === "awarded" && milestone.status === "submitted" && (
                        <Can perm="project:write">
                          <div className="flex justify-end gap-1.5">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                setRejecting(milestone);
                                setReason("");
                              }}
                            >
                              Reject
                            </Button>
                            <Button
                              size="sm"
                              onClick={() =>
                                void run(
                                  () =>
                                    certify.mutateAsync({
                                      milestoneId: milestone.id,
                                      data: {},
                                    }),
                                  "Certified",
                                )
                              }
                            >
                              Certify
                            </Button>
                          </div>
                        </Can>
                      )}
                      {milestone.status === "rejected" && milestone.rejection_reason && (
                        <span className="text-xs text-muted-foreground">
                          {milestone.rejection_reason}
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {rejecting && (
              <div className="space-y-2 rounded-md border p-3">
                <Label htmlFor="reject-reason">
                  Why {rejecting.name} is going back
                </Label>
                <Textarea
                  id="reject-reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="What has to be put right before this stage can be signed off"
                />
                <div className="flex justify-end gap-2">
                  <Button variant="outline" size="sm" onClick={() => setRejecting(null)}>
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    disabled={!reason.trim()}
                    onClick={() =>
                      void run(async () => {
                        await reject.mutateAsync({
                          milestoneId: rejecting.id,
                          data: { reason },
                        });
                        setRejecting(null);
                      }, "Sent back")
                    }
                  >
                    Send Back
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function MilestoneBadge({ milestone }: { milestone: MilestoneRead }) {
  switch (milestone.status) {
    case "certified":
      return <Badge variant="success">Certified {fmtDate(milestone.certified_on ?? null)}</Badge>;
    case "submitted":
      return <Badge variant="warning">Awaiting sign-off</Badge>;
    case "rejected":
      return <Badge variant="destructive">Sent back</Badge>;
    default:
      return <Badge variant="outline">Not started</Badge>;
  }
}

function Figure({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-md border p-3">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-lg font-semibold tabular-nums">{value}</div>
      {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}

interface StageDraft {
  name: string;
  value: string;
  due_date: string;
}

function CreateDialog({
  projectId,
  open,
  onOpenChange,
}: {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const create = useCreateSubcontract();
  const { data: suppliers } = useListSuppliers({ page: 1, page_size: 200 });
  const [form, setForm] = useState({
    supplier_id: "",
    title: "",
    scope: "",
    retention_pct: "10",
    starts_on: "",
    ends_on: "",
  });
  const [stages, setStages] = useState<StageDraft[]>([{ name: "", value: "", due_date: "" }]);

  const filled = stages.filter((s) => s.name.trim() && Number(s.value) > 0);
  const total = filled.reduce((sum, s) => sum + Number(s.value), 0);

  const submit = async () => {
    try {
      await create.mutateAsync({
        projectId,
        data: {
          supplier_id: form.supplier_id,
          title: form.title,
          scope: form.scope || null,
          value: String(total),
          retention_pct: form.retention_pct || "0",
          starts_on: form.starts_on || null,
          ends_on: form.ends_on || null,
          milestones: filled.map((s) => ({
            name: s.name,
            value: s.value,
            due_date: s.due_date || null,
          })),
        },
      });
      await queryClient.invalidateQueries();
      onOpenChange(false);
      setForm({
        supplier_id: "",
        title: "",
        scope: "",
        retention_pct: "10",
        starts_on: "",
        ends_on: "",
      });
      setStages([{ name: "", value: "", due_date: "" }]);
      toast.success("Package created");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const setStage = (index: number, patch: Partial<StageDraft>) =>
    setStages((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>New subcontract package</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="sc-supplier">Subcontractor</Label>
            <Select
              id="sc-supplier"
              value={form.supplier_id}
              onChange={(e) => setForm({ ...form, supplier_id: e.target.value })}
            >
              <option value="">Choose a subcontractor</option>
              {suppliers?.items.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="sc-title">Package</Label>
            <Input
              id="sc-title"
              placeholder="Electrical first fix"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="sc-scope">Scope</Label>
            <Textarea
              id="sc-scope"
              value={form.scope}
              onChange={(e) => setForm({ ...form, scope: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sc-retention">Retention %</Label>
            <Input
              id="sc-retention"
              inputMode="decimal"
              value={form.retention_pct}
              onChange={(e) => setForm({ ...form, retention_pct: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="sc-start">Starts</Label>
              <Input
                id="sc-start"
                type="date"
                value={form.starts_on}
                onChange={(e) => setForm({ ...form, starts_on: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sc-end">Ends</Label>
              <Input
                id="sc-end"
                type="date"
                value={form.ends_on}
                onChange={(e) => setForm({ ...form, ends_on: e.target.value })}
              />
            </div>
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>Stages</Label>
            <span className="text-sm tabular-nums text-muted-foreground">
              {moneyExact(total)} total
            </span>
          </div>
          {stages.map((stage, index) => (
            <div key={index} className="flex gap-2">
              <Input
                aria-label="Stage name"
                placeholder="Stage"
                value={stage.name}
                onChange={(e) => setStage(index, { name: e.target.value })}
              />
              <Input
                aria-label="Stage value"
                placeholder="Value"
                inputMode="decimal"
                className="w-32"
                value={stage.value}
                onChange={(e) => setStage(index, { value: e.target.value })}
              />
              <Input
                aria-label="Stage due date"
                type="date"
                className="w-40"
                value={stage.due_date}
                onChange={(e) => setStage(index, { due_date: e.target.value })}
              />
              <Button
                variant="ghost"
                size="icon"
                aria-label="Remove stage"
                disabled={stages.length === 1}
                onClick={() => setStages((rows) => rows.filter((_, i) => i !== index))}
              >
                <Trash />
              </Button>
            </div>
          ))}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setStages((rows) => [...rows, { name: "", value: "", due_date: "" }])}
          >
            <Plus /> Stage
          </Button>
          <p className="text-xs text-muted-foreground">
            The package is worth the sum of its stages, so nothing can be certified that was
            never priced.
          </p>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!form.supplier_id || !form.title || !filled.length || create.isPending}
            onClick={() => void submit()}
          >
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
