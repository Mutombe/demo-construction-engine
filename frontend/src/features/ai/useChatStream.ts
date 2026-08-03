import { useRef } from "react";
import { useAuthStore } from "@/features/auth/store";
import { refreshAccessToken } from "@/lib/api/axios";
import { useChatStore } from "./chatStore";

interface StreamEvent {
  type: string;
  delta?: string;
  name?: string;
  is_error?: boolean;
  detail?: string;
}

/** Raw-fetch SSE consumer — axios/orval buffer responses, so streaming must go
 * through fetch + ReadableStream. Drives both the main conversation and the
 * on-demand "Brief" condensed rewrites. */
export function useChatStream() {
  const abortRef = useRef<AbortController | null>(null);

  const stop = () => {
    abortRef.current?.abort();
  };

  const streamChat = async (
    body: object,
    abort: AbortController,
    onEvent: (event: StreamEvent) => void,
  ): Promise<"ok" | "unconfigured" | "unavailable"> => {
    const doFetch = (token: string | null) =>
      fetch("/api/v1/ai/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
        signal: abort.signal,
      });

    let res = await doFetch(useAuthStore.getState().accessToken);
    if (res.status === 401) {
      const token = await refreshAccessToken();
      if (!token) throw new Error("session_expired");
      res = await doFetch(token);
    }
    if (res.status === 503) return "unconfigured";
    if (!res.ok || !res.body) return "unavailable";

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
        try {
          onEvent(JSON.parse(frame.slice(6)) as StreamEvent);
        } catch {
          // malformed frame — skip
        }
      }
    }
    return "ok";
  };

  const send = async (content: string, projectId?: string) => {
    const store = useChatStore.getState();
    if (store.isStreaming) return;
    store.pushUser(content);
    store.startAssistant();
    store.setStreaming(true);
    store.setPhase({ kind: "thinking" });

    const abort = new AbortController();
    abortRef.current = abort;

    try {
      const outcome = await streamChat(
        {
          messages: useChatStore
            .getState()
            .messages.filter((m) => m.content)
            .map((m) => ({ role: m.role, content: m.content })),
          project_id: projectId ?? null,
        },
        abort,
        (event) => {
          const s = useChatStore.getState();
          if (event.type === "text" && event.delta) s.appendDelta(event.delta);
          else if (event.type === "tool_start" && event.name) {
            s.addActivity({ name: event.name });
            s.setPhase({ kind: "researching", tool: event.name });
          } else if (event.type === "tool_result" && event.is_error && event.name)
            s.addActivity({ name: event.name, isError: true });
          else if (event.type === "error")
            s.setError(event.detail ?? "The assistant hit an error.");
        },
      );
      if (outcome === "unconfigured") {
        useChatStore
          .getState()
          .setError(
            "AI is not configured. Add ANTHROPIC_API_KEY to the backend .env to enable the assistant.",
          );
      } else if (outcome === "unavailable") {
        useChatStore.getState().setError("The assistant is unavailable right now.");
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        useChatStore.getState().setError("Connection to the assistant was lost.");
      }
    } finally {
      useChatStore.getState().setStreaming(false);
      useChatStore.getState().setPhase({ kind: "idle" });
      abortRef.current = null;
    }
  };

  /** Stream a condensed rewrite of an existing answer into `msg.short`.
   *  Runs as a side-channel request — it never joins the conversation. */
  const condense = async (index: number) => {
    const store = useChatStore.getState();
    const msg = store.messages[index];
    if (!msg || msg.role !== "assistant" || !msg.content || store.isStreaming) return;
    if (msg.short) {
      store.setView(index, "short");
      return;
    }
    store.setView(index, "short");
    store.setStreaming(true);
    store.setPhase({ kind: "condensing", index });

    const abort = new AbortController();
    abortRef.current = abort;
    try {
      await streamChat(
        {
          messages: [
            {
              role: "user",
              content:
                "Rewrite the following answer as a brief version: at most 3 short sentences " +
                "or up to 5 tight bullet points. Keep every key figure, name and conclusion. " +
                "No preamble — output only the rewritten answer, in markdown.\n\n---\n\n" +
                msg.content,
            },
          ],
          project_id: null,
        },
        abort,
        (event) => {
          if (event.type === "text" && event.delta) {
            useChatStore.getState().appendShortDelta(index, event.delta);
          }
        },
      );
    } catch {
      // fall back to the detailed view on any failure
      useChatStore.getState().setView(index, "full");
    } finally {
      useChatStore.getState().setStreaming(false);
      useChatStore.getState().setPhase({ kind: "idle" });
      abortRef.current = null;
    }
  };

  return { send, stop, condense };
}
