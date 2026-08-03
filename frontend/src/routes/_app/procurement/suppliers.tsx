import { createFileRoute } from "@tanstack/react-router";
import { Pencil, Plus, Search } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/layout/AppShell";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { usePermission } from "@/features/auth/hooks";
import { SupplierFormDialog } from "@/features/procurement/SupplierFormDialog";
import { useListSuppliers, useUpdateSupplier } from "@/lib/api/generated/endpoints";
import type { SupplierRead } from "@/lib/api/generated/model";

export const Route = createFileRoute("/_app/procurement/suppliers")({
  component: SuppliersPage,
});

function SuppliersPage() {
  const [search, setSearch] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<SupplierRead | null>(null);
  const queryClient = useQueryClient();
  const canWrite = usePermission("procurement:write");
  const { data, isLoading } = useListSuppliers({ search: search || undefined, page_size: 100 });
  const updateMutation = useUpdateSupplier();

  const toggleActive = async (supplier: SupplierRead) => {
    try {
      await updateMutation.mutateAsync({
        supplierId: supplier.id,
        data: { is_active: !supplier.is_active },
      });
      await queryClient.invalidateQueries();
    } catch {
      toast.error("Update failed");
    }
  };

  return (
    <div>
      <PageHeader
        title="Suppliers"
        description={data ? `${data.total} supplier${data.total === 1 ? "" : "s"}` : undefined}
        actions={
          <Can perm="procurement:write">
            <Button
              onClick={() => {
                setEditing(null);
                setDialogOpen(true);
              }}
            >
              <Plus /> New supplier
            </Button>
          </Can>
        }
      />

      <div className="relative mb-4 w-72">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search name or category…"
          className="pl-8"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Supplier</TableHead>
              <TableHead>Contact</TableHead>
              <TableHead>Categories</TableHead>
              <TableHead>Status</TableHead>
              {canWrite && <TableHead className="w-40" />}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={5} className="py-10 text-center text-muted-foreground">
                  Loading…
                </TableCell>
              </TableRow>
            )}
            {!isLoading && !data?.items.length && (
              <TableRow>
                <TableCell colSpan={5} className="py-10 text-center text-muted-foreground">
                  No suppliers yet.
                </TableCell>
              </TableRow>
            )}
            {data?.items.map((s) => (
              <TableRow key={s.id}>
                <TableCell>
                  <div className="font-medium">{s.name}</div>
                  {s.tax_id && (
                    <div className="text-xs text-muted-foreground">Tax: {s.tax_id}</div>
                  )}
                </TableCell>
                <TableCell className="text-sm">
                  <div>{s.contact_name ?? "—"}</div>
                  <div className="text-xs text-muted-foreground">
                    {[s.email, s.phone].filter(Boolean).join(" · ")}
                  </div>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {s.categories ?? "—"}
                </TableCell>
                <TableCell>
                  {s.is_active ? (
                    <Badge variant="success">Active</Badge>
                  ) : (
                    <Badge variant="outline">Inactive</Badge>
                  )}
                </TableCell>
                {canWrite && (
                  <TableCell>
                    <div className="flex gap-1.5">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => {
                          setEditing(s);
                          setDialogOpen(true);
                        }}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void toggleActive(s)}
                      >
                        {s.is_active ? "Deactivate" : "Reactivate"}
                      </Button>
                    </div>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <SupplierFormDialog open={dialogOpen} onOpenChange={setDialogOpen} supplier={editing} />
    </div>
  );
}
