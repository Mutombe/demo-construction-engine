/** Optimistic-mutation toolkit over TanStack Query v5 + orval.
 *
 * The contract (per the app's optimistic-UI standard):
 *   onMutate  → cancel in-flight refetches for the affected keys, snapshot
 *               every matching cache entry, apply the optimistic patch
 *   onError   → restore the snapshot exactly, toast the human-readable error
 *   onSettled → targeted invalidation (never the whole cache) so the server's
 *               truth replaces the guess
 *
 * Orval mutation hooks accept `{ mutation: {...} }`, so the returned handlers
 * spread straight in:  useCreateX({ mutation: optimistic(queryClient, {...}) })
 *
 * Placeholder rows are flagged `__optimistic` (excluded from row actions until
 * real); in-place updates flag `__saving` (rendered dimmed with a badge).
 */

import type { QueryClient, UseMutationOptions } from "@tanstack/react-query";
import { toast } from "sonner";
import { errDetail } from "@/lib/api/errors";

/* eslint-disable @typescript-eslint/no-explicit-any */

export interface OptimisticFlags {
  __optimistic?: boolean;
  __saving?: boolean;
}

interface PageShape<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

let tempSeq = 0;
export const tempId = () => `optimistic-${++tempSeq}`;
export const isOptimistic = (row: unknown): boolean =>
  Boolean((row as OptimisticFlags | null)?.__optimistic);

type Snapshot = Array<[readonly unknown[], unknown]>;

interface Ctx {
  snapshots: Snapshot;
}

export function optimistic<TVars = any>(
  queryClient: QueryClient,
  opts: {
    /** URL prefixes whose cached queries get patched (all params variants). */
    prefixes: string[];
    /** Pure cache patch; receives each matching cached value. Return the next
     *  value (or the input unchanged). */
    apply: (old: any, vars: TVars) => any;
    /** Extra prefixes to refetch on settle (defaults to `prefixes`). */
    invalidate?: string[];
    successToast?: string | ((data: any, vars: TVars) => string);
    errorToast?: boolean;
  },
  // Deliberately loose: this spreads into every orval hook's `mutation` slot
  // regardless of its concrete TData/TVars generics.
): UseMutationOptions<any, any, any, any> {
  const { prefixes, apply, invalidate = opts.prefixes, errorToast = true } = opts;
  return {
    onMutate: async (vars: TVars): Promise<Ctx> => {
      const snapshots: Snapshot = [];
      for (const prefix of prefixes) {
        await queryClient.cancelQueries({ queryKey: [prefix] });
        for (const [key, data] of queryClient.getQueriesData({ queryKey: [prefix] })) {
          snapshots.push([key, data]);
          if (data !== undefined) {
            queryClient.setQueryData(key, apply(data, vars));
          }
        }
      }
      return { snapshots };
    },
    onError: (err: unknown, _vars: TVars, ctx: Ctx | undefined) => {
      for (const [key, data] of ctx?.snapshots ?? []) {
        queryClient.setQueryData(key, data);
      }
      if (errorToast) toast.error(errDetail(err));
    },
    onSuccess: (data: any, vars: TVars) => {
      if (opts.successToast) {
        toast.success(
          typeof opts.successToast === "function"
            ? opts.successToast(data, vars)
            : opts.successToast,
        );
      }
    },
    onSettled: async () => {
      await Promise.all(
        invalidate.map((prefix) =>
          queryClient.invalidateQueries({ queryKey: [prefix] }),
        ),
      );
    },
  };
}

/* --- Page<T>-aware patch helpers ------------------------------------------ */

/** Insert a placeholder row at the top of every cached page list. */
export function addRow<T>(make: () => T) {
  return (old: any): any => {
    if (!old || !Array.isArray(old.items)) return old;
    const page = old as PageShape<T>;
    return {
      ...page,
      items: [{ ...(make() as object), __optimistic: true } as T, ...page.items],
      total: page.total + 1,
    };
  };
}

/** Patch a row in place (list caches) and any detail cache with matching id. */
export function patchRow(id: string, patch: Record<string, unknown>) {
  return (old: any): any => {
    if (old && Array.isArray(old.items)) {
      const page = old as PageShape<{ id?: string }>;
      return {
        ...page,
        items: page.items.map((row) =>
          row.id === id ? { ...row, ...patch, __saving: true } : row,
        ),
      };
    }
    if (old && (old as { id?: string }).id === id) {
      return { ...old, ...patch, __saving: true };
    }
    return old;
  };
}

/** Remove a row from every cached page list immediately. */
export function removeRow(id: string) {
  return (old: any): any => {
    if (!old || !Array.isArray(old.items)) return old;
    const page = old as PageShape<{ id?: string }>;
    const items = page.items.filter((row) => row.id !== id);
    if (items.length === page.items.length) return old;
    return { ...page, items, total: Math.max(0, page.total - 1) };
  };
}
