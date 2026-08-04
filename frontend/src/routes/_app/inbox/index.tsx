import { keepPreviousData } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { PageHeader } from "@/components/layout/AppShell";
import { Card, CardContent } from "@/components/ui/card";
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
import { DropZone } from "@/features/ingestion/DropZone";
import { IngestionCard } from "@/features/ingestion/IngestionCard";
import { ReviewPanel } from "@/features/ingestion/ReviewPanel";
import { IngestionStatusBadge } from "@/features/ingestion/StatusBadge";
import { actionOf, DOC_TYPE_LABELS } from "@/features/ingestion/types";
import { useUploadPump } from "@/features/ingestion/useUploadPump";
import { useListIngestionItems, useListProjects } from "@/lib/api/generated/endpoints";
import type { IngestionStatus } from "@/lib/api/generated/model";
import { fmtDate } from "@/lib/format";

export const Route = createFileRoute("/_app/inbox/")({
  component: InboxPage,
  // ?item=<id> deep-links straight into the review panel — shareable/bookmarkable
  validateSearch: (search: Record<string, unknown>) => ({
    item: typeof search.item === "string" ? search.item : undefined,
    page: typeof search.page === "number" && search.page >= 1 ? search.page : 1,
  }),
});

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "All Statuses" },
  { value: "needs_info", label: "Needs Review" },
  { value: "drafted", label: "Ready to Approve" },
  { value: "posted", label: "Posted" },
  { value: "rejected", label: "Rejected" },
  { value: "failed", label: "Failed" },
];

function InboxPage() {
  const [projectHint, setProjectHint] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const { item: reviewId, page } = Route.useSearch();
  const navigate = useNavigate();
  const setReviewId = (id: string | null) =>
    void navigate({
      to: "/inbox",
      search: { item: id ?? undefined, page },
      replace: reviewId != null && id != null,
    });

  const { data: projects } = useListProjects({ page_size: 100 });
  const { cards, addFiles, retry, refreshCard } = useUploadPump(projectHint || undefined);
  const { data: history, isLoading } = useListIngestionItems(
    {
      page,
      page_size: DEFAULT_PAGE_SIZE,
      status: (statusFilter || undefined) as IngestionStatus | undefined,
    },
    { query: { placeholderData: keepPreviousData } },
  );

  const activeItemIds = new Set(cards.map((c) => c.itemId).filter(Boolean));
  const historyItems = (history?.items ?? []).filter((i) => !activeItemIds.has(i.id));

  return (
    <div>
      <PageHeader
        title="AI Inbox"
        description="Drop site paperwork here. Claude reads it, you approve it, and it posts"
        actions={
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Project hint</span>
            <Select
              className="w-56"
              value={projectHint}
              onChange={(e) => setProjectHint(e.target.value)}
            >
              <option value="">No hint</option>
              {projects?.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code} · {p.name}
                </option>
              ))}
            </Select>
          </div>
        }
      />

      <div className="space-y-4">
        <DropZone onFiles={addFiles} />

        {cards.length > 0 && (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {cards.map((card) => (
              <IngestionCard
                key={card.localId}
                card={card}
                onRetry={retry}
                onReview={setReviewId}
              />
            ))}
          </div>
        )}

        <Card>
          <CardContent className="p-0">
            <div className="flex items-center justify-between border-b px-4 py-2.5">
              <span className="text-sm font-medium">History</span>
              <Select
                className="w-44"
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  void navigate({
                    to: "/inbox",
                    search: { item: reviewId, page: 1 },
                    replace: true,
                  });
                }}
              >
                {STATUS_FILTERS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </Select>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>File</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Summary</TableHead>
                  <TableHead>Received</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading && !history && <TableSkeleton columns={5} />}
                {!isLoading && historyItems.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                      Nothing here yet. Drop a document above to get started.
                    </TableCell>
                  </TableRow>
                )}
                {historyItems.map((item) => {
                  const action = actionOf(item);
                  return (
                    <TableRow
                      key={item.id}
                      className="cursor-pointer"
                      onClick={() => setReviewId(item.id)}
                    >
                      <TableCell className="max-w-48 truncate font-medium">
                        {item.original_filename}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {item.doc_type ? DOC_TYPE_LABELS[item.doc_type] : "—"}
                      </TableCell>
                      <TableCell>
                        <IngestionStatusBadge status={item.status} />
                      </TableCell>
                      <TableCell className="max-w-72 truncate text-xs text-muted-foreground">
                        {typeof action?.display?.summary === "string"
                          ? action.display.summary
                          : (item.error ?? "—")}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {fmtDate(item.created_at)}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            <PaginationBar
              page={page}
              pageSize={DEFAULT_PAGE_SIZE}
              total={history?.total}
              onPageChange={(p) =>
                void navigate({
                  to: "/inbox",
                  search: { item: reviewId, page: p },
                  replace: true,
                })
              }
            />
          </CardContent>
        </Card>
      </div>

      <ReviewPanel
        itemId={reviewId ?? null}
        onOpenChange={(open) => {
          if (!open) setReviewId(null);
        }}
        onUpdated={refreshCard}
      />
    </div>
  );
}
