import { useRouterState } from "@tanstack/react-router";
import { CircleStop, RotateCcw, Search, Send, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAiStatus } from "@/features/ai/useAiStatus";
import { cn } from "@/lib/utils";
import { useChatStore } from "./chatStore";
import { useChatStream } from "./useChatStream";

const SUGGESTIONS = [
  "Which project is over budget, and why?",
  "Summarize the open RFQs and their quotes",
  "What are the biggest cost overruns right now?",
];

export function ChatPanel() {
  const { open, messages, isStreaming, setOpen, clear } = useChatStore();
  const { aiAvailable, loaded } = useAiStatus();
  const { send, stop } = useChatStream();
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const projectId = /\/projects\/([0-9a-f-]{36})/.exec(pathname)?.[1];

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  if (!open) return null;

  const submit = () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput("");
    void send(text, projectId);
  };

  return (
    <div className="fixed inset-y-0 right-0 z-50 flex w-[400px] flex-col border-l bg-card shadow-xl">
      <div className="flex h-14 shrink-0 items-center justify-between border-b px-4">
        <div className="flex items-center gap-2 font-semibold">
          <Sparkles className="h-4 w-4 text-primary" /> Assistant
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            title="New conversation"
            onClick={clear}
            disabled={isStreaming}
          >
            <RotateCcw />
          </Button>
          <Button variant="ghost" size="icon" onClick={() => setOpen(false)}>
            <X />
          </Button>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
        {loaded && !aiAvailable && (
          <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
            The assistant needs an Anthropic API key. Add <code>ANTHROPIC_API_KEY</code> to the
            backend <code>.env</code> and restart the server.
          </div>
        )}
        {aiAvailable && messages.length === 0 && (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Ask about your projects, budgets, BOQ or procurement. I look up live data before
              answering.
            </p>
            <div className="space-y-1.5">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  className="block w-full rounded-md border p-2 text-left text-sm transition-colors hover:bg-accent"
                  onClick={() => void send(suggestion, projectId)}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}>
            <div
              className={cn(
                "max-w-[90%] rounded-lg px-3 py-2 text-sm",
                msg.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-secondary text-foreground",
              )}
            >
              {msg.activity && msg.activity.length > 0 && (
                <div className="mb-1.5 flex flex-wrap gap-1">
                  {msg.activity.map((a, j) => (
                    <span
                      key={j}
                      className={cn(
                        "inline-flex items-center gap-1 rounded-full bg-card px-2 py-0.5 text-[10px] text-muted-foreground",
                        a.isError && "text-destructive",
                      )}
                    >
                      <Search className="h-2.5 w-2.5" />
                      {a.name.replaceAll("_", " ")}
                    </span>
                  ))}
                </div>
              )}
              <div className="whitespace-pre-wrap">
                {msg.content}
                {msg.role === "assistant" &&
                  isStreaming &&
                  i === messages.length - 1 &&
                  !msg.error && <span className="ml-0.5 animate-pulse">▌</span>}
              </div>
              {msg.error && <div className="mt-1 text-xs text-destructive">{msg.error}</div>}
            </div>
          </div>
        ))}
      </div>

      <div className="shrink-0 border-t p-3">
        <div className="flex items-end gap-2">
          <Textarea
            rows={2}
            className="resize-none"
            placeholder={aiAvailable ? "Ask about your projects…" : "AI not configured"}
            disabled={!aiAvailable || isStreaming}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          {isStreaming ? (
            <Button variant="outline" size="icon" onClick={stop} title="Stop">
              <CircleStop />
            </Button>
          ) : (
            <Button size="icon" onClick={submit} disabled={!aiAvailable || !input.trim()}>
              <Send />
            </Button>
          )}
        </div>
        {projectId && (
          <p className="mt-1.5 text-[10px] text-muted-foreground">
            Context: the project you're currently viewing
          </p>
        )}
      </div>
    </div>
  );
}
