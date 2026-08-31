/** Draining the outbox when there is signal again.
 *
 *  The send is one request carrying the whole backlog, and it is safe to
 *  repeat: the server matches on the id each capture was born with and hands
 *  back what already happened rather than writing it twice. So the failure
 *  mode of a flaky connection is a wasted request, never a duplicated diary.
 */

import { api } from "@/lib/api/axios";
import { deviceId, markRejected, pending, remove, subscribe } from "@/lib/offline/outbox";

export interface SyncResult {
  client_op_id: string;
  status: "applied" | "merged" | "duplicate" | "rejected";
  entity_type: string | null;
  entity_id: string | null;
  detail: string | null;
}

export interface SyncSummary {
  applied: number;
  merged: number;
  duplicate: number;
  rejected: number;
  results: SyncResult[];
}

let running = false;

export function isSyncing(): boolean {
  return running;
}

/** Push everything waiting. Returns null when there was nothing to send or
 *  the network refused the whole request, which is not an error worth
 *  shouting about — it just means try again later. */
export async function drain(): Promise<SyncSummary | null> {
  if (running || !navigator.onLine) return null;
  const queued = await pending();
  if (!queued.length) return null;

  running = true;
  try {
    const { data } = await api.post<SyncSummary>("/api/v1/sync/push", {
      device_id: deviceId(),
      operations: queued.map((op) => ({
        client_op_id: op.client_op_id,
        op_type: op.op_type,
        payload: op.payload,
        captured_at: op.captured_at,
      })),
    });

    for (const result of data.results) {
      if (result.status === "rejected") {
        // Kept on the device with the reason, so the person who wrote it can
        // see what did not land instead of finding the gap at month end.
        await markRejected(result.client_op_id, result.detail ?? "Refused");
      } else {
        await remove(result.client_op_id);
      }
    }
    return data;
  } catch {
    return null;
  } finally {
    running = false;
  }
}

/** Try whenever the connection comes back, and periodically in case it came
 *  back without the browser saying so — which on a site radio it often does. */
export function startSyncLoop(): () => void {
  const attempt = () => {
    void drain();
  };
  window.addEventListener("online", attempt);
  const timer = window.setInterval(attempt, 60_000);
  const unsubscribe = subscribe(attempt);
  attempt();

  return () => {
    window.removeEventListener("online", attempt);
    window.clearInterval(timer);
    unsubscribe();
  };
}
