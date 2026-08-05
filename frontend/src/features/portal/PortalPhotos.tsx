import { useQuery } from "@tanstack/react-query";
import { CaretLeft, CaretRight, ImageSquare, X } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { fetchPhotoUrl, fetchPhotos, type PortalPhoto } from "@/features/portal/api";

/** Loads one image through the portal token and hands back an object URL,
 *  revoking it on the way out so a long browse does not leak blobs. */
function usePhotoUrl(token: string, photoId: string | null, thumb: boolean) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!photoId) {
      setUrl(null);
      return;
    }
    let objectUrl: string | null = null;
    let cancelled = false;
    fetchPhotoUrl(token, photoId, thumb)
      .then((next) => {
        if (cancelled) {
          URL.revokeObjectURL(next);
          return;
        }
        objectUrl = next;
        setUrl(next);
      })
      .catch(() => setUrl(null));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [token, photoId, thumb]);

  return url;
}

function Thumbnail({
  token,
  photo,
  onOpen,
}: {
  token: string;
  photo: PortalPhoto;
  onOpen: () => void;
}) {
  const url = usePhotoUrl(token, photo.id, photo.has_thumbnail);

  return (
    <button
      type="button"
      onClick={onOpen}
      title={photo.caption ?? "Open photo"}
      className="group relative aspect-square overflow-hidden rounded-lg border bg-muted"
    >
      {url ? (
        <img
          src={url}
          alt={photo.caption ?? "Site photo"}
          loading="lazy"
          className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
        />
      ) : (
        <span className="flex h-full w-full items-center justify-center text-muted-foreground">
          <ImageSquare className="h-5 w-5" />
        </span>
      )}
      {photo.caption && (
        <span className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/70 to-transparent px-2 pb-1.5 pt-5 text-left text-[11px] text-white">
          {photo.caption}
        </span>
      )}
    </button>
  );
}

function Lightbox({
  token,
  photos,
  index,
  onClose,
  onMove,
}: {
  token: string;
  photos: PortalPhoto[];
  index: number;
  onClose: () => void;
  onMove: (next: number) => void;
}) {
  const photo = photos[index];
  const url = usePhotoUrl(token, photo?.id ?? null, false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") onMove(Math.min(index + 1, photos.length - 1));
      if (e.key === "ArrowLeft") onMove(Math.max(index - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, photos.length, onClose, onMove]);

  if (!photo) return null;

  return (
    <div
      className="fixed inset-0 z-[2200] flex items-center justify-center bg-black/85 p-4"
      onClick={onClose}
      role="presentation"
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        className="absolute right-4 top-4 rounded-md p-2 text-white/70 transition-colors hover:text-white"
      >
        <X className="h-5 w-5" />
      </button>
      {index > 0 && (
        <button
          type="button"
          aria-label="Previous"
          onClick={(e) => {
            e.stopPropagation();
            onMove(index - 1);
          }}
          className="absolute left-3 rounded-full bg-white/10 p-2 text-white transition-colors hover:bg-white/20"
        >
          <CaretLeft className="h-5 w-5" />
        </button>
      )}
      {index < photos.length - 1 && (
        <button
          type="button"
          aria-label="Next"
          onClick={(e) => {
            e.stopPropagation();
            onMove(index + 1);
          }}
          className="absolute right-3 rounded-full bg-white/10 p-2 text-white transition-colors hover:bg-white/20"
        >
          <CaretRight className="h-5 w-5" />
        </button>
      )}
      <figure className="max-h-full max-w-4xl" onClick={(e) => e.stopPropagation()}>
        {url ? (
          <img
            src={url}
            alt={photo.caption ?? "Site photo"}
            className="max-h-[80vh] w-auto rounded-lg object-contain"
          />
        ) : (
          <div className="flex h-64 w-64 items-center justify-center text-white/60">
            Loading…
          </div>
        )}
        {photo.caption && (
          <figcaption className="mt-3 text-center text-sm text-white/80">
            {photo.caption}
          </figcaption>
        )}
      </figure>
    </div>
  );
}

const dayLabel = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

const shortDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });

/** Progress photos, oldest day first, so scrolling reads as the build going up. */
export function PortalPhotos({ token, projectId }: { token: string; projectId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["portal-photos", token, projectId],
    queryFn: () => fetchPhotos(token, projectId),
    retry: false,
  });
  const [open, setOpen] = useState<number | null>(null);

  // Flattened in display order, so the lightbox arrows walk the whole build
  // rather than stopping at the end of a day.
  const flat = data?.days.flatMap((day) => day.photos) ?? [];

  if (isLoading) {
    return (
      <section>
        <SectionHeading />
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="aspect-square animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      </section>
    );
  }

  if (!data || data.total_photos === 0) {
    return (
      <section>
        <SectionHeading />
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed py-10 text-center">
          <ImageSquare className="h-6 w-6 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            No site photos have been shared yet
          </p>
        </div>
      </section>
    );
  }

  return (
    <section>
      <SectionHeading />
      <p className="mb-4 text-xs text-muted-foreground">
        {data.total_photos} {data.total_photos === 1 ? "photo" : "photos"}
        {data.first_photo && data.last_photo && (
          <>
            {" "}
            from {shortDate(data.first_photo)}
            {data.first_photo !== data.last_photo && <> to {shortDate(data.last_photo)}</>}
          </>
        )}
      </p>

      <div className="space-y-6">
        {data.days.map((day) => (
          <div key={day.day}>
            <div className="mb-2 flex items-center gap-3">
              <h3 className="text-xs font-medium text-foreground">{dayLabel(day.day)}</h3>
              <span className="h-px flex-1 bg-border" />
              <span className="text-[11px] text-muted-foreground">
                {day.photos.length} {day.photos.length === 1 ? "photo" : "photos"}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
              {day.photos.map((photo) => (
                <Thumbnail
                  key={photo.id}
                  token={token}
                  photo={photo}
                  onOpen={() => setOpen(flat.findIndex((p) => p.id === photo.id))}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      {open !== null && (
        <Lightbox
          token={token}
          photos={flat}
          index={open}
          onClose={() => setOpen(null)}
          onMove={setOpen}
        />
      )}
    </section>
  );
}

function SectionHeading() {
  return (
    <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
      Progress Photos
    </h2>
  );
}
