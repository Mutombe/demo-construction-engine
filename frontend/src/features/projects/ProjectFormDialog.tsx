import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { toast } from "@/lib/toast";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateProject,
  useListClients,
  useListUsers,
  useUpdateProject,
} from "@/lib/api/generated/endpoints";
import type { ProjectListItem } from "@/lib/api/generated/model";
import { usePermission } from "@/features/auth/hooks";
import { STATUS_LABELS } from "@/lib/format";

const schema = z.object({
  name: z.string().min(1, "Required"),
  client_id: z.string().min(1, "Required"),
  status: z.enum(["planning", "active", "on_hold", "completed", "cancelled"]),
  description: z.string().optional(),
  site_address: z.string().optional(),
  city: z.string().optional(),
  planned_start: z.string().optional(),
  planned_end: z.string().optional(),
  contract_value: z.string().optional(),
  project_manager_id: z.string().optional(),
});
type FormValues = z.infer<typeof schema>;

export function ProjectFormDialog({
  open,
  onOpenChange,
  project,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  project?: ProjectListItem | null;
}) {
  const queryClient = useQueryClient();
  const isAdmin = usePermission("users:manage");
  const { data: clients } = useListClients({ page_size: 200 }, { query: { enabled: open } });
  const { data: users } = useListUsers(
    { page_size: 200 },
    { query: { enabled: open && isAdmin } },
  );
  const createMutation = useCreateProject();
  const updateMutation = useUpdateProject();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  useEffect(() => {
    if (open) {
      reset({
        name: project?.name ?? "",
        client_id: project?.client_id ?? "",
        status: (project?.status as FormValues["status"]) ?? "planning",
        description: project?.description ?? "",
        site_address: project?.site_address ?? "",
        city: project?.city ?? "",
        planned_start: project?.planned_start ?? "",
        planned_end: project?.planned_end ?? "",
        contract_value: project?.contract_value ?? "",
        project_manager_id: project?.project_manager_id ?? "",
      });
    }
  }, [open, project, reset]);

  const onSubmit = async (values: FormValues) => {
    const payload = {
      name: values.name,
      client_id: values.client_id,
      status: values.status,
      description: values.description || null,
      site_address: values.site_address || null,
      city: values.city || null,
      planned_start: values.planned_start || null,
      planned_end: values.planned_end || null,
      contract_value: values.contract_value || null,
      project_manager_id: values.project_manager_id || null,
    };
    try {
      if (project) {
        await updateMutation.mutateAsync({ projectId: project.id, data: payload });
        toast.success("Project updated");
      } else {
        await createMutation.mutateAsync({ data: payload });
        toast.success("Project created");
      }
      await queryClient.invalidateQueries();
      onOpenChange(false);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
          ?.detail ?? "Something went wrong";
      toast.error(detail);
    }
  };

  const busy = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{project ? `Edit ${project.code}` : "New Project"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="p-name">Project Name</Label>
            <Input id="p-name" {...register("name")} />
            {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="p-client">Client</Label>
              <Select id="p-client" {...register("client_id")}>
                <option value="">Select client…</option>
                {clients?.items.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
              {errors.client_id && (
                <p className="text-xs text-destructive">{errors.client_id.message}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="p-status">Status</Label>
              <Select id="p-status" {...register("status")}>
                {Object.entries(STATUS_LABELS)
                  .filter(([k]) =>
                    ["planning", "active", "on_hold", "completed", "cancelled"].includes(k),
                  )
                  .map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="p-start">Planned Start</Label>
              <Input id="p-start" type="date" {...register("planned_start")} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="p-end">Planned End</Label>
              <Input id="p-end" type="date" {...register("planned_end")} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="p-value">Contract Value (USD)</Label>
              <Input id="p-value" type="number" step="0.01" min="0" {...register("contract_value")} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="p-pm">Project Manager</Label>
              <Select id="p-pm" {...register("project_manager_id")}>
                <option value="">Unassigned</option>
                {users?.items
                  .filter((u) => ["admin", "project_manager"].includes(u.role))
                  .map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.full_name}
                    </option>
                  ))}
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="p-site">Site Address</Label>
              <Input id="p-site" {...register("site_address")} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="p-city">City</Label>
              <Input id="p-city" {...register("city")} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="p-desc">Description</Label>
            <Textarea id="p-desc" rows={2} {...register("description")} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : project ? "Save Changes" : "Create Project"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
