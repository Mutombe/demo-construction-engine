import { Camera, ImageSquare } from "@phosphor-icons/react";
import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { CardListSkeleton } from "@/components/ui/skeleton";
import { useGetPhotoTimeline } from "@/lib/api/generated/endpoints";
import type { MediaRead } from "@/lib/api/generated/model";
import { fmtDate } from "@/lib/format";
import { useAuthedBlobUrl } from "./useAuthedBlobUrl";

function Thumb({ photo, onOpen }: { photo: MediaRead; onOpen: () => void }) {
  const url = useAuthedBlobUrl(
    photo.has_thumbnail ? `/api/v1/media/${photo.id}/thumbnail` : null,
  );
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group relative aspect-square overflow-hidden rounded-md border bg-muted/40"
      title={photo.caption ?? photo.original_filename}
    >
      {url ? (
        <img
          src={url}
          alt={photo.caption ?? ""}
          className="h-full w-full object-cover transition-transform group-hover:scale-105"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center">
          <ImageSquare className="size-6 text-muted-foreground" />
        </div>
      )}
      {photo.caption && (
        <span className="absolute inset-x-0 bottom-0 truncate bg-black/55 px-1.5 py-1 text-left text-[10px] text-white">
          {photo.caption}
        </span>
      )}
    </button>
  );
}

/** Site photos as a progress diary: newest day at the top, each day's photos
 *  in the order they were taken. */
export function PhotoTimeline({
  entityType,
  entityId,
}: {
  entityType: string;
  entityId: string;
}) {
  const { data, isLoading } = useGetPhotoTimeline({
    entity_type: entityType,
    entity_id: entityId,
  });
  const [viewing, setViewing] = useState<MediaRead | null>(null);
  const fullUrl = useAuthedBlobUrl(viewing ? `/api/v1/media/${viewing.id}/file` : null);

  if (isLoading || !data) {
    return <CardListSkeleton count={3} />;
  }
  if (data.total_photos === 0) {
    return (
      <div className="rounded-lg border">
        <EmptyState
          icon={<Camera />}
          title="No site photos yet"
          hint="Photos taken with the camera or uploaded to the Photos folder appear here as a day-by-day progress record."
        />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="text-sm text-muted-foreground">
        {data.total_photos} photo{data.total_photos === 1 ? "" : "s"}
        {data.first_photo && data.last_photo && (
          <> · {fmtDate(data.first_photo)} to {fmtDate(data.last_photo)}</>
        )}
      </div>

      {data.days.map((day) => (
        <div key={day.day} className="relative border-l pl-5">
          <span className="absolute -left-[5px] top-1.5 size-2.5 rounded-full bg-primary" />
          <div className="mb-2 flex items-baseline gap-2">
            <span className="text-sm font-medium">{fmtDate(day.day)}</span>
            <span className="text-xs text-muted-foreground">
              {day.photos.length} photo{day.photos.length === 1 ? "" : "s"}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-8">
            {day.photos.map((photo) => (
              <Thumb key={photo.id} photo={photo} onOpen={() => setViewing(photo)} />
            ))}
          </div>
        </div>
      ))}

      <Dialog open={!!viewing} onOpenChange={(open) => !open && setViewing(null)}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle className="truncate pr-8 text-sm">
              {viewing?.caption ?? viewing?.original_filename}
              {viewing && (
                <span className="ml-2 font-normal text-muted-foreground">
                  {fmtDate(viewing.created_at)}
                </span>
              )}
            </DialogTitle>
          </DialogHeader>
          <div className="flex max-h-[75vh] items-center justify-center overflow-hidden rounded-md bg-black/90">
            {fullUrl ? (
              <img src={fullUrl} alt="" className="max-h-[75vh] w-auto object-contain" />
            ) : (
              <div className="py-24 text-sm text-white/70">Loading…</div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
