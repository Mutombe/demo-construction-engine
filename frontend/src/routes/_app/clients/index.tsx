import { createFileRoute } from "@tanstack/react-router";
import { Building2, Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { PageHeader } from "@/components/layout/AppShell";
import { Can } from "@/components/layout/Can";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ClickableRow, RowActions } from "@/components/ui/linked-row";
import { TableSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ClientFormDialog } from "@/features/clients/ClientFormDialog";
import { getGetClientQueryOptions, useListClients } from "@/lib/api/generated/endpoints";
import type { ClientRead } from "@/lib/api/generated/model";

export const Route = createFileRoute("/_app/clients/")({
  component: ClientsPage,
});

function ClientsPage() {
  const { data, isLoading } = useListClients({ page_size: 100 });
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<ClientRead | null>(null);

  return (
    <div>
      <PageHeader
        title="Clients"
        description="The people you build for — each client links to their projects and portal access"
        actions={
          <Can perm="client:write">
            <Button
              onClick={() => {
                setEditing(null);
                setDialogOpen(true);
              }}
            >
              <Plus /> New client
            </Button>
          </Can>
        }
      />
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Client</TableHead>
                <TableHead>Contact</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Phone</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && !data && <TableSkeleton columns={5} rows={5} />}
              {data?.items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="p-0">
                    <EmptyState
                      icon={<Building2 />}
                      title="No clients yet"
                      hint="Add the companies you build for; projects, valuations and portal links all hang off a client."
                    />
                  </TableCell>
                </TableRow>
              )}
              {data?.items.map((client) => (
                <ClickableRow
                  key={client.id}
                  to="/clients/$clientId"
                  params={{ clientId: client.id }}
                  prefetch={() => getGetClientQueryOptions(client.id)}
                >
                  <TableCell className="font-medium">{client.name}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {client.contact_person ?? "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{client.email ?? "—"}</TableCell>
                  <TableCell className="text-muted-foreground">{client.phone ?? "—"}</TableCell>
                  <RowActions className="text-right">
                    <Can perm="client:write">
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Edit client"
                        onClick={() => {
                          setEditing(client);
                          setDialogOpen(true);
                        }}
                      >
                        <Pencil />
                      </Button>
                    </Can>
                  </RowActions>
                </ClickableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      <ClientFormDialog open={dialogOpen} onOpenChange={setDialogOpen} client={editing} />
    </div>
  );
}
