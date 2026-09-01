/** The queue of things captured on site before there was any signal.
 *
 *  Everything a field form produces is written here first and sent later,
 *  including when the network is up. That is deliberate: a form that
 *  sometimes posts directly and sometimes queues has two code paths and only
 *  one of them gets tested, and it is never the one the site uses.
 *
 *  IndexedDB rather than localStorage because this has to survive the browser
 *  being killed mid-shift and because photos are blobs.
 */

const DB_NAME = "erp-outbox";
const DB_VERSION = 2;
const STORE = "operations";
const PHOTO_STORE = "photos";
const DEVICE_KEY = "erp-device-id";

export type OutboxStatus = "pending" | "sending" | "rejected";

export interface OutboxOperation {
  /** Made on the device before the record is saved, so it survives retries
   *  and makes the send idempotent on the server. */
  client_op_id: string;
  op_type: string;
  payload: Record<string, unknown>;
  captured_at: string;
  status: OutboxStatus;
  attempts: number;
  /** Why the server refused it, in words meant for the person who wrote it. */
  detail?: string;
  label: string;
}

let dbPromise: Promise<IDBDatabase> | null = null;

function open(): Promise<IDBDatabase> {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: "client_op_id" });
        store.createIndex("status", "status");
      }
      // Photos live in their own store because they are blobs and go up one
      // at a time. Putting a megabyte of JPEG in the JSON backlog would make
      // one bad photo hold up an entire day of typed records.
      if (!db.objectStoreNames.contains(PHOTO_STORE)) {
        db.createObjectStore(PHOTO_STORE, { keyPath: "client_op_id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  return dbPromise;
}

function tx<T>(
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>,
  storeName: string = STORE,
) {
  return open().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const transaction = db.transaction(storeName, mode);
        const request = run(transaction.objectStore(storeName));
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      }),
  );
}

/** Stable per browser. The server uses it to tell one person's phone from
 *  another's when the same login is shared across a crew, which happens. */
export function deviceId(): string {
  let id = localStorage.getItem(DEVICE_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(DEVICE_KEY, id);
  }
  return id;
}

export async function enqueue(
  op_type: string,
  payload: Record<string, unknown>,
  label: string,
): Promise<OutboxOperation> {
  const operation: OutboxOperation = {
    client_op_id: crypto.randomUUID(),
    op_type,
    payload,
    captured_at: new Date().toISOString(),
    status: "pending",
    attempts: 0,
    label,
  };
  await tx("readwrite", (store) => store.put(operation));
  notify();
  return operation;
}

export async function all(): Promise<OutboxOperation[]> {
  const rows = await tx<OutboxOperation[]>("readonly", (store) => store.getAll());
  return rows.sort((a, b) => a.captured_at.localeCompare(b.captured_at));
}

export async function pending(): Promise<OutboxOperation[]> {
  return (await all()).filter((op) => op.status !== "rejected");
}

export async function remove(client_op_id: string): Promise<void> {
  await tx("readwrite", (store) => store.delete(client_op_id));
  notify();
}

export async function markRejected(client_op_id: string, detail: string): Promise<void> {
  const existing = await tx<OutboxOperation | undefined>("readonly", (store) =>
    store.get(client_op_id),
  );
  if (!existing) return;
  await tx("readwrite", (store) =>
    store.put({ ...existing, status: "rejected", detail, attempts: existing.attempts + 1 }),
  );
  notify();
}

// --- Subscription so the UI can show what is still waiting -------------------

const listeners = new Set<() => void>();

function notify() {
  for (const listener of listeners) listener();
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}


// --- Photos ------------------------------------------------------------------

export interface OutboxPhoto {
  client_op_id: string;
  entity_type: string;
  entity_id: string;
  caption: string;
  filename: string;
  blob: Blob;
  captured_at: string;
  attempts: number;
  detail?: string;
}

export async function enqueuePhoto(
  entity_type: string,
  entity_id: string,
  file: File,
  caption: string,
): Promise<OutboxPhoto> {
  const photo: OutboxPhoto = {
    client_op_id: crypto.randomUUID(),
    entity_type,
    entity_id,
    caption,
    filename: file.name || "site-photo.jpg",
    // The blob itself, so the photo survives the browser being closed on a
    // site with no signal. A file handle would not.
    blob: file,
    captured_at: new Date().toISOString(),
    attempts: 0,
  };
  await tx("readwrite", (store) => store.put(photo), PHOTO_STORE);
  notify();
  return photo;
}

export async function allPhotos(): Promise<OutboxPhoto[]> {
  const rows = await tx<OutboxPhoto[]>("readonly", (store) => store.getAll(), PHOTO_STORE);
  return rows.sort((a, b) => a.captured_at.localeCompare(b.captured_at));
}

export async function removePhoto(client_op_id: string): Promise<void> {
  await tx("readwrite", (store) => store.delete(client_op_id), PHOTO_STORE);
  notify();
}

export async function notePhotoFailure(client_op_id: string, detail: string): Promise<void> {
  const existing = await tx<OutboxPhoto | undefined>(
    "readonly",
    (store) => store.get(client_op_id),
    PHOTO_STORE,
  );
  if (!existing) return;
  await tx(
    "readwrite",
    (store) => store.put({ ...existing, attempts: existing.attempts + 1, detail }),
    PHOTO_STORE,
  );
  notify();
}
