import { keepPreviousData, useQueryClient } from "@tanstack/react-query";
import {
  Camera,
  DownloadSimple,
  File as FileIcon,
  FileCsv,
  FileDoc,
  FilePdf,
  FileXls,
  Folder,
  Images,
  MagnifyingGlass,
  PencilSimple,
  Trash,
  UploadSimple,
} from "@phosphor-icons/react";
import { useRef, useState } from "react";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { confirmDialog } from "@/components/ui/confirm";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DEFAULT_PAGE_SIZE, PaginationBar } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
import { CardListSkeleton } from "@/components/ui/skeleton";
import { errDetail } from "@/lib/api/errors";
import {
  useDeleteMedia,
  useGetMediaFolderCounts,
  useListMedia,
  useUpdateMedia,
  useUploadMedia,
} from "@/lib/api/generated/endpoints";
import { MediaFolder, type MediaRead } from "@/lib/api/generated/model";
import { downloadFile } from "@/lib/api/download";
import { fmtDate } from "@/lib/format";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import { CameraCaptureDialog } from "./CameraCaptureDialog";
import { useAuthedBlobUrl } from "./useAuthedBlobUrl";

const FOLDER_LABELS: Record<MediaFolder, string> = {
  drawings: "Drawings",
  contracts: "Contracts",
  permits: "Permits",
  photos: "Photos",
  reports: "Reports",
  other: "Other",
};

function typeIcon(mediaType: string) {
  if (mediaType === "application/pdf") return <FilePdf />;
  if (mediaType.includes("wordprocessingml")) return <FileDoc />;
  if (mediaType.includes("spreadsheetml")) return <FileXls />;
  if (mediaType === "text/csv") return <FileCsv />;
  return <FileIcon />;
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function MediaCard({
  media,
  onEdit,
  onDelete,
}: {
  media: MediaRead;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const thumbUrl = useAuthedBlobUrl(
    media.has_thumbnail ? `/api/v1/media/${media.id}/thumbnail` : null,
  );
  const [previewOpen, setPreviewOpen] = useState(false);
  const fullUrl = useAuthedBlobUrl(
    previewOpen ? `/api/v1/media/${media.id}/file` : null,
  );
  const saving = (media as { __saving?: boolean }).__saving;

  return (
    <div
      className={cn(
        "group flex flex-col overflow-hidden rounded-lg border bg-card transition-shadow hover:shadow-md",
        saving && "animate-pulse opacity-70",
      )}
    >
      <button
        type="button"
        className="relative flex h-32 w-full items-center justify-center overflow-hidden bg-muted/40 [&_svg]:size-9 [&_svg]:text-muted-foreground"
        title={media.has_thumbnail ? "Preview" : "Download"}
        onClick={() => {
          if (media.has_thumbnail) setPreviewOpen(true);
          else
            void downloadFile(`/api/v1/media/${media.id}/file`, media.original_filename).catch(
              () => toast.error("Download failed"),
            );
        }}
      >
        {media.has_thumbnail ? (
          thumbUrl ? (
            <img
              src={thumbUrl}
              alt={media.caption ?? media.original_filename}
              className="h-full w-full object-cover transition-transform group-hover:scale-105"
            />
          ) : (
            <Images />
          )
        ) : (
          typeIcon(media.media_type)
        )}
      </button>
      <div className="flex flex-1 flex-col gap-1 p-2.5">
        <div className="truncate text-xs font-medium" title={media.original_filename}>
          {media.original_filename}
        </div>
        {media.caption && (
          <div className="line-clamp-2 text-xs text-muted-foreground" title={media.caption}>
            {media.caption}
          </div>
        )}
        <div className="mt-auto flex items-center justify-between pt-1">
          <span className="text-[10px] text-muted-foreground">
            {fmtSize(media.file_size)} · {fmtDate(media.created_at)}
          </span>
          <div className="flex opacity-0 transition-opacity group-hover:opacity-100">
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              title="Download"
              onClick={() =>
                void downloadFile(`/api/v1/media/${media.id}/file`, media.original_filename).catch(
                  () => toast.error("Download failed"),
                )
              }
            >
              <DownloadSimple className="size-3.5" />
            </Button>
            <Can perm="media:write">
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                title="Edit details"
                onClick={onEdit}
              >
                <PencilSimple className="size-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 text-destructive"
                title="Delete"
                onClick={onDelete}
              >
                <Trash className="size-3.5" />
              </Button>
            </Can>
          </div>
        </div>
      </div>

      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="truncate pr-8 text-sm">
              {media.caption ?? media.original_filename}
            </DialogTitle>
          </DialogHeader>
          <div className="flex max-h-[70vh] items-center justify-center overflow-hidden rounded-md bg-black/90">
            {fullUrl ? (
              <img src={fullUrl} alt="" className="max-h-[70vh] w-auto object-contain" />
            ) : (
              <div className="py-24 text-sm text-white/70">Loading…</div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** Reusable document/photo library for any attachable entity.
 *  Renders folder chips with counts, search, grid with previews, upload from
 *  disk and straight from the device camera. */
export function MediaPanel({
  entityType,
  entityId,
  defaultFolder,
}: {
  entityType: string;
  entityId: string;
  defaultFolder?: MediaFolder;
}) {
  const queryClient = useQueryClient();
  const [folder, setFolder] = useState<MediaFolder | "all">(defaultFolder ?? "all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [editing, setEditing] = useState<MediaRead | null>(null);

  const { data: counts } = useGetMediaFolderCounts({
    entity_type: entityType,
    entity_id: entityId,
  });
  const { data: pageData, isLoading } = useListMedia(
    {
      entity_type: entityType,
      entity_id: entityId,
      folder: folder === "all" ? undefined : folder,
      search: search || undefined,
      page,
      page_size: DEFAULT_PAGE_SIZE,
    },
    { query: { placeholderData: keepPreviousData } },
  );

  const invalidate = () =>
    queryClient.invalidateQueries({
      predicate: (q) => String(q.queryKey[0] ?? "").startsWith("/api/v1/media"),
    });

  const uploadMutation = useUploadMedia();
  const updateMutation = useUpdateMedia();
  const deleteMutation = useDeleteMedia();

  const upload = async (file: File, uploadFolder: MediaFolder, caption: string | null) => {
    await uploadMutation.mutateAsync({
      data: {
        file,
        entity_type: entityType,
        entity_id: entityId,
        folder: uploadFolder,
        caption: caption ?? undefined,
      },
    });
  };

  const onFilesPicked = async (files: FileList | null) => {
    if (!files?.length) return;
    const targetFolder = folder === "all" ? MediaFolder.other : folder;
    let uploaded = 0;
    for (const file of Array.from(files)) {
      try {
        await upload(file, targetFolder, null);
        uploaded += 1;
      } catch (err) {
        toast.error(`${file.name}: ${errDetail(err)}`);
      }
    }
    if (uploaded > 0) {
      toast.success(
        uploaded === 1 ? "File uploaded" : `${uploaded} files uploaded`,
      );
      await invalidate();
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const onCapture = async (file: File, caption: string | null) => {
    try {
      await upload(file, MediaFolder.photos, caption);
      toast.success("Photo added");
      setCameraOpen(false);
      setFolder((f) => (f === "all" ? f : MediaFolder.photos));
      await invalidate();
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const onDelete = async (media: MediaRead) => {
    if (
      !(await confirmDialog({
        title: "Delete file",
        message: `Delete "${media.original_filename}"? This cannot be undone.`,
        tone: "danger",
      }))
    )
      return;
    try {
      await deleteMutation.mutateAsync({ mediaId: media.id });
      toast.success("File deleted");
      await invalidate();
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const items = pageData?.items ?? [];
  const total = counts?.total ?? 0;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => {
            setFolder("all");
            setPage(1);
          }}
          className={cn(
            "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
            folder === "all"
              ? "border-primary bg-primary text-primary-foreground"
              : "text-muted-foreground hover:border-border hover:text-foreground",
          )}
        >
          All {total > 0 && <span className="opacity-70">({total})</span>}
        </button>
        {Object.values(MediaFolder).map((f) => {
          const count = counts?.counts?.[f] ?? 0;
          return (
            <button
              key={f}
              type="button"
              onClick={() => {
                setFolder(f);
                setPage(1);
              }}
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                folder === f
                  ? "border-primary bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:border-border hover:text-foreground",
              )}
            >
              {FOLDER_LABELS[f]} {count > 0 && <span className="opacity-70">({count})</span>}
            </button>
          );
        })}
        <div className="ml-auto flex items-center gap-2">
          <div className="relative">
            <MagnifyingGlass className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search files…"
              className="h-8 w-44 pl-8 text-xs"
            />
          </div>
          <Can perm="media:write">
            <Button variant="outline" size="sm" onClick={() => setCameraOpen(true)}>
              <Camera /> Take Photo
            </Button>
            <Button
              size="sm"
              disabled={uploadMutation.isPending}
              onClick={() => fileInputRef.current?.click()}
            >
              <UploadSimple /> {uploadMutation.isPending ? "Uploading…" : "Upload"}
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="image/jpeg,image/png,image/webp,image/gif,application/pdf,.docx,.xlsx,.csv,.txt"
              className="hidden"
              onChange={(e) => void onFilesPicked(e.target.files)}
            />
          </Can>
        </div>
      </div>

      {isLoading && !pageData ? (
        <CardListSkeleton count={8} />
      ) : items.length === 0 ? (
        <div className="rounded-lg border">
          <EmptyState
            icon={<Folder />}
            title={
              folder === "all" && !search
                ? "No files yet"
                : "No files match this view"
            }
            hint={
              folder === "all" && !search
                ? "Upload drawings, contracts and site photos — or take a photo straight from the device camera."
                : "Try another folder or clear the search."
            }
          />
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {items.map((m) => (
            <MediaCard
              key={m.id}
              media={m}
              onEdit={() => setEditing(m)}
              onDelete={() => void onDelete(m)}
            />
          ))}
        </div>
      )}
      <PaginationBar
        page={page}
        pageSize={DEFAULT_PAGE_SIZE}
        total={pageData?.total}
        onPageChange={setPage}
      />

      <CameraCaptureDialog
        open={cameraOpen}
        onOpenChange={setCameraOpen}
        onCapture={onCapture}
        uploading={uploadMutation.isPending}
      />

      <EditMediaDialog
        media={editing}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
        onSave={async (mediaId, caption, newFolder) => {
          try {
            await updateMutation.mutateAsync({
              mediaId,
              data: { caption, folder: newFolder },
            });
            toast.success("File updated");
            setEditing(null);
            await invalidate();
          } catch (err) {
            toast.error(errDetail(err));
          }
        }}
        saving={updateMutation.isPending}
      />
    </div>
  );
}

function EditMediaDialog({
  media,
  onOpenChange,
  onSave,
  saving,
}: {
  media: MediaRead | null;
  onOpenChange: (open: boolean) => void;
  onSave: (mediaId: string, caption: string, folder: MediaFolder) => Promise<void>;
  saving: boolean;
}) {
  const [caption, setCaption] = useState("");
  const [folder, setFolder] = useState<MediaFolder>(MediaFolder.other);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);

  if (media && loadedFor !== media.id) {
    setCaption(media.caption ?? "");
    setFolder(media.folder ?? MediaFolder.other);
    setLoadedFor(media.id);
  }

  return (
    <Dialog open={!!media} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Edit File Details</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Caption</Label>
            <Input
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              maxLength={255}
              placeholder="What is this file?"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Folder</Label>
            <Select
              value={folder}
              onChange={(e) => setFolder(e.target.value as MediaFolder)}
            >
              {Object.values(MediaFolder).map((f) => (
                <option key={f} value={f}>
                  {FOLDER_LABELS[f]}
                </option>
              ))}
            </Select>
          </div>
          {media && (
            <div className="text-xs text-muted-foreground">
              <Badge variant="outline" className="mr-1.5">
                {media.media_type.split("/").pop()}
              </Badge>
              {media.original_filename}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={saving}
            onClick={() => media && void onSave(media.id, caption, folder)}
          >
            {saving ? "Saving…" : "Save Changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
