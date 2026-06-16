import { create } from 'zustand';
import type { ChatMessage, ChatSession, QuickCommand, GenerationProgress } from '../types/chat';

const createSessionId = () => {
  const randomPart =
    globalThis.crypto?.randomUUID?.() ?? Math.random().toString(16).slice(2);
  return `session_${Date.now()}_${randomPart}`;
};

interface ChatStore {
  currentSessionId: string;
  sessions: ChatSession[];
  messages: ChatMessage[];
  quickCommands: QuickCommand[];
  isStreaming: boolean;
  loading: boolean;
  agentProgress: GenerationProgress | null;

  setCurrentSession: (id: string) => void;
  addMessage: (msg: ChatMessage) => void;
  updateLastAssistant: (updater: (msg: ChatMessage) => ChatMessage) => void;
  appendToLastAssistant: (chunk: string) => void;
  setStreaming: (v: boolean) => void;
  setAgentProgress: (p: GenerationProgress | null) => void;
  setSessions: (sessions: ChatSession[]) => void;
  setQuickCommands: (cmds: QuickCommand[]) => void;
  setLoading: (v: boolean) => void;
  clearMessages: () => void;
  newSession: () => void;
  removeLastMessage: () => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  currentSessionId: createSessionId(),
  sessions: [],
  messages: [],
  quickCommands: [],
  isStreaming: false,
  loading: false,
  agentProgress: null,

  setCurrentSession: (id) => set({ currentSessionId: id }),

  addMessage: (msg) =>
    set((s) => ({ messages: [...s.messages, msg] })),

  updateLastAssistant: (updater) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last?.role === 'assistant') {
        msgs[msgs.length - 1] = updater(last);
      }
      return { messages: msgs };
    }),

  appendToLastAssistant: (chunk) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last?.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, content: last.content + chunk };
      }
      return { messages: msgs };
    }),

  setStreaming: (v) => set({ isStreaming: v }),
  setAgentProgress: (p) => set({ agentProgress: p }),
  setSessions: (sessions) => set({ sessions }),
  setQuickCommands: (cmds) => set({ quickCommands: cmds }),
  setLoading: (v) => set({ loading: v }),
  clearMessages: () => set({ messages: [] }),
  newSession: () => set({ currentSessionId: createSessionId(), messages: [], agentProgress: null }),
  removeLastMessage: () =>
    set((s) => ({ messages: s.messages.slice(0, -1) })),
}));
