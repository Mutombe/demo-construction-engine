import { useQueryClient } from "@tanstack/react-query";
import { Link, createFileRoute } from "@tanstack/react-router";
import { Diamond, PencilSimple, Plus, Trash } from "@phosphor-icons/react";
import { useState } from "react";
import { toast } from "@/lib/toast";
import { Can } from "@/components/layout/Can";
import { Button } from "@/components/ui/button";
import { confirmDialog } from "@/components/ui/confirm";
import { Progress } from "@/components/ui/progress";
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
import { usePermission } from "@/features/auth/hooks";
import { WorkStatusBadge } from "@/features/projects/StatusBadge";
import { TaskBoard } from "@/features/tasks/TaskBoard";
import { TaskFormDialog } from "@/features/tasks/TaskFormDialog";
import {
  useDeleteTask,
  useListProjectTags,
  useListTasks,
  useUpdateTask,
} from "@/lib/api/generated/endpoints";
import type { TaskListItem } from "@/lib/api/generated/model";
import { fmtDate, STATUS_LABELS } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/projects/$projectId/tasks")({
  component: TasksTab,
});

function TasksTab() {
  const { projectId } = Route.useParams();
  const queryClient = useQueryClient();
  const { data: tasks, isLoading } = useListTasks(projectId);
  const updateMutation = useUpdateTask();
  const deleteMutation = useDeleteTask();
  const canWrite = usePermission("task:write");

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<TaskListItem | null>(null);
  const [view, setView] = useState<"board" | "list">("board");
  const [priority, setPriority] = useState("");
  const [tag, setTag] = useState("");
  const { data: projectTags } = useListProjectTags(projectId);

  const today = new Date().toISOString().slice(0, 10);

  const quickUpdate = async (task: TaskListItem, patch: Record<string, unknown>) => {
    try {
      await updateMutation.mutateAsync({ taskId: task.id, data: patch });
      await queryClient.invalidateQueries();
    } catch {
      toast.error("Update failed");
    }
  };

  const handleDelete = async (task: TaskListItem) => {
    if (
      !(await confirmDialog({
        title: "Delete task",
        message: `Delete task "${task.name}"? This also removes its dependencies.`,
        tone: "danger",
      }))
    )
      return;
    try {
      await deleteMutation.mutateAsync({ taskId: task.id });
      await queryClient.invalidateQueries();
      toast.success("Task deleted");
    } catch {
      toast.error("Delete failed");
    }
  };

  const openEditor = (task: TaskListItem) => {
    setEditing(task);
    setDialogOpen(true);
  };

  const visible = (tasks ?? []).filter(
    (task) =>
      (priority === "" || task.priority === priority) &&
      (tag === "" || (task.tags ?? []).includes(tag)),
  );

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex rounded-md border p-0.5">
          {(["board", "list"] as const).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setView(option)}
              className={cn(
                "rounded px-2.5 py-1 text-xs font-medium capitalize transition-colors",
                view === option
                  ? "bg-secondary text-secondary-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {option}
            </button>
          ))}
        </div>
        <Select className="w-40" value={priority} onChange={(e) => setPriority(e.target.value)}>
          <option value="">Any priority</option>
          <option value="urgent">Urgent</option>
          <option value="high">High</option>
          <option value="normal">Normal</option>
          <option value="low">Low</option>
        </Select>
        {projectTags && projectTags.length > 0 && (
          <Select className="w-40" value={tag} onChange={(e) => setTag(e.target.value)}>
            <option value="">Any tag</option>
            {projectTags.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </Select>
        )}
        <Can perm="task:write">
          <Button
            className="ml-auto"
            onClick={() => {
              setEditing(null);
              setDialogOpen(true);
            }}
          >
            <Plus /> New Task
          </Button>
        </Can>
      </div>

      {view === "board" && (
        <TaskBoard tasks={visible} canWrite={canWrite} onOpen={openEditor} />
      )}

      <div className={cn("rounded-lg border bg-card", view !== "list" && "hidden")}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-16">WBS</TableHead>
              <TableHead>Task</TableHead>
              <TableHead>Phase</TableHead>
              <TableHead>Assignee</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-36">Progress</TableHead>
              <TableHead>Due</TableHead>
              {canWrite && <TableHead className="w-20" />}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && <TableSkeleton columns={canWrite ? 8 : 7} rows={6} />}
            {!isLoading && visible.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="py-10 text-center text-muted-foreground">
                  No tasks yet.
                </TableCell>
              </TableRow>
            )}
            {visible.map((task) => {
              const isOverdue =
                task.planned_end &&
                task.planned_end < today &&
                !["done", "cancelled"].includes(task.status ?? "");
              return (
                <TableRow key={task.id}>
                  <TableCell className="font-mono text-xs">{task.wbs_code ?? "—"}</TableCell>
                  <TableCell>
                    <span className="flex items-center gap-1.5 font-medium">
                      {task.is_milestone && <Diamond className="h-3 w-3 text-primary" />}
                      <Link
                        to="/tasks/$taskId"
                        params={{ taskId: task.id }}
                        className="underline-offset-2 hover:text-primary hover:underline"
                      >
                        {task.name}
                      </Link>
                    </span>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {task.phase_name ?? "—"}
                  </TableCell>
                  <TableCell className="text-sm">{task.assignee_name ?? "—"}</TableCell>
                  <TableCell>
                    {canWrite ? (
                      <Select
                        className="h-7 w-32 text-xs"
                        value={task.status ?? "not_started"}
                        onChange={(e) => void quickUpdate(task, { status: e.target.value })}
                      >
                        {["not_started", "in_progress", "blocked", "done", "cancelled"].map(
                          (s) => (
                            <option key={s} value={s}>
                              {STATUS_LABELS[s]}
                            </option>
                          ),
                        )}
                      </Select>
                    ) : (
                      <WorkStatusBadge status={task.status ?? "not_started"} />
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Progress value={task.progress_pct ?? 0} className="flex-1" />
                      <span className="w-8 text-right text-xs text-muted-foreground">
                        {task.progress_pct}%
                      </span>
                    </div>
                  </TableCell>
                  <TableCell
                    className={cn(
                      "whitespace-nowrap text-sm",
                      isOverdue && "font-medium text-destructive",
                    )}
                  >
                    {fmtDate(task.planned_end)}
                  </TableCell>
                  {canWrite && (
                    <TableCell>
                      <div className="flex gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() => {
                            setEditing(task);
                            setDialogOpen(true);
                          }}
                        >
                          <PencilSimple className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive"
                          onClick={() => void handleDelete(task)}
                        >
                          <Trash className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  )}
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <TaskFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        projectId={projectId}
        task={editing}
        allTasks={tasks ?? []}
      />
    </div>
  );
}
