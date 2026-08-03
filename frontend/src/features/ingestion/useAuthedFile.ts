import { useEffect, useState } from "react";
import { api } from "@/lib/api/axios";

/** Fetch the (auth-protected) stored document as a blob object URL for preview. */
export function useAuthedFile(itemId: string | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!itemId) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    api
      .get(`/api/v1/ingestion/items/${itemId}/file`, { responseType: "blob" })
      .then((res) => {
        objectUrl = URL.createObjectURL(res.data as Blob);
        if (!cancelled) setUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setUrl(null);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [itemId]);

  return url;
}
