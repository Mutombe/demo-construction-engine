import { keepPreviousData, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import {
  ClipboardText,
  FileText,
  Plus,
  Prohibit,
  ShoppingCart,
  Warning,
} from "@phosphor-icons/react";
import { useState } from "react";
import { z } from "zod";
import { PageHeader } from "@/components/layout/AppShell";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { confirmDialog } from "@/components/ui/confirm";
import { EmptyState } from "@/components/ui/empty-state";
import { ClickableRow, RowActions } from "@/components/ui/linked-row";
import { DEFAULT_PAGE_SIZE, PaginationBar } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
import { TableSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ConvertToPoDialog } from "@/features/requisitions/ConvertToPoDialog";
import { RequisitionFormDialog } from "@/features/requisitions/RequisitionFormDialog";
import { errDetail } from "@/lib/api/errors";
import {
  useCancelRequisition,
  useConvertRequisitionToRfq,
  getGetRequisitionQueryOptions,
  useListRequisitions,
} from "@/lib/api/generated/endpoints";
import type { RequisitionRead } from "@/lib/api/generated/model";
import { fmtDate } from "@/lib/format";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

const searchSchema = z.object({
  page: z.number().int().min(1).optional().default(1),
  status: z.string().optional(),
});

export const Route = createFileRoute("/_app/procurement/requisitions")({
  validateSearch: searchSchema,
  component: RequisitionsPage,
});

function AgeBadge({ requisition }: { requisition: RequisitionRead }) {
  if (requisition.status !== "open") {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  const days = requisition.age_days ?? 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs font-medium tabular-nums",
        requisition.is_urgent ? "text-destructive" : "text-muted-foreground",
      )}
    >
      {requisition.is_urgent && <Warning className="size-3.5" />}
      {days === 0 ? "today" : `${days}d waiting`}
    </span>
  );
}

function RequisitionsPage() {
  const { page, status } = Route.useSearch();
  const navigate = Route.useNavigate();
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [converting, setConverting] = useState<RequisitionRead | null>(null);

  const { data, isLoading } = useListRequisitions(
    {
      page,
      page_size: DEFAULT_PAGE_SIZE,
      status: (status as "open" | "actioned" | "cancelled") || undefined,
    },
    { query: { placeholderData: keepPreviousData } },
  );

  const toRfqMutation = useConvertRequisitionToRfq();
  const cancelMutation = useCancelRequisition();

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["/api/v1/requisitions"] }),
      queryClient.invalidateQueries({ queryKey: ["/api/v1/dashboard"] }),
    ]);

  const convertToRfq = async (requisition: RequisitionRead) => {
    if (
      !(await confirmDialog({
        title: "Convert to RFQ",
        message: `Draft an RFQ from ${requisition.doc_number} with its ${requisition.item_count} line(s)?`,
      }))
    )
      return;
    try {
      const rfq = await toRfqMutation.mutateAsync({ requisitionId: requisition.id });
      await refresh();
      toast.success(`${rfq.doc_number} drafted`);
      void navigate({ to: "/procurement/rfqs/$rfqId", params: { rfqId: rfq.id } });
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const cancel = async (requisition: RequisitionRead) => {
    if (
      !(await confirmDialog({
        title: "Cancel request",
        message: `Cancel ${requisition.doc_number}? Site will see it is no longer being actioned.`,
        tone: "danger",
      }))
    )
      return;
    try {
      await cancelMutation.mutateAsync({ requisitionId: requisition.id });
      await refresh();
      toast.success("Request cancelled");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const items = data?.items ?? [];
  const openCount = items.filter((r) => r.status === "open").length;

  return (
    <div>
      <PageHeader
        title="Material Requests"
        description="What site is waiting for — oldest requests first"
        actions={
          <Can perm="requisition:create">
            <Button onClick={() => setFormOpen(true)}>
              <Plus /> Request Materials
            </Button>
          </Can>
        }
      />

      <div className="mb-4 flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Status:</span>
        <Select
          className="w-48"
          value={status ?? ""}
          onChange={(e) =>
            void navigate({
              search: { page: 1, status: e.target.value || undefined },
              replace: true,
            })
          }
        >
          <option value="">All</option>
          <option value="open">Open</option>
          <option value="actioned">Actioned</option>
          <option value="cancelled">Cancelled</option>
        </Select>
        {openCount > 0 && (
          <span className="text-sm text-muted-foreground">
            {openCount} awaiting action on this page
          </span>
        )}
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Request</TableHead>
                <TableHead>Project</TableHead>
                <TableHead>Requested By</TableHead>
                <TableHead>Needed By</TableHead>
                <TableHead>Waiting</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && !data && <TableSkeleton columns={7} rows={5} />}
              {!isLoading && items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="p-0">
                    <EmptyState
                      icon={<ClipboardText />}
                      title="Nothing waiting on procurement"
                      hint="When site needs materials they raise a request here, and it converts to an RFQ or purchase order in one click."
                    />
                  </TableCell>
                </TableRow>
              )}
              {items.map((requisition) => (
                <ClickableRow
                  key={requisition.id}
                  to="/procurement/requisitions/$requisitionId"
                  params={{ requisitionId: requisition.id }}
                  prefetch={() => getGetRequisitionQueryOptions(requisition.id)}
                >
                  <TableCell>
                    <div className="font-mono text-xs text-muted-foreground">
                      {requisition.doc_number}
                    </div>
                    <div className="text-sm">
                      {requisition.item_count} line
                      {requisition.item_count === 1 ? "" : "s"}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">{requisition.project_name ?? "—"}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {requisition.requested_by_name ?? "—"}
                  </TableCell>
                  <TableCell className="text-sm">
                    {requisition.needed_by ? fmtDate(requisition.needed_by) : "—"}
                  </TableCell>
                  <TableCell>
                    <AgeBadge requisition={requisition} />
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        requisition.status === "open"
                          ? requisition.is_urgent
                            ? "destructive"
                            : "warning"
                          : requisition.status === "actioned"
                            ? "success"
                            : "outline"
                      }
                    >
                      {requisition.status}
                    </Badge>
                  </TableCell>
                  <RowActions>
                    <div className="flex justify-end gap-1">
                      {requisition.status === "open" && (
                        <Can perm="requisition:action">
                          <Button
                            variant="outline"
                            size="sm"
                            title="Draft an RFQ from this request"
                            onClick={() => void convertToRfq(requisition)}
                          >
                            <FileText /> To RFQ
                          </Button>
                          <Button
                            size="sm"
                            title="Draft a purchase order from this request"
                            onClick={() => setConverting(requisition)}
                          >
                            <ShoppingCart /> To PO
                          </Button>
                        </Can>
                      )}
                      {requisition.status === "open" && (
                        <Can perm="requisition:create">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="text-destructive"
                            title="Cancel request"
                            onClick={() => void cancel(requisition)}
                          >
                            <Prohibit />
                          </Button>
                        </Can>
                      )}
                    </div>
                  </RowActions>
                </ClickableRow>
              ))}
            </TableBody>
          </Table>
          <PaginationBar
            page={page}
            pageSize={DEFAULT_PAGE_SIZE}
            total={data?.total}
            onPageChange={(p) =>
              void navigate({ search: (prev) => ({ ...prev, page: p }), replace: true })
            }
          />
        </CardContent>
      </Card>

      <RequisitionFormDialog open={formOpen} onOpenChange={setFormOpen} />
      <ConvertToPoDialog
        requisition={converting}
        onOpenChange={(open) => {
          if (!open) setConverting(null);
        }}
        onDone={async (poId) => {
          setConverting(null);
          await refresh();
          void navigate({ to: "/procurement/pos/$poId", params: { poId } });
        }}
      />
    </div>
  );
}
