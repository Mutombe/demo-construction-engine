import { useEffect, useState } from "react";
import { api } from "@/lib/api/axios";

/** Fetch any auth-protected file endpoint as a blob object URL.
 *  Files are served only through authed endpoints, so plain <img src> can't
 *  reach them — this hook bridges the gap and revokes the URL on unmount. */
export function useAuthedBlobUrl(url: string | null | undefined): string | null {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!url) return;
    let created: string | null = null;
    let cancelled = false;
    api
      .get(url, { responseType: "blob" })
      .then((res) => {
        created = URL.createObjectURL(res.data as Blob);
        if (!cancelled) setObjectUrl(created);
      })
      .catch(() => {
        if (!cancelled) setObjectUrl(null);
      });
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
      setObjectUrl(null);
    };
  }, [url]);

  return objectUrl;
}
