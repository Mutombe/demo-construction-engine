import { createFileRoute } from "@tanstack/react-router";
import { Mail, MapPin, Pencil, Phone, UserRound } from "lucide-react";
import { useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Can } from "@/components/layout/Can";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ClickableRow } from "@/components/ui/linked-row";
import { DetailSkeleton, TableSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ClientFormDialog } from "@/features/clients/ClientFormDialog";
import { PortalAccessCard } from "@/features/portal/PortalAccessCard";
import { ProjectStatusBadge } from "@/features/projects/StatusBadge";
import {
  getGetClientQueryOptions,
  getGetProjectQueryOptions,
  useGetClient,
  useListProjects,
} from "@/lib/api/generated/endpoints";
import { fmtDate, money } from "@/lib/format";

export const Route = createFileRoute("/_app/clients/$clientId")({
  component: ClientDetailPage,
  loader: ({ context: { queryClient }, params }) =>
    queryClient.ensureQueryData(getGetClientQueryOptions(params.clientId)),
});

function ClientDetailPage() {
  const { clientId } = Route.useParams();
  const { data: client } = useGetClient(clientId);
  const { data: projects, isLoading: projectsLoading } = useListProjects({
    client_id: clientId,
    page_size: 100,
  });
  const [editOpen, setEditOpen] = useState(false);

  if (!client) {
    return <DetailSkeleton />;
  }

  const contractTotal = (projects?.items ?? []).reduce(
    (sum, p) => sum + Number(p.contract_value ?? 0),
    0,
  );

  return (
    <div>
      <Breadcrumbs items={[{ label: "Clients", to: "/clients" }, { label: client.name }]} />
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{client.name}</h1>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
            {client.contact_person && (
              <span className="inline-flex items-center gap-1">
                <UserRound className="h-3.5 w-3.5" /> {client.contact_person}
              </span>
            )}
            {client.email && (
              <a
                href={`mailto:${client.email}`}
                className="inline-flex items-center gap-1 hover:text-foreground"
              >
                <Mail className="h-3.5 w-3.5" /> {client.email}
              </a>
            )}
            {client.phone && (
              <span className="inline-flex items-center gap-1">
                <Phone className="h-3.5 w-3.5" /> {client.phone}
              </span>
            )}
            {client.address && (
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-3.5 w-3.5" /> {client.address}
              </span>
            )}
          </div>
        </div>
        <Can perm="client:write">
          <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
            <Pencil /> Edit
          </Button>
        </Can>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle>Projects</CardTitle>
            <span className="text-sm text-muted-foreground tabular-nums">
              {projects?.total ?? 0} project{(projects?.total ?? 0) === 1 ? "" : "s"} ·{" "}
              {money(contractTotal)} contracted
            </span>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Code</TableHead>
                  <TableHead>Project</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Due</TableHead>
                  <TableHead className="text-right">Contract</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {projectsLoading && !projects && <TableSkeleton columns={5} rows={3} />}
                {projects?.items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="p-0">
                      <EmptyState
                        icon={<UserRound />}
                        title="No projects for this client yet"
                        hint="Create a project and pick this client to see it here."
                      />
                    </TableCell>
                  </TableRow>
                )}
                {projects?.items.map((project) => (
                  <ClickableRow
                    key={project.id}
                    to="/projects/$projectId"
                    params={{ projectId: project.id }}
                    prefetch={() => getGetProjectQueryOptions(project.id)}
                  >
                    <TableCell className="font-mono text-xs">{project.code}</TableCell>
                    <TableCell className="font-medium">{project.name}</TableCell>
                    <TableCell>
                      <ProjectStatusBadge status={project.status ?? "planning"} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {fmtDate(project.planned_end)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {money(project.contract_value)}
                    </TableCell>
                  </ClickableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Can perm="project:write">
            <PortalAccessCard clientId={client.id} clientName={client.name} />
          </Can>
          {client.notes && (
            <Card>
              <CardHeader>
                <CardTitle>Notes</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                  {client.notes}
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      <ClientFormDialog open={editOpen} onOpenChange={setEditOpen} client={client} />
    </div>
  );
}
