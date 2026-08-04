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
import {
  useAddDependency,
  useCreateTask,
  useListPhases,
  useListUsers,
  useRemoveDependency,
  useUpdateTask,
} from "@/lib/api/generated/endpoints";
import type { TaskListItem } from "@/lib/api/generated/model";
import { usePermission } from "@/features/auth/hooks";
import { STATUS_LABELS } from "@/lib/format";

const schema = z.object({
  name: z.string().min(1, "Required"),
  wbs_code: z.string().optional(),
  phase_id: z.string().optional(),
  assignee_id: z.string().optional(),
  status: z.enum(["not_started", "in_progress", "blocked", "done", "cancelled"]),
  progress_pct: z.number().int().min(0).max(100),
  planned_start: z.string().optional(),
  planned_end: z.string().optional(),
  is_milestone: z.boolean().optional(),
  predecessor_id: z.string().optional(),
});
type FormValues = z.infer<typeof schema>;

export function TaskFormDialog({
  open,
  onOpenChange,
  projectId,
  task,
  allTasks,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  task?: TaskListItem | null;
  allTasks: TaskListItem[];
}) {
  const queryClient = useQueryClient();
  const isAdmin = usePermission("users:manage");
  const { data: phases } = useListPhases(projectId, { query: { enabled: open } });
  const { data: users } = useListUsers(
    { page_size: 200 },
    { query: { enabled: open && isAdmin } },
  );
  const createMutation = useCreateTask();
  const updateMutation = useUpdateTask();
  const addDep = useAddDependency();
  const removeDep = useRemoveDependency();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  useEffect(() => {
    if (open) {
      reset({
        name: task?.name ?? "",
        wbs_code: task?.wbs_code ?? "",
        phase_id: task?.phase_id ?? "",
        assignee_id: task?.assignee_id ?? "",
        status: (task?.status as FormValues["status"]) ?? "not_started",
        progress_pct: task?.progress_pct ?? 0,
        planned_start: task?.planned_start ?? "",
        planned_end: task?.planned_end ?? "",
        is_milestone: task?.is_milestone ?? false,
        predecessor_id: task?.predecessor_ids?.[0] ?? "",
      });
    }
  }, [open, task, reset]);

  const onSubmit = async (values: FormValues) => {
    const payload = {
      name: values.name,
      wbs_code: values.wbs_code || null,
      phase_id: values.phase_id || null,
      assignee_id: values.assignee_id || null,
      status: values.status,
      progress_pct: values.progress_pct,
      planned_start: values.planned_start || null,
      planned_end: values.planned_end || null,
      is_milestone: values.is_milestone ?? false,
    };
    try {
      let taskId = task?.id;
      if (task) {
        await updateMutation.mutateAsync({ taskId: task.id, data: payload });
      } else {
        const created = await createMutation.mutateAsync({ projectId, data: payload });
        taskId = created.id;
      }

      // Single-predecessor convenience wiring from the dialog
      const prevPred = task?.predecessor_ids?.[0];
      const nextPred = values.predecessor_id || undefined;
      if (taskId && prevPred !== nextPred) {
        if (prevPred) {
          await removeDep.mutateAsync({ taskId, predecessorId: prevPred });
        }
        if (nextPred) {
          await addDep.mutateAsync({ taskId, data: { predecessor_id: nextPred } });
        }
      }

      toast.success(task ? "Task updated" : "Task created");
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
  const candidatePredecessors = allTasks.filter((t) => t.id !== task?.id);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{task ? "Edit Task" : "New Task"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-4 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="t-wbs">WBS</Label>
              <Input id="t-wbs" placeholder="2.3" {...register("wbs_code")} />
            </div>
            <div className="col-span-3 space-y-1.5">
              <Label htmlFor="t-name">Task Name</Label>
              <Input id="t-name" {...register("name")} />
              {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="t-phase">Phase</Label>
              <Select id="t-phase" {...register("phase_id")}>
                <option value="">No phase</option>
                {phases?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.sequence}. {p.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="t-assignee">Assignee</Label>
              <Select id="t-assignee" {...register("assignee_id")}>
                <option value="">Unassigned</option>
                {users?.items.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="t-status">Status</Label>
              <Select id="t-status" {...register("status")}>
                {["not_started", "in_progress", "blocked", "done", "cancelled"].map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABELS[s]}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="t-progress">Progress %</Label>
              <Input
                id="t-progress"
                type="number"
                min={0}
                max={100}
                {...register("progress_pct", { valueAsNumber: true })}
              />
            </div>
            <div className="flex items-end gap-2 pb-2">
              <input id="t-milestone" type="checkbox" {...register("is_milestone")} />
              <Label htmlFor="t-milestone">Milestone</Label>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="t-start">Planned Start</Label>
              <Input id="t-start" type="date" {...register("planned_start")} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="t-end">Planned End</Label>
              <Input id="t-end" type="date" {...register("planned_end")} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="t-pred">Depends On (Predecessor)</Label>
            <Select id="t-pred" {...register("predecessor_id")}>
              <option value="">No dependency</option>
              {candidatePredecessors.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.wbs_code ? `${t.wbs_code} · ` : ""}
                  {t.name}
                </option>
              ))}
            </Select>
            <p className="text-xs text-muted-foreground">
              The schedule rejects dependencies that would create a cycle.
            </p>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : task ? "Save Changes" : "Create Task"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
