import { useQueryClient } from "@tanstack/react-query";
import { ChatCircle, Diamond, ListChecks, Warning } from "@phosphor-icons/react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { useUpdateTask } from "@/lib/api/generated/endpoints";
import type { TaskListItem } from "@/lib/api/generated/model";
import { errDetail } from "@/lib/api/errors";
import { fmtDate } from "@/lib/format";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

/** Cancelled is deliberately not a column. It is an outcome, not a stage, and
 *  giving it a lane invites people to park work there instead of deciding. */
const COLUMNS = [
  { status: "not_started", label: "To Do" },
  { status: "in_progress", label: "In Progress" },
  { status: "blocked", label: "Blocked" },
  { status: "done", label: "Done" },
] as const;

const PRIORITY_STYLE: Record<string, string> = {
  urgent: "bg-destructive/10 text-destructive",
  high: "bg-warning/15 text-warning",
  normal: "",
  low: "text-muted-foreground",
};

function TaskCard({
  task,
  onOpen,
  draggable,
  onDragStart,
}: {
  task: TaskListItem;
  onOpen: (task: TaskListItem) => void;
  draggable: boolean;
  onDragStart: (id: string) => void;
}) {
  const overdue =
    task.planned_end && task.status !== "done" && new Date(task.planned_end) < new Date();

  return (
    <button
      type="button"
      draggable={draggable}
      onDragStart={() => onDragStart(task.id)}
      onClick={() => onOpen(task)}
      className={cn(
        "w-full rounded-lg border bg-card p-2.5 text-left shadow-sm transition-shadow hover:shadow-md",
        draggable && "cursor-grab active:cursor-grabbing",
      )}
    >
      <div className="flex items-start gap-1.5">
        {task.is_milestone && (
          <Diamond className="mt-0.5 size-3 shrink-0 text-primary" weight="fill" />
        )}
        <span className="flex-1 text-sm leading-snug">{task.name}</span>
      </div>

      {(task.tags ?? []).length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {(task.tags ?? []).slice(0, 3).map((tag) => (
            <span
              key={tag}
              className="rounded bg-secondary px-1.5 py-0.5 text-[10px] text-secondary-foreground"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-muted-foreground">
        {task.priority !== "normal" && (
          <span className={cn("rounded px-1.5 py-0.5 font-medium", PRIORITY_STYLE[task.priority ?? "normal"])}>
            {task.priority}
          </span>
        )}
        {task.assignee_name && <span className="truncate">{task.assignee_name}</span>}
        {task.planned_end && (
          <span className={cn(overdue && "font-medium text-destructive")}>
            {overdue && <Warning className="mr-0.5 inline size-3" />}
            {fmtDate(task.planned_end)}
          </span>
        )}
        {(task.subtask_count ?? 0) > 0 && (
          <Tooltip content={`${task.subtasks_done} of ${task.subtask_count} subtasks done`}>
            <span className="flex items-center gap-0.5">
              <ListChecks className="size-3" />
              {task.subtasks_done}/{task.subtask_count}
            </span>
          </Tooltip>
        )}
        {(task.comment_count ?? 0) > 0 && (
          <span className="flex items-center gap-0.5">
            <ChatCircle className="size-3" />
            {task.comment_count}
          </span>
        )}
      </div>
    </button>
  );
}

/** Drag a card to a column to change its status. The board only ever writes
 *  status — everything else stays in the task form, so a mis-drop is one
 *  drag to undo rather than a lost edit. */
export function TaskBoard({
  tasks,
  canWrite,
  onOpen,
}: {
  tasks: TaskListItem[];
  canWrite: boolean;
  onOpen: (task: TaskListItem) => void;
}) {
  const queryClient = useQueryClient();
  const update = useUpdateTask();
  const [dragging, setDragging] = useState<string | null>(null);
  const [over, setOver] = useState<string | null>(null);

  const drop = async (status: string) => {
    const id = dragging;
    setDragging(null);
    setOver(null);
    if (!id) return;
    const task = tasks.find((t) => t.id === id);
    if (!task || task.status === status) return;
    try {
      await update.mutateAsync({ taskId: id, data: { status: status as never } });
      await queryClient.invalidateQueries();
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {COLUMNS.map((column) => {
        const inColumn = tasks.filter((t) => t.status === column.status);
        return (
          <div
            key={column.status}
            onDragOver={(e) => {
              if (!canWrite) return;
              e.preventDefault();
              setOver(column.status);
            }}
            onDragLeave={() => setOver((c) => (c === column.status ? null : c))}
            onDrop={() => void drop(column.status)}
            className={cn(
              "rounded-lg border bg-muted/30 p-2 transition-colors",
              over === column.status && "border-primary bg-primary/5",
            )}
          >
            <div className="mb-2 flex items-center justify-between px-1">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {column.label}
              </h3>
              <Badge variant="outline">{inColumn.length}</Badge>
            </div>
            <div className="space-y-2">
              {inColumn.map((task) => (
                <TaskCard
                  key={task.id}
                  task={task}
                  onOpen={onOpen}
                  draggable={canWrite}
                  onDragStart={setDragging}
                />
              ))}
              {inColumn.length === 0 && (
                <p className="px-1 py-6 text-center text-xs text-muted-foreground">
                  Nothing here
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
