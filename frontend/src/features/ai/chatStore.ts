import { create } from "zustand";

export interface ChatActivity {
  name: string;
  isError?: boolean;
}

export interface ChatMsg {
  role: "user" | "assistant";
  /** Full (detailed) answer text — the streaming target. */
  content: string;
  /** On-demand condensed rewrite of the same answer. */
  short?: string;
  /** Which version the user is currently viewing. */
  view: "full" | "short";
  /** Data lookups performed while producing this message. */
  activity?: ChatActivity[];
  error?: string;
}

/** Live phase of the in-flight response — drives the status indicator. */
export type ChatPhase =
  | { kind: "idle" }
  | { kind: "thinking" }
  | { kind: "researching"; tool: string }
  | { kind: "writing" }
  | { kind: "condensing"; index: number };

interface ChatState {
  open: boolean;
  messages: ChatMsg[];
  isStreaming: boolean;
  phase: ChatPhase;
  toggle: () => void;
  setOpen: (open: boolean) => void;
  setStreaming: (streaming: boolean) => void;
  setPhase: (phase: ChatPhase) => void;
  pushUser: (content: string) => void;
  startAssistant: () => void;
  appendDelta: (delta: string) => void;
  appendShortDelta: (index: number, delta: string) => void;
  setView: (index: number, view: "full" | "short") => void;
  addActivity: (activity: ChatActivity) => void;
  setError: (error: string) => void;
  clear: () => void;
}

function patchMessage(
  messages: ChatMsg[],
  index: number,
  patch: (msg: ChatMsg) => ChatMsg,
): ChatMsg[] {
  const next = [...messages];
  const target = next[index];
  if (target) next[index] = patch(target);
  return next;
}

export const useChatStore = create<ChatState>((set) => ({
  open: false,
  messages: [],
  isStreaming: false,
  phase: { kind: "idle" },
  toggle: () => set((s) => ({ open: !s.open })),
  setOpen: (open) => set({ open }),
  setStreaming: (isStreaming) => set({ isStreaming }),
  setPhase: (phase) => set({ phase }),
  pushUser: (content) =>
    set((s) => ({ messages: [...s.messages, { role: "user", content, view: "full" }] })),
  startAssistant: () =>
    set((s) => ({
      messages: [...s.messages, { role: "assistant", content: "", view: "full", activity: [] }],
    })),
  appendDelta: (delta) =>
    set((s) => ({
      messages: patchMessage(s.messages, s.messages.length - 1, (m) =>
        m.role === "assistant" ? { ...m, content: m.content + delta } : m,
      ),
      phase: { kind: "writing" },
    })),
  appendShortDelta: (index, delta) =>
    set((s) => ({
      messages: patchMessage(s.messages, index, (m) => ({
        ...m,
        short: (m.short ?? "") + delta,
      })),
    })),
  setView: (index, view) =>
    set((s) => ({ messages: patchMessage(s.messages, index, (m) => ({ ...m, view })) })),
  addActivity: (activity) =>
    set((s) => ({
      messages: patchMessage(s.messages, s.messages.length - 1, (m) =>
        m.role === "assistant"
          ? { ...m, activity: [...(m.activity ?? []), activity] }
          : m,
      ),
    })),
  setError: (error) =>
    set((s) => ({
      messages: patchMessage(s.messages, s.messages.length - 1, (m) =>
        m.role === "assistant" ? { ...m, error } : m,
      ),
    })),
  clear: () => set({ messages: [], phase: { kind: "idle" } }),
}));

/** Friendly labels for the assistant's data lookups — our terminology. */
export const TOOL_LABELS: Record<string, string> = {
  list_projects: "Checking projects",
  get_project_summary: "Reviewing the project summary",
  get_boq_summary: "Reading the BOQ",
  list_boq_items: "Reading BOQ lines",
  get_budget_status: "Reviewing budget status",
  list_rfqs: "Checking RFQs",
  get_rfq: "Reading an RFQ",
  list_quotes: "Comparing quotes",
  list_purchase_orders: "Checking purchase orders",
  list_suppliers: "Checking suppliers",
  get_site_diary: "Reading the site diary",
  list_site_issues: "Checking site issues",
  list_expense_claims: "Reviewing expense claims",
  get_stock_levels: "Checking stock levels",
  get_ingestion_history: "Checking the AI Inbox",
};

export const toolLabel = (name: string): string =>
  TOOL_LABELS[name] ?? name.replaceAll("_", " ");
