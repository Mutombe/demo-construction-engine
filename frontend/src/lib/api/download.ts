import { api } from "@/lib/api/axios";

interface DownloadOptions {
  /** POST when the document is built from a body rather than from the URL. */
  method?: "GET" | "POST";
  body?: unknown;
}

/** Fetch an authenticated endpoint as a blob and trigger a browser download.
 *  Filename comes from Content-Disposition, falling back to `fallbackName`. */
export async function downloadFile(
  url: string,
  fallbackName: string,
  options: DownloadOptions = {},
): Promise<void> {
  const res =
    options.method === "POST"
      ? await api.post(url, options.body ?? {}, { responseType: "blob" })
      : await api.get(url, { responseType: "blob" });
  const disposition: string = res.headers["content-disposition"] ?? "";
  const match = /filename="?([^";]+)"?/.exec(disposition);
  const filename = match?.[1] ?? fallbackName;

  const objectUrl = URL.createObjectURL(res.data as Blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}
