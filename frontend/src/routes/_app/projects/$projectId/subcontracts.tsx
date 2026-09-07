import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
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
import { ErrorState } from "@/components/ui/list-state";
import { TableSkeleton } from "@/components/ui/skeleton";
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
  useCreateSubcontract,
  useListSubcontracts,
  useListSuppliers,
} from "@/lib/api/generated/endpoints";
import type { SubcontractRead } from "@/lib/api/generated/model";
import { money, moneyExact } from "@/lib/format";
import { toast } from "@/lib/toast";
import { reputationLabel, useReputations } from "@/features/procurement/ReputationTag";

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
  const query = useListSubcontracts(projectId);
  const { data: contracts, isLoading } = query;
  const [createOpen, setCreateOpen] = useState(false);

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
          {query.isError ? (
            <ErrorState error={query.error} onRetry={() => void query.refetch()} />
          ) : isLoading && !contracts ? (
            <TableSkeleton columns={6} />
          ) : rows.length ? (
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
                  <TableRow key={contract.id}>
                    <TableCell className="font-mono text-xs">
                      <Link
                        to="/subcontracts/$subcontractId"
                        params={{ subcontractId: contract.id }}
                        className="hover:underline"
                      >
                        {contract.doc_number}
                      </Link>
                    </TableCell>
                    <TableCell className="font-medium">
                      <Link
                        to="/subcontracts/$subcontractId"
                        params={{ subcontractId: contract.id }}
                        className="hover:underline"
                      >
                        {contract.title}
                      </Link>
                    </TableCell>
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
  const reputations = useReputations();
  const { data: suppliers } = useListSuppliers({ page: 1, page_size: 200 });
  const [form, setForm] = useState({
    supplier_id: "",
    title: "",
    scope: "",
    retention_pct: "10",
    withholding_pct: "0",
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
          withholding_pct: form.withholding_pct || "0",
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
        withholding_pct: "0",
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
                  {/* An option carries no markup, so the standing rides
                      in the text rather than as a badge. */}
                  {s.name} — {reputationLabel(reputations.get(s.id))}
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
          <div className="space-y-1.5">
            <Label htmlFor="sc-withholding">Withholding tax %</Label>
            <Input
              id="sc-withholding"
              inputMode="decimal"
              value={form.withholding_pct}
              onChange={(e) => setForm({ ...form, withholding_pct: e.target.value })}
            />
            <p className="text-xs text-muted-foreground">
              Zero where they hold a valid tax clearance — which is a decision to record, not
              one to leave blank and hope.
            </p>
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
