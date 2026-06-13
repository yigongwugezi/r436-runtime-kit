import { create } from 'zustand';
import type { ChatMessage, ChatSession, QuickCommand } from '../types/chat';

interface ChatStore {
  /** 当前会话 */
  currentSessionId: string | null;
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
  /** 从消息末尾移除最后一条（用于撤回） */
  removeLastMessage: () => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  currentSessionId: null,
  sessions: [],
  messages: [],
  quickCommands: [],
  isStreaming: false,
  loading: false,

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
  setSessions: (sessions) => set({ sessions }),
  setQuickCommands: (cmds) => set({ quickCommands: cmds }),
  setLoading: (v) => set({ loading: v }),
  clearMessages: () => set({ messages: [] }),
  removeLastMessage: () =>
    set((s) => ({ messages: s.messages.slice(0, -1) })),
}));
