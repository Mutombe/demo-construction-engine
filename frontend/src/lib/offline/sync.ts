/** Draining the outbox when there is signal again.
 *
 *  The send is one request carrying the whole backlog, and it is safe to
 *  repeat: the server matches on the id each capture was born with and hands
 *  back what already happened rather than writing it twice. So the failure
 *  mode of a flaky connection is a wasted request, never a duplicated diary.
 */

import { api } from "@/lib/api/axios";
import {
  allPhotos,
  deviceId,
  markRejected,
  notePhotoFailure,
  pending,
  remove,
  removePhoto,
  subscribe,
} from "@/lib/offline/outbox";

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
    void drain().then(() => drainPhotos());
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


/** Photographs, one at a time.

 *  Sent individually rather than in the backlog: they are megabytes each, and
 *  a single large photo on a bad connection would otherwise hold up a whole
 *  day of typed records behind it. Each carries the id it was given when it
 *  was taken, so a retry after a dropped upload returns the photo already
 *  stored rather than filing a second copy of it.
 */
export async function drainPhotos(): Promise<number> {
  if (!navigator.onLine) return 0;
  const queued = await allPhotos();
  let sent = 0;

  for (const photo of queued) {
    // A photo the server keeps refusing is left alone after a few goes. It
    // stays on the device and visible rather than being retried forever on a
    // metered connection.
    if (photo.attempts >= 5) continue;

    const form = new FormData();
    form.append("file", photo.blob, photo.filename);
    form.append("entity_type", photo.entity_type);
    form.append("entity_id", photo.entity_id);
    form.append("folder", "progress");
    form.append("client_op_id", photo.client_op_id);
    if (photo.caption) form.append("caption", photo.caption);

    try {
      await api.post("/api/v1/media", form);
      await removePhoto(photo.client_op_id);
      sent += 1;
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      // A refusal is about this photo and will not fix itself; a network
      // failure will. Only the first is worth counting against the limit.
      if (status && status >= 400 && status < 500) {
        await notePhotoFailure(photo.client_op_id, "The server would not accept this photo");
      }
      break;
    }
  }
  return sent;
}
