import { useRef } from "react";
import { useAuthStore } from "@/features/auth/store";
import { refreshAccessToken } from "@/lib/api/axios";
import { useChatStore } from "./chatStore";

/** Raw-fetch SSE consumer — axios/orval buffer responses, so streaming must go
 * through fetch + ReadableStream. */
export function useChatStream() {
  const abortRef = useRef<AbortController | null>(null);

  const stop = () => {
    abortRef.current?.abort();
  };

  const send = async (content: string, projectId?: string) => {
    const store = useChatStore.getState();
    if (store.isStreaming) return;
    store.pushUser(content);
    store.startAssistant();
    store.setStreaming(true);

    const abort = new AbortController();
    abortRef.current = abort;

    const doFetch = (token: string | null) =>
      fetch("/api/v1/ai/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          messages: useChatStore
            .getState()
            .messages.filter((m) => m.content || m.role === "user")
            .map((m) => ({ role: m.role, content: m.content }))
            .filter((m) => m.content),
          project_id: projectId ?? null,
        }),
        signal: abort.signal,
      });

    try {
      let res = await doFetch(useAuthStore.getState().accessToken);
      if (res.status === 401) {
        const token = await refreshAccessToken();
        if (!token) throw new Error("session_expired");
        res = await doFetch(token);
      }
      if (res.status === 503) {
        useChatStore.getState().setError(
          "AI is not configured. Add ANTHROPIC_API_KEY to the backend .env to enable the assistant.",
        );
        return;
      }
      if (!res.ok || !res.body) {
        useChatStore.getState().setError("The assistant is unavailable right now.");
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop()!;
        for (const frame of frames) {
          if (!frame.startsWith("data: ")) continue;
          let event: { type: string; delta?: string; name?: string; is_error?: boolean; detail?: string };
          try {
            event = JSON.parse(frame.slice(6));
          } catch {
            continue;
          }
          const s = useChatStore.getState();
          if (event.type === "text" && event.delta) s.appendDelta(event.delta);
          else if (event.type === "tool_start" && event.name)
            s.addActivity({ name: event.name });
          else if (event.type === "tool_result" && event.is_error && event.name)
            s.addActivity({ name: event.name, isError: true });
          else if (event.type === "error")
            s.setError(event.detail ?? "The assistant hit an error.");
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        useChatStore.getState().setError("Connection to the assistant was lost.");
      }
    } finally {
      useChatStore.getState().setStreaming(false);
      abortRef.current = null;
    }
  };

  return { send, stop };
}
