import { keepPreviousData } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { CalendarBlank, HardHat, PencilSimple, Phone } from "@phosphor-icons/react";
import { useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { EntityLink } from "@/components/ui/linked-row";
import { DEFAULT_PAGE_SIZE, PaginationBar } from "@/components/ui/pagination";
import { DetailSkeleton, TableSkeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/ui/stat-card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { WorkerFormDialog } from "@/features/payroll/WorkerFormDialog";
import {
  getGetPayRunQueryOptions,
  getGetWorkerQueryOptions,
  useGetWorker,
  useListTimesheets,
} from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";

export const Route = createFileRoute("/_app/payroll/workers/$workerId")({
  component: WorkerDetailPage,
  loader: ({ context: { queryClient }, params }) =>
    queryClient.ensureQueryData(getGetWorkerQueryOptions(params.workerId)),
});

function WorkerDetailPage() {
  const { workerId } = Route.useParams();
  const { data: worker } = useGetWorker(workerId);
  const [page, setPage] = useState(1);
  const { data: timesheets, isLoading: sheetsLoading } = useListTimesheets(
    { worker_id: workerId, page, page_size: DEFAULT_PAGE_SIZE },
    { query: { placeholderData: keepPreviousData } },
  );
  const [editOpen, setEditOpen] = useState(false);

  if (!worker) {
    return <DetailSkeleton />;
  }

  const unit = worker.pay_basis === "hourly" ? "hrs" : "days";
  const unpaidQty = (timesheets?.items ?? [])
    .filter((s) => !s.pay_run_id)
    .reduce((sum, s) => sum + Number(s.quantity), 0);

  return (
    <div>
      <Breadcrumbs
        items={[{ label: "Payroll", to: "/payroll" }, { label: worker.full_name }]}
      />
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-semibold tracking-tight">{worker.full_name}</h1>
            {worker.is_active ? (
              <Badge variant="success">Active</Badge>
            ) : (
              <Badge variant="outline">Off payroll</Badge>
            )}
          </div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <HardHat className="h-3.5 w-3.5" /> {worker.trade}
            </span>
            {worker.phone && (
              <span className="inline-flex items-center gap-1">
                <Phone className="h-3.5 w-3.5" /> {worker.phone}
              </span>
            )}
            {worker.national_id && <span>ID {worker.national_id}</span>}
          </div>
        </div>
        <Can perm="payroll:write">
          <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
            <PencilSimple /> Edit worker
          </Button>
        </Can>
      </div>

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <StatCard
          label="Rate"
          value={moneyExact(worker.rate)}
          sub={worker.pay_basis === "hourly" ? "per hour" : "per day"}
        />
        <StatCard
          label="Unpaid time"
          value={`${timesheets && timesheets.total > DEFAULT_PAGE_SIZE ? "~" : ""}${unpaidQty} ${unit}`}
          sub="awaiting the next pay run"
          icon={<CalendarBlank />}
        />
        <StatCard
          label="Recurring items"
          value={(worker.pay_items ?? []).filter((i) => i.is_active).length}
          sub={
            (worker.pay_items ?? [])
              .filter((i) => i.is_active)
              .map((i) => i.label)
              .join(", ") || "none"
          }
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent timesheets</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Project</TableHead>
                <TableHead className="text-right">Qty</TableHead>
                <TableHead className="text-right">OT</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sheetsLoading && !timesheets && <TableSkeleton columns={5} rows={5} />}
              {timesheets?.items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="p-0">
                    <EmptyState
                      icon={<CalendarBlank />}
                      title="No timesheets yet"
                      hint="Record a site day on the Payroll page to capture this worker's time."
                    />
                  </TableCell>
                </TableRow>
              )}
              {timesheets?.items.map((sheet) => (
                <TableRow key={sheet.id}>
                  <TableCell>{fmtDate(sheet.work_date)}</TableCell>
                  <TableCell>
                    <EntityLink
                      to="/projects/$projectId"
                      params={{ projectId: sheet.project_id }}
                      className="font-mono text-xs"
                    >
                      {sheet.project_code}
                    </EntityLink>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {Number(sheet.quantity)} {unit}
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
                        className="text-xs"
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
            page={page}
            pageSize={DEFAULT_PAGE_SIZE}
            total={timesheets?.total}
            onPageChange={setPage}
          />
        </CardContent>
      </Card>

      <WorkerFormDialog open={editOpen} onOpenChange={setEditOpen} worker={worker} />
    </div>
  );
}
