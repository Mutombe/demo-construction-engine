import {
  ArrowCounterClockwise,
  ArrowDown,
  CaretDown,
  CaretRight,
  Check,
  Copy,
  MagnifyingGlass,
  PaperPlaneTilt,
  StopCircle,
  TextAlignLeft,
  TextT,
  X,
} from "@phosphor-icons/react";
import { useRouterState } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { ClaudeIcon } from "@/components/ui/claude-icon";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ChatMarkdown } from "@/features/ai/ChatMarkdown";
import { useAiStatus } from "@/features/ai/useAiStatus";
import { useTypewriter } from "@/features/ai/useTypewriter";
import { cn } from "@/lib/utils";
import { toolLabel, useChatStore, type ChatMsg, type ChatPhase } from "./chatStore";
import { useChatStream } from "./useChatStream";

const SUGGESTIONS = [
  "Which project is over budget, and why?",
  "Summarize the open RFQs and their quotes",
  "What came through the AI Inbox this week?",
];

/* --- status line ----------------------------------------------------------- */

function PhaseIndicator({ phase }: { phase: ChatPhase }) {
  if (phase.kind === "idle") return null;
  const label =
    phase.kind === "thinking"
      ? "Thinking…"
      : phase.kind === "researching"
        ? `${toolLabel(phase.tool)}…`
        : phase.kind === "condensing"
          ? "Writing a brief version…"
          : null;
  if (!label) return null; // "writing" shows the live text itself
  return (
    <div className="flex items-center gap-2 py-0.5">
      <ClaudeIcon size={13} className="animate-pulse text-claude" />
      <span className="shimmer-text text-sm">{label}</span>
      {phase.kind === "researching" && (
        <MagnifyingGlass size={12} className="animate-pulse text-muted-foreground" />
      )}
    </div>
  );
}

/* --- research trail -------------------------------------------------------- */

function ActivityTrail({ msg, live }: { msg: ChatMsg; live: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const activity = msg.activity ?? [];
  if (activity.length === 0) return null;

  if (live || expanded) {
    return (
      <div className="mb-2 space-y-1 rounded-md border border-dashed px-2.5 py-2">
        {!live && (
          <button
            type="button"
            className="flex w-full items-center gap-1 text-[11px] font-medium text-muted-foreground hover:text-foreground"
            onClick={() => setExpanded(false)}
          >
            <CaretDown size={10} /> Research steps
          </button>
        )}
        {activity.map((a, i) => (
          <div
            key={i}
            className={cn(
              "flex items-center gap-1.5 text-[11px] text-muted-foreground",
              a.isError && "text-destructive",
            )}
          >
            <Check size={10} className={a.isError ? "text-destructive" : "text-success"} />
            {toolLabel(a.name)}
            {a.isError && " — failed"}
          </div>
        ))}
      </div>
    );
  }
  return (
    <button
      type="button"
      className="mb-1.5 flex items-center gap-1 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground"
      onClick={() => setExpanded(true)}
    >
      <CaretRight size={10} />
      <MagnifyingGlass size={10} />
      Consulted {activity.length} data source{activity.length === 1 ? "" : "s"}
    </button>
  );
}

/* --- assistant message ----------------------------------------------------- */

function AssistantMessage({
  msg,
  index,
  isLast,
  isStreaming,
  phase,
  onCondense,
  onExpand,
}: {
  msg: ChatMsg;
  index: number;
  isLast: boolean;
  isStreaming: boolean;
  phase: ChatPhase;
  onCondense: () => void;
  onExpand: () => void;
}) {
  const streamingThis =
    isStreaming &&
    ((isLast && phase.kind !== "condensing") ||
      (phase.kind === "condensing" && phase.index === index));
  const condensingThis = phase.kind === "condensing" && phase.index === index;

  const target = msg.view === "short" && msg.short !== undefined ? msg.short : msg.content;
  const shown = useTypewriter(target, streamingThis);
  const [copied, setCopied] = useState(false);
  const settled = !streamingThis && msg.content.length > 0;

  return (
    <div className="group flex gap-2.5">
      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-claude/10">
        <ClaudeIcon size={13} className="text-claude" />
      </div>
      <div className="min-w-0 flex-1">
        <ActivityTrail msg={msg} live={streamingThis && !condensingThis && !msg.content} />
        {shown ? (
          <>
            <ChatMarkdown content={shown} />
            {streamingThis && <span className="stream-cursor" aria-hidden="true" />}
          </>
        ) : (
          !streamingThis && !msg.error && null
        )}
        {msg.error && (
          <div className="mt-1 rounded-md border border-destructive/40 bg-destructive/5 px-2.5 py-1.5 text-xs text-destructive">
            {msg.error}
          </div>
        )}

        {settled && !msg.error && (
          <div className="mt-1.5 flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
            <button
              type="button"
              title="Copy"
              className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              onClick={() => {
                void navigator.clipboard.writeText(target).then(() => {
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1500);
                });
              }}
            >
              {copied ? <Check size={13} className="text-success" /> : <Copy size={13} />}
            </button>
            {msg.view === "full" ? (
              <button
                type="button"
                title="Get a shorter version"
                className="flex items-center gap-1 rounded px-1.5 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                onClick={onCondense}
                disabled={isStreaming}
              >
                <TextT size={12} /> Brief
              </button>
            ) : (
              <button
                type="button"
                title="Show the detailed version"
                className="flex items-center gap-1 rounded px-1.5 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                onClick={onExpand}
                disabled={isStreaming}
              >
                <TextAlignLeft size={12} /> Detailed
              </button>
            )}
            {msg.short !== undefined && (
              <span className="text-[10px] uppercase tracking-wide text-muted-foreground/70">
                {msg.view === "short" ? "brief view" : "detailed view"}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* --- panel ------------------------------------------------------------------ */

export function ChatPanel() {
  const { open, messages, isStreaming, phase, setOpen, setView, clear } = useChatStore();
  const { aiAvailable, loaded } = useAiStatus();
  const { send, stop, condense } = useChatStream();
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);

  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const projectId = /\/projects\/([0-9a-f-]{36})/.exec(pathname)?.[1];

  // Stick to the bottom only while the user is at the bottom.
  useEffect(() => {
    if (atBottom) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
    }
  });

  if (!open) return null;

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 48);
  };

  const submit = () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput("");
    setAtBottom(true);
    void send(text, projectId);
  };

  return (
    <div className="fixed inset-y-0 right-0 z-50 flex w-[420px] flex-col border-l bg-card shadow-xl">
      <div className="flex h-14 shrink-0 items-center justify-between border-b px-4">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-claude/10">
            <ClaudeIcon size={15} className="text-claude" />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold">Assistant</div>
            <div className="text-[10px] text-muted-foreground">Powered by Claude</div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            title="New conversation"
            onClick={clear}
            disabled={isStreaming}
          >
            <ArrowCounterClockwise />
          </Button>
          <Button variant="ghost" size="icon" onClick={() => setOpen(false)}>
            <X />
          </Button>
        </div>
      </div>

      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="relative flex-1 space-y-4 overflow-y-auto p-4"
      >
        {loaded && !aiAvailable && (
          <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
            The assistant needs an Anthropic API key. Add <code>ANTHROPIC_API_KEY</code> to the
            backend <code>.env</code> and restart the server.
          </div>
        )}
        {aiAvailable && messages.length === 0 && (
          <div className="fade-up space-y-4 pt-6 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-claude/10">
              <ClaudeIcon size={26} className="text-claude" />
            </div>
            <div>
              <p className="text-sm font-medium">How can I help with your projects?</p>
              <p className="mx-auto mt-1 max-w-[280px] text-xs text-muted-foreground">
                I check your live data — budgets, BOQ, procurement, payroll, the AI Inbox —
                before answering.
              </p>
            </div>
            <div className="space-y-1.5 text-left">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  className="block w-full rounded-lg border p-2.5 text-left text-sm transition-colors hover:border-claude/40 hover:bg-claude/5"
                  onClick={() => void send(suggestion, projectId)}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) =>
          msg.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-primary px-3.5 py-2 text-sm text-primary-foreground">
                {msg.content}
              </div>
            </div>
          ) : (
            <AssistantMessage
              key={i}
              msg={msg}
              index={i}
              isLast={i === messages.length - 1}
              isStreaming={isStreaming}
              phase={phase}
              onCondense={() => void condense(i)}
              onExpand={() => setView(i, "full")}
            />
          ),
        )}

        {(phase.kind === "thinking" || phase.kind === "researching") && (
          <div className="flex gap-2.5 pl-[34px]">
            <PhaseIndicator phase={phase} />
          </div>
        )}
        {phase.kind === "condensing" && (
          <div className="pl-[34px]">
            <PhaseIndicator phase={phase} />
          </div>
        )}
      </div>

      {!atBottom && (
        <button
          type="button"
          aria-label="Jump to latest"
          className="dropdown-in absolute bottom-24 right-4 z-10 flex h-8 w-8 items-center justify-center rounded-full border bg-card shadow-md transition-colors hover:bg-muted"
          onClick={() => {
            setAtBottom(true);
            scrollRef.current?.scrollTo({
              top: scrollRef.current.scrollHeight,
              behavior: "smooth",
            });
          }}
        >
          <ArrowDown size={14} />
        </button>
      )}

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
            <Button variant="outline" size="icon" onClick={stop} title="Stop generating">
              <StopCircle className="text-destructive" />
            </Button>
          ) : (
            <Button size="icon" onClick={submit} disabled={!aiAvailable || !input.trim()}>
              <PaperPlaneTilt />
            </Button>
          )}
        </div>
        <p className="mt-1.5 text-[10px] text-muted-foreground">
          {projectId
            ? "Context: the project you're viewing · Claude can check live ERP data"
            : "Claude can check live ERP data before answering"}
        </p>
      </div>
    </div>
  );
}
