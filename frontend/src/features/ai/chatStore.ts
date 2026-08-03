import { create } from "zustand";

export interface ChatActivity {
  name: string;
  isError?: boolean;
}

export interface ChatMsg {
  role: "user" | "assistant";
  content: string;
  /** Tool lookups performed while producing this assistant message */
  activity?: ChatActivity[];
  error?: string;
}

interface ChatState {
  open: boolean;
  messages: ChatMsg[];
  isStreaming: boolean;
  toggle: () => void;
  setOpen: (open: boolean) => void;
  setStreaming: (streaming: boolean) => void;
  pushUser: (content: string) => void;
  startAssistant: () => void;
  appendDelta: (delta: string) => void;
  addActivity: (activity: ChatActivity) => void;
  setError: (error: string) => void;
  clear: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  open: false,
  messages: [],
  isStreaming: false,
  toggle: () => set((s) => ({ open: !s.open })),
  setOpen: (open) => set({ open }),
  setStreaming: (isStreaming) => set({ isStreaming }),
  pushUser: (content) =>
    set((s) => ({ messages: [...s.messages, { role: "user", content }] })),
  startAssistant: () =>
    set((s) => ({
      messages: [...s.messages, { role: "assistant", content: "", activity: [] }],
    })),
  appendDelta: (delta) =>
    set((s) => {
      const messages = [...s.messages];
      const last = messages[messages.length - 1];
      if (last?.role === "assistant") {
        messages[messages.length - 1] = { ...last, content: last.content + delta };
      }
      return { messages };
    }),
  addActivity: (activity) =>
    set((s) => {
      const messages = [...s.messages];
      const last = messages[messages.length - 1];
      if (last?.role === "assistant") {
        messages[messages.length - 1] = {
          ...last,
          activity: [...(last.activity ?? []), activity],
        };
      }
      return { messages };
    }),
  setError: (error) =>
    set((s) => {
      const messages = [...s.messages];
      const last = messages[messages.length - 1];
      if (last?.role === "assistant") {
        messages[messages.length - 1] = { ...last, error };
      }
      return { messages };
    }),
  clear: () => set({ messages: [] }),
}));
