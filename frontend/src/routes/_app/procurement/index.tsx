import { Link, createFileRoute } from "@tanstack/react-router";
import { UsersThree } from "@phosphor-icons/react";
import { z } from "zod";
import { PageHeader } from "@/components/layout/AppShell";
import { Select } from "@/components/ui/select";
import { PoList, RfqList } from "@/features/procurement/ProcurementLists";
import { useListProjects } from "@/lib/api/generated/endpoints";

const searchSchema = z.object({ projectId: z.string().optional() });

export const Route = createFileRoute("/_app/procurement/")({
  validateSearch: searchSchema,
  component: ProcurementPage,
});

function ProcurementPage() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  const { data: projects } = useListProjects({ page_size: 100 });

  const projectId = search.projectId ?? projects?.items[0]?.id;

  return (
    <div>
      <PageHeader
        title="Procurement"
        description="RFQs, supplier quotes and purchase orders"
        actions={
          <Link
            to="/procurement/suppliers"
            className="inline-flex h-9 items-center gap-2 rounded-md border border-input bg-card px-4 text-sm font-medium transition-colors hover:bg-accent"
          >
            <UsersThree className="h-4 w-4" /> Suppliers
          </Link>
        }
      />

      <div className="mb-4 flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Project:</span>
        <Select
          className="w-80"
          value={projectId ?? ""}
          onChange={(e) =>
            void navigate({ search: { projectId: e.target.value }, replace: true })
          }
        >
          {projects?.items.map((p) => (
            <option key={p.id} value={p.id}>
              {p.code} · {p.name}
            </option>
          ))}
        </Select>
      </div>

      {projectId ? (
        <div className="grid gap-4 xl:grid-cols-2">
          <RfqList projectId={projectId} />
          <PoList projectId={projectId} />
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Create a project first.</p>
      )}
    </div>
  );
}
