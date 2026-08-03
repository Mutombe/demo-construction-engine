import { useGetAiStatus } from "@/lib/api/generated/endpoints";

/** Whether the backend has an Anthropic API key configured. Cached for the session. */
export function useAiStatus(): { aiAvailable: boolean; loaded: boolean } {
  const { data, isSuccess } = useGetAiStatus({
    query: { staleTime: Infinity, retry: false },
  });
  return { aiAvailable: data?.available ?? false, loaded: isSuccess };
}
