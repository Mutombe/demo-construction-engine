import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { processIngestionItem, uploadIngestionItem } from "@/lib/api/generated/endpoints";
import type { IngestionItemRead } from "@/lib/api/generated/model";
import { ACCEPTED_TYPES, MAX_UPLOAD_BYTES } from "@/features/ingestion/types";

const MAX_CONCURRENT = 3;

export interface PumpCard {
  localId: string;
  filename: string;
  objectUrl: string | null; // image thumbnail; null for PDFs
  isPdf: boolean;
  phase: "uploading" | "queued" | "processing" | "done" | "error";
  itemId?: string;
  item?: IngestionItemRead;
  duplicateIds: string[];
  error?: string;
}

function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}

let seq = 0;

/** Instant per-file cards; uploads immediately, then processes with ≤3 concurrent AI calls. */
export function useUploadPump(projectId?: string) {
  const [cards, setCards] = useState<PumpCard[]>([]);
  const inFlight = useRef(0);
  const queue = useRef<{ localId: string; itemId: string }[]>([]);
  const queryClient = useQueryClient();

  const patch = useCallback((localId: string, changes: Partial<PumpCard>) => {
    setCards((prev) => prev.map((c) => (c.localId === localId ? { ...c, ...changes } : c)));
  }, []);

  const pump = useCallback(() => {
    while (inFlight.current < MAX_CONCURRENT && queue.current.length > 0) {
      const next = queue.current.shift();
      if (!next) break;
      inFlight.current += 1;
      patch(next.localId, { phase: "processing" });
      processIngestionItem(next.itemId)
        .then((item) => {
          patch(next.localId, {
            phase: item.status === "failed" ? "error" : "done",
            item,
            error: item.error ?? undefined,
          });
        })
        .catch((err) => patch(next.localId, { phase: "error", error: errDetail(err) }))
        .finally(() => {
          inFlight.current -= 1;
          void queryClient.invalidateQueries();
          pump();
        });
    }
  }, [patch, queryClient]);

  const addFiles = useCallback(
    (files: File[]) => {
      for (const file of files) {
        if (!ACCEPTED_TYPES.includes(file.type)) {
          toast.error(`${file.name}: only JPEG, PNG, WebP and PDF are supported`);
          continue;
        }
        if (file.size > MAX_UPLOAD_BYTES) {
          toast.error(`${file.name}: exceeds the 15 MB limit`);
          continue;
        }
        const localId = `up-${++seq}`;
        const isPdf = file.type === "application/pdf";
        setCards((prev) => [
          {
            localId,
            filename: file.name,
            objectUrl: isPdf ? null : URL.createObjectURL(file),
            isPdf,
            phase: "uploading",
            duplicateIds: [],
          },
          ...prev,
        ]);
        uploadIngestionItem({ file, project_id: projectId || undefined })
          .then((res) => {
            patch(localId, {
              phase: "queued",
              itemId: res.item.id,
              item: res.item,
              duplicateIds: res.duplicate_ids,
            });
            queue.current.push({ localId, itemId: res.item.id });
            pump();
          })
          .catch((err) => patch(localId, { phase: "error", error: errDetail(err) }));
      }
    },
    [patch, projectId, pump],
  );

  const retry = useCallback(
    (localId: string) => {
      const card = cards.find((c) => c.localId === localId);
      if (!card?.itemId) return;
      patch(localId, { phase: "queued", error: undefined });
      queue.current.push({ localId, itemId: card.itemId });
      pump();
    },
    [cards, patch, pump],
  );

  const refreshCard = useCallback(
    (item: IngestionItemRead) => {
      setCards((prev) =>
        prev.map((c) => (c.itemId === item.id ? { ...c, item, phase: "done" } : c)),
      );
    },
    [],
  );

  const clearFinished = useCallback(() => {
    setCards((prev) =>
      prev.filter((c) => {
        const finished =
          c.phase === "done" && (c.item?.status === "posted" || c.item?.status === "rejected");
        if (finished && c.objectUrl) URL.revokeObjectURL(c.objectUrl);
        return !finished;
      }),
    );
  }, []);

  return { cards, addFiles, retry, refreshCard, clearFinished };
}
