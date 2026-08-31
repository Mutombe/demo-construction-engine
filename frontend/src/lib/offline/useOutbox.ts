import { useCallback, useEffect, useState } from "react";
import { all, subscribe, type OutboxOperation } from "@/lib/offline/outbox";
import { drain } from "@/lib/offline/sync";

export interface OutboxState {
  online: boolean;
  waiting: OutboxOperation[];
  rejected: OutboxOperation[];
  sending: boolean;
  send: () => Promise<void>;
}

/** What is still on this device, and whether it can leave. */
export function useOutbox(): OutboxState {
  const [rows, setRows] = useState<OutboxOperation[]>([]);
  const [online, setOnline] = useState(() => navigator.onLine);
  const [sending, setSending] = useState(false);

  const reload = useCallback(() => {
    void all().then(setRows);
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
    } finally {
      setSending(false);
      reload();
    }
  }, [reload]);

  return {
    online,
    waiting: rows.filter((row) => row.status !== "rejected"),
    rejected: rows.filter((row) => row.status === "rejected"),
    sending,
    send,
  };
}
