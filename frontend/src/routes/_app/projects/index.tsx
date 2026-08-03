import { keepPreviousData } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Plus, Search } from "lucide-react";
import { useState } from "react";
import { z } from "zod";
import { PageHeader } from "@/components/layout/AppShell";
import { Can } from "@/components/layout/Can";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ClickableRow, EntityLink } from "@/components/ui/linked-row";
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
import { ProjectFormDialog } from "@/features/projects/ProjectFormDialog";
import { ProjectStatusBadge } from "@/features/projects/StatusBadge";
import {
  getGetClientQueryOptions,
  getGetProjectQueryOptions,
  useListProjects,
} from "@/lib/api/generated/endpoints";
import type { ProjectStatus } from "@/lib/api/generated/model";
import { fmtDate, money } from "@/lib/format";

const searchSchema = z.object({
  page: z.number().int().min(1).optional().default(1),
  status: z
    .enum(["planning", "active", "on_hold", "completed", "cancelled"])
    .optional(),
  q: z.string().optional(),
});

export const Route = createFileRoute("/_app/projects/")({
  validateSearch: searchSchema,
  component: ProjectsPage,
});

const PAGE_SIZE = 25;

function ProjectsPage() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  const [dialogOpen, setDialogOpen] = useState(false);

  const { data, isLoading } = useListProjects(
    {
      page: search.page,
      page_size: PAGE_SIZE,
      status: (search.status as ProjectStatus) ?? undefined,
      search: search.q || undefined,
    },
    // Refiltering/paging keeps the previous rows on screen — no blank flash
    { query: { placeholderData: keepPreviousData } },
  );

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div>
      <PageHeader
        title="Projects"
        description={data ? `${data.total} project${data.total === 1 ? "" : "s"}` : undefined}
        actions={
          <Can perm="project:write">
            <Button onClick={() => setDialogOpen(true)}>
              <Plus /> New project
            </Button>
          </Can>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search name or code…"
            className="w-64 pl-8"
            defaultValue={search.q ?? ""}
            onChange={(e) => {
              const value = e.target.value;
              void navigate({
                search: (prev) => ({ ...prev, q: value || undefined, page: 1 }),
                replace: true,
              });
            }}
          />
        </div>
        <Select
          className="w-40"
          value={search.status ?? ""}
          onChange={(e) =>
            void navigate({
              search: (prev) => ({
                ...prev,
                status: (e.target.value || undefined) as typeof search.status,
                page: 1,
              }),
            })
          }
        >
          <option value="">All statuses</option>
          <option value="planning">Planning</option>
          <option value="active">Active</option>
          <option value="on_hold">On hold</option>
          <option value="completed">Completed</option>
          <option value="cancelled">Cancelled</option>
        </Select>
      </div>

      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Code</TableHead>
              <TableHead>Project</TableHead>
              <TableHead>Client</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Dates</TableHead>
              <TableHead className="text-right">Contract value</TableHead>
              <TableHead>PM</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && !data && <TableSkeleton columns={7} rows={6} />}
            {!isLoading && !data?.items.length && (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                  No projects match your filters.
                </TableCell>
              </TableRow>
            )}
            {data?.items.map((p) => (
              <ClickableRow
                key={p.id}
                to="/projects/$projectId"
                params={{ projectId: p.id }}
                prefetch={() => getGetProjectQueryOptions(p.id)}
              >
                <TableCell className="font-mono text-xs">{p.code}</TableCell>
                <TableCell>
                  <span className="font-medium">{p.name}</span>
                  {p.city && <div className="text-xs text-muted-foreground">{p.city}</div>}
                </TableCell>
                <TableCell>
                  {p.client_name ? (
                    <EntityLink
                      to="/clients/$clientId"
                      params={{ clientId: p.client_id }}
                      prefetch={() => getGetClientQueryOptions(p.client_id)}
                      className="text-sm font-normal"
                    >
                      {p.client_name}
                    </EntityLink>
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell>
                  <ProjectStatusBadge status={p.status ?? "planning"} />
                </TableCell>
                <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                  {fmtDate(p.planned_start)} → {fmtDate(p.planned_end)}
                </TableCell>
                <TableCell className="text-right font-medium tabular-nums">
                  {money(p.contract_value)}
                </TableCell>
                <TableCell className="text-sm">{p.project_manager_name ?? "—"}</TableCell>
              </ClickableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {totalPages > 1 && (
        <div className="mt-3 flex items-center justify-end gap-2 text-sm">
          <Button
            variant="outline"
            size="sm"
            disabled={search.page <= 1}
            onClick={() =>
              void navigate({ search: (prev) => ({ ...prev, page: search.page - 1 }) })
            }
          >
            Previous
          </Button>
          <span className="text-muted-foreground">
            Page {search.page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={search.page >= totalPages}
            onClick={() =>
              void navigate({ search: (prev) => ({ ...prev, page: search.page + 1 }) })
            }
          >
            Next
          </Button>
        </div>
      )}

      <ProjectFormDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  );
}
