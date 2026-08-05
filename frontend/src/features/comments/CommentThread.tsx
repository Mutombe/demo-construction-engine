import { useQueryClient } from "@tanstack/react-query";
import { ChatCircleDots, PaperPlaneRight, PencilSimple, Trash } from "@phosphor-icons/react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { confirmDialog } from "@/components/ui/confirm";
import { EmptyState } from "@/components/ui/empty-state";
import { Textarea } from "@/components/ui/textarea";
import { useAuthStore } from "@/features/auth/store";
import { errDetail } from "@/lib/api/errors";
import {
  useCreateComment,
  useDeleteComment,
  useListComments,
  useUpdateComment,
} from "@/lib/api/generated/endpoints";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

const COMMENTS_KEY = ["/api/v1/comments"];

/** Relative for anything recent, absolute once it stops being "the other day". */
function whenLabel(iso: string): string {
  const then = new Date(iso);
  const minutes = Math.round((Date.now() - then.getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)}h ago`;
  if (minutes < 60 * 24 * 7) return `${Math.round(minutes / (60 * 24))}d ago`;
  return then.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function initials(name: string | null | undefined): string {
  if (!name) return "?";
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function CommentThread({
  entityType,
  entityId,
  className,
}: {
  entityType: string;
  entityId: string;
  className?: string;
}) {
  const queryClient = useQueryClient();
  const { data: comments, isLoading } = useListComments({
    entity_type: entityType,
    entity_id: entityId,
  });
  const create = useCreateComment();
  const update = useUpdateComment();
  const remove = useDeleteComment();
  const me = useAuthStore((s) => s.user);

  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");

  const refresh = () => queryClient.invalidateQueries({ queryKey: COMMENTS_KEY });

  const send = async () => {
    const body = draft.trim();
    if (!body) return;
    try {
      await create.mutateAsync({
        params: { entity_type: entityType, entity_id: entityId },
        data: { body },
      });
      setDraft("");
      await refresh();
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const saveEdit = async (commentId: string) => {
    const body = editDraft.trim();
    if (!body) return;
    try {
      await update.mutateAsync({ commentId, data: { body } });
      setEditing(null);
      await refresh();
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const del = async (commentId: string) => {
    if (
      !(await confirmDialog({
        title: "Delete comment",
        message: "This removes it from the thread for everyone.",
        confirmLabel: "Delete",
        tone: "danger",
      }))
    )
      return;
    try {
      await remove.mutateAsync({ commentId });
      await refresh();
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <div className={cn("space-y-4", className)}>
      {isLoading && !comments && (
        <div className="space-y-3">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="flex gap-3">
              <div className="h-8 w-8 shrink-0 animate-pulse rounded-full bg-muted" />
              <div className="flex-1 space-y-1.5">
                <div className="h-3 w-32 animate-pulse rounded bg-muted" />
                <div className="h-3 w-full animate-pulse rounded bg-muted" />
              </div>
            </div>
          ))}
        </div>
      )}

      {comments && comments.length === 0 && (
        <EmptyState
          icon={<ChatCircleDots />}
          title="No comments yet"
          hint="Anything written here stays attached to this record."
        />
      )}

      {comments && comments.length > 0 && (
        <ol className="space-y-4">
          {comments.map((comment) => {
            const mine = comment.author_id === me?.id;
            return (
              <li key={comment.id} className="flex gap-3">
                <span
                  className={cn(
                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-medium",
                    mine ? "bg-primary/10 text-primary" : "bg-secondary text-secondary-foreground",
                  )}
                >
                  {initials(comment.author_name)}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-2">
                    <span className="text-sm font-medium">
                      {comment.author_name ?? "Removed user"}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {whenLabel(comment.created_at)}
                      {comment.edited_at && " · edited"}
                    </span>
                    {comment.can_edit && editing !== comment.id && (
                      <span className="ml-auto flex gap-0.5">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6"
                          title="Edit"
                          onClick={() => {
                            setEditing(comment.id);
                            setEditDraft(comment.body);
                          }}
                        >
                          <PencilSimple />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6 text-destructive"
                          title="Delete"
                          onClick={() => void del(comment.id)}
                        >
                          <Trash />
                        </Button>
                      </span>
                    )}
                  </div>

                  {editing === comment.id ? (
                    <div className="mt-1.5 space-y-2">
                      <Textarea
                        rows={3}
                        value={editDraft}
                        onChange={(e) => setEditDraft(e.target.value)}
                      />
                      <div className="flex gap-2">
                        <Button size="sm" onClick={() => void saveEdit(comment.id)}>
                          Save
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => setEditing(null)}>
                          Cancel
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <p className="mt-0.5 whitespace-pre-wrap text-sm leading-relaxed">
                      {comment.body}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}

      <div className="flex items-end gap-2 border-t pt-4">
        <Textarea
          rows={2}
          value={draft}
          placeholder="Write a comment"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            // Enter sends, Shift+Enter breaks the line: the shape people expect
            // from every other message box.
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <Button
          disabled={!draft.trim() || create.isPending}
          title="Send (Enter)"
          onClick={() => void send()}
        >
          <PaperPlaneRight />
        </Button>
      </div>
    </div>
  );
}
