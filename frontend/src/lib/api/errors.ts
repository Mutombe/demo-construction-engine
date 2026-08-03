/** Single source for extracting the backend's error envelope
 *  ({error: {code, detail}}) from an axios failure. */
export function errDetail(err: unknown): string {
  return (
    (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
      ?.detail ?? "Something went wrong"
  );
}
