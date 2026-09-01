import { useCallback, useEffect, useState } from "react";
import {
  all,
  allPhotos,
  subscribe,
  type OutboxOperation,
  type OutboxPhoto,
} from "@/lib/offline/outbox";
import { drain, drainPhotos } from "@/lib/offline/sync";

export interface OutboxState {
  online: boolean;
  waiting: OutboxOperation[];
  rejected: OutboxOperation[];
  photos: OutboxPhoto[];
  sending: boolean;
  send: () => Promise<void>;
}

/** What is still on this device, and whether it can leave. */
export function useOutbox(): OutboxState {
  const [rows, setRows] = useState<OutboxOperation[]>([]);
  const [photos, setPhotos] = useState<OutboxPhoto[]>([]);
  const [online, setOnline] = useState(() => navigator.onLine);
  const [sending, setSending] = useState(false);

  const reload = useCallback(() => {
    void all().then(setRows);
    void allPhotos().then(setPhotos);
  }, []);

  useEffect(() => {
    reload();
    const unsubscribe = subscribe(reload);
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      unsubscribe();
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, [reload]);

  const send = useCallback(async () => {
    setSending(true);
    try {
      await drain();
      await drainPhotos();
    } finally {
      setSending(false);
      reload();
    }
  }, [reload]);

  return {
    online,
    waiting: rows.filter((row) => row.status !== "rejected"),
    rejected: rows.filter((row) => row.status === "rejected"),
    photos,
    sending,
    send,
  };
}
