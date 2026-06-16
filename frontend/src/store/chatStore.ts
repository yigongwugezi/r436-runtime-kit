import { create } from 'zustand';
import type { ChatMessage, ChatSession, QuickCommand } from '../types/chat';

const STORAGE_KEY = 'eduagent_current_session_id';

const createSessionId = () => {
  const randomPart =
    globalThis.crypto?.randomUUID?.() ?? Math.random().toString(16).slice(2);
  return `session_${Date.now()}_${randomPart}`;
};

/** 从 localStorage 恢复或创建新的 sessionId */
const loadSessionId = (): string => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return stored;
  } catch { /* 无痕模式等环境 */ }
  const id = createSessionId();
  try { localStorage.setItem(STORAGE_KEY, id); } catch { /* noop */ }
  return id;
};

/** 将 sessionId 写入 localStorage */
const persistSessionId = (id: string) => {
  try { localStorage.setItem(STORAGE_KEY, id); } catch { /* noop */ }
};

interface ChatStore {
  /** 当前会话 */
  currentSessionId: string;
  sessions: ChatSession[];
  messages: ChatMessage[];
  /** 快捷指令 */
  quickCommands: QuickCommand[];
  /** 是否正在流式生成 */
  isStreaming: boolean;
  /** 加载状态 */
  loading: boolean;

  setCurrentSession: (id: string) => void;
  addMessage: (msg: ChatMessage) => void;
  updateLastAssistant: (updater: (msg: ChatMessage) => ChatMessage) => void;
  appendToLastAssistant: (chunk: string) => void;
  setStreaming: (v: boolean) => void;
  setSessions: (sessions: ChatSession[]) => void;
  setQuickCommands: (cmds: QuickCommand[]) => void;
  setLoading: (v: boolean) => void;
  clearMessages: () => void;
  newSession: () => void;
  /** 从消息末尾移除最后一条（用于撤回） */
  removeLastMessage: () => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  currentSessionId: loadSessionId(),
  sessions: [],
  messages: [],
  quickCommands: [],
  isStreaming: false,
  loading: false,

  setCurrentSession: (id) => {
    persistSessionId(id);
    set({ currentSessionId: id });
  },

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
  setSessions: (sessions) => set({ sessions }),
  setQuickCommands: (cmds) => set({ quickCommands: cmds }),
  setLoading: (v) => set({ loading: v }),
  clearMessages: () => set({ messages: [] }),
  newSession: () => {
    const id = createSessionId();
    persistSessionId(id);
    set({ currentSessionId: id, messages: [] });
  },
  removeLastMessage: () =>
    set((s) => ({ messages: s.messages.slice(0, -1) })),
}));
