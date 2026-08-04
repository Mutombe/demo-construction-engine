import { keepPreviousData, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { CalendarPlus, HardHat, Money, PencilSimple, Plus } from "@phosphor-icons/react";
import { useState } from "react";
import { toast } from "@/lib/toast";
import { PageHeader } from "@/components/layout/AppShell";
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
import { ClickableRow, EntityLink, RowActions } from "@/components/ui/linked-row";
import { DEFAULT_PAGE_SIZE, PaginationBar } from "@/components/ui/pagination";
import { PageSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePermission } from "@/features/auth/hooks";
import { DayEntryDialog } from "@/features/payroll/DayEntryDialog";
import { WorkerFormDialog } from "@/features/payroll/WorkerFormDialog";
import {
  getGetPayRunQueryOptions,
  getGetWorkerQueryOptions,
  useCreatePayRun,
  useListPayRuns,
  useListTimesheets,
  useListWorkers,
} from "@/lib/api/generated/endpoints";
import type { WorkerRead } from "@/lib/api/generated/model";
import { isOptimistic } from "@/lib/api/optimistic";
import { fmtDate, moneyExact } from "@/lib/format";

export const Route = createFileRoute("/_app/payroll/")({
  component: PayrollPage,
});

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

function PayRunCreateDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const createMutation = useCreatePayRun();
  const today = new Date();
  const monday = new Date(today);
  monday.setDate(today.getDate() - ((today.getDay() + 6) % 7));
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);

  const [start, setStart] = useState(monday.toISOString().slice(0, 10));
  const [end, setEnd] = useState(sunday.toISOString().slice(0, 10));

  const save = async () => {
    try {
      const run = await createMutation.mutateAsync({
        data: { period_start: start, period_end: end },
      });
      await queryClient.invalidateQueries();
      toast.success(`${run.doc_number} drafted with ${run.line_count} workers`);
      onOpenChange(false);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>New Pay Run</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Period start</Label>
              <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Period end</Label>
              <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            All unpaid timesheets in the period are pulled in automatically. You can regenerate
            the draft before approving.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button disabled={createMutation.isPending} onClick={() => void save()}>
              {createMutation.isPending ? "Building…" : "Create Draft"}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function PayrollPage() {
  const canAdmin = usePermission("payroll:write");
  const [tab, setTab] = useState("timesheets");
  const [workerDialog, setWorkerDialog] = useState(false);
  const [editingWorker, setEditingWorker] = useState<WorkerRead | null>(null);
  const [dayDialog, setDayDialog] = useState(false);
  const [runDialog, setRunDialog] = useState(false);
  const [sheetsPage, setSheetsPage] = useState(1);
  const [workersPage, setWorkersPage] = useState(1);
  const [runsPage, setRunsPage] = useState(1);

  const { data: workers, isLoading: workersLoading } = useListWorkers(
    { page: workersPage, page_size: DEFAULT_PAGE_SIZE, include_inactive: true },
    { query: { placeholderData: keepPreviousData } },
  );
  const { data: timesheets, isLoading: sheetsLoading } = useListTimesheets(
    { page: sheetsPage, page_size: DEFAULT_PAGE_SIZE },
    { query: { placeholderData: keepPreviousData } },
  );
  const { data: runs, isLoading: runsLoading } = useListPayRuns(
    { page: runsPage, page_size: DEFAULT_PAGE_SIZE },
    { query: { enabled: canAdmin, placeholderData: keepPreviousData } },
  );

  return (
    <div>
      <PageHeader
        title="Payroll"
        description="Workers, site timesheets and weekly pay runs"
        actions={
          <div className="flex gap-2">
            <Can perm="timesheet:write">
              <Button variant="outline" onClick={() => setDayDialog(true)}>
                <CalendarPlus /> Site Day Entry
              </Button>
            </Can>
            <Can perm="payroll:write">
              <Button onClick={() => setRunDialog(true)}>
                <Money /> New Pay Run
              </Button>
            </Can>
          </div>
        }
      />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="timesheets">Timesheets</TabsTrigger>
          <TabsTrigger value="workers">Workers</TabsTrigger>
          {canAdmin && <TabsTrigger value="runs">Pay Runs</TabsTrigger>}
        </TabsList>

        <TabsContent value="timesheets">
          {sheetsLoading ? (
            <PageSkeleton rows={6} />
          ) : (timesheets?.items.length ?? 0) === 0 ? (
            <Card>
              <EmptyState
                icon={<CalendarPlus />}
                title="No timesheets yet"
                hint="Record a site day to capture who worked where. Pay runs are built from these."
                action={
                  <Can perm="timesheet:write">
                    <Button size="sm" onClick={() => setDayDialog(true)}>
                      <CalendarPlus /> Site Day Entry
                    </Button>
                  </Can>
                }
              />
            </Card>
          ) : (
            <Card>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Date</TableHead>
                      <TableHead>Worker</TableHead>
                      <TableHead>Project</TableHead>
                      <TableHead className="text-right">Qty</TableHead>
                      <TableHead className="text-right">OT</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {timesheets?.items.map((sheet) => (
                      <TableRow
                        key={sheet.id}
                        className={
                          isOptimistic(sheet) ? "row-creating transition-colors" : "transition-colors"
                        }
                      >
                        <TableCell>{fmtDate(sheet.work_date)}</TableCell>
                        <TableCell>
                          <div>
                            <EntityLink
                              to="/payroll/workers/$workerId"
                              params={{ workerId: sheet.worker_id }}
                              prefetch={() => getGetWorkerQueryOptions(sheet.worker_id)}
                            >
                              {sheet.worker_name}
                            </EntityLink>
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {sheet.worker_trade}
                          </div>
                        </TableCell>
                        <TableCell>
                          <EntityLink
                            to="/projects/$projectId"
                            params={{ projectId: sheet.project_id }}
                            className="font-mono text-xs font-normal"
                          >
                            {sheet.project_code}
                          </EntityLink>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {Number(sheet.quantity)}{" "}
                          <span className="text-xs text-muted-foreground">
                            {sheet.pay_basis === "hourly" ? "hrs" : "d"}
                          </span>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {Number(sheet.overtime_quantity) || "—"}
                        </TableCell>
                        <TableCell>
                          {sheet.pay_run_id ? (
                            <EntityLink
                              to="/payroll/runs/$runId"
                              params={{ runId: sheet.pay_run_id }}
                              prefetch={() => getGetPayRunQueryOptions(sheet.pay_run_id!)}
                            >
                              <Badge variant="success">Paid</Badge>
                            </EntityLink>
                          ) : (
                            <Badge variant="secondary">Unpaid</Badge>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <PaginationBar
                  page={sheetsPage}
                  pageSize={DEFAULT_PAGE_SIZE}
                  total={timesheets?.total}
                  onPageChange={setSheetsPage}
                />
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="workers">
          {workersLoading ? (
            <PageSkeleton rows={6} />
          ) : (workers?.items.length ?? 0) === 0 ? (
            <Card>
              <EmptyState
                icon={<HardHat />}
                title="No workers on the register"
                hint="Add your site crew with their trade and day/hour rate to start running payroll."
                action={
                  <Can perm="payroll:write">
                    <Button size="sm" onClick={() => setWorkerDialog(true)}>
                      <Plus /> Add Worker
                    </Button>
                  </Can>
                }
              />
            </Card>
          ) : (
            <Card>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Trade</TableHead>
                      <TableHead>Basis</TableHead>
                      <TableHead className="text-right">Rate</TableHead>
                      <TableHead>Extras</TableHead>
                      <TableHead>Status</TableHead>
                      {canAdmin && <TableHead className="w-12" />}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {workers?.items.map((worker, rowIndex) => (
                      <ClickableRow
                        index={rowIndex}
                        key={worker.id}
                        to="/payroll/workers/$workerId"
                        params={{ workerId: worker.id }}
                        prefetch={() => getGetWorkerQueryOptions(worker.id)}
                      >
                        <TableCell className="font-medium">{worker.full_name}</TableCell>
                        <TableCell className="text-muted-foreground">{worker.trade}</TableCell>
                        <TableCell className="text-xs">
                          {worker.pay_basis === "hourly" ? "Hourly" : "Daily"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {moneyExact(worker.rate)}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {(worker.pay_items ?? [])
                            .filter((i) => i.is_active)
                            .map((i) => i.label)
                            .join(", ") || "—"}
                        </TableCell>
                        <TableCell>
                          {worker.is_active ? (
                            <Badge variant="success">Active</Badge>
                          ) : (
                            <Badge variant="outline">Inactive</Badge>
                          )}
                        </TableCell>
                        {canAdmin && (
                          <RowActions>
                            <Button
                              variant="ghost"
                              size="icon"
                              title="Edit worker"
                              onClick={() => {
                                setEditingWorker(worker);
                                setWorkerDialog(true);
                              }}
                            >
                              <PencilSimple />
                            </Button>
                          </RowActions>
                        )}
                      </ClickableRow>
                    ))}
                  </TableBody>
                </Table>
                <PaginationBar
                  page={workersPage}
                  pageSize={DEFAULT_PAGE_SIZE}
                  total={workers?.total}
                  onPageChange={setWorkersPage}
                />
              </CardContent>
            </Card>
          )}
          {canAdmin && (workers?.items.length ?? 0) > 0 && (
            <div className="mt-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setEditingWorker(null);
                  setWorkerDialog(true);
                }}
              >
                <Plus /> Add Worker
              </Button>
            </div>
          )}
        </TabsContent>

        {canAdmin && (
          <TabsContent value="runs">
            {runsLoading ? (
              <PageSkeleton rows={4} />
            ) : (runs?.items.length ?? 0) === 0 ? (
              <Card>
                <EmptyState
                  icon={<Money />}
                  title="No pay runs yet"
                  hint="A pay run gathers all unpaid timesheets in a period, prices them and posts labour costs on approval."
                  action={
                    <Button size="sm" onClick={() => setRunDialog(true)}>
                      <Money /> New Pay Run
                    </Button>
                  }
                />
              </Card>
            ) : (
              <Card>
                <CardContent className="p-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Document</TableHead>
                        <TableHead>Period</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="text-right">Workers</TableHead>
                        <TableHead className="text-right">Gross</TableHead>
                        <TableHead className="text-right">Net</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {runs?.items.map((run, rowIndex) => (
                        <ClickableRow
                          index={rowIndex}
                          key={run.id}
                          to="/payroll/runs/$runId"
                          params={{ runId: run.id }}
                          prefetch={() => getGetPayRunQueryOptions(run.id)}
                        >
                          <TableCell className="font-mono text-xs">{run.doc_number}</TableCell>
                          <TableCell className="text-sm">
                            {fmtDate(run.period_start)} → {fmtDate(run.period_end)}
                          </TableCell>
                          <TableCell>
                            {run.status === "approved" ? (
                              <Badge variant="success">Approved</Badge>
                            ) : (
                              <Badge variant="secondary">Draft</Badge>
                            )}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {run.line_count}
                          </TableCell>
                          <TableCell className="text-right font-medium tabular-nums">
                            {moneyExact(run.gross_total)}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {moneyExact(run.net_total)}
                          </TableCell>
                        </ClickableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <PaginationBar
                    page={runsPage}
                    pageSize={DEFAULT_PAGE_SIZE}
                    total={runs?.total}
                    onPageChange={setRunsPage}
                  />
                </CardContent>
              </Card>
            )}
          </TabsContent>
        )}
      </Tabs>

      <WorkerFormDialog
        open={workerDialog}
        onOpenChange={setWorkerDialog}
        worker={editingWorker}
      />
      <DayEntryDialog open={dayDialog} onOpenChange={setDayDialog} />
      <PayRunCreateDialog open={runDialog} onOpenChange={setRunDialog} />
    </div>
  );
}
