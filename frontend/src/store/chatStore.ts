import { create } from 'zustand';
import type { ChatMessage, ChatSession, QuickCommand, GenerationProgress } from '../types/chat';
import { getCurrentLearner } from '../pages/LoginPage';
import { useSubjectStore } from './subjectStore';
import { readStorageItem, readStorageJson, writeStorageItem, writeStorageJson, runtimeStorageKeys } from '../utils/storageKeys';

/** 基于 learnerId + subjectId 生成 storage key，实现科目隔离 */
export const suffix = () => {
  const learner = getCurrentLearner();
  const subject = useSubjectStore.getState().activeSubject;
  const learnerId = learner?.id || 'anonymous';
  const subjectId = subject?.id || 'default';
  return `${learnerId}_${subjectId}`;
};

const storageKey = () => runtimeStorageKeys.chatSession(suffix());
const sessionsKey = () => runtimeStorageKeys.chatSessions(suffix());

const createSessionId = () => {
  const randomPart =
    globalThis.crypto?.randomUUID?.() ?? Math.random().toString(16).slice(2);
  return `session_${Date.now()}_${randomPart}`;
};

/** 从 localStorage 恢复或创建新的 sessionId */
const loadSessionId = (): string => {
  try {
    const stored = readStorageItem(storageKey());
    if (stored) return stored;
  } catch { /* 无痕模式等环境 */ }
  const id = createSessionId();
  writeStorageItem(storageKey(), id);
  return id;
};

const persistSessionId = (id: string) => {
  writeStorageItem(storageKey(), id);
};

/** 加载历史会话列表 */
const loadSessions = (): ChatSession[] => {
  return readStorageJson(sessionsKey(), []);
};

const persistSessions = (sessions: ChatSession[]) => {
  writeStorageJson(sessionsKey(), sessions);
};

interface ChatStore {
  currentSessionId: string;
  sessions: ChatSession[];
  messages: ChatMessage[];
  quickCommands: QuickCommand[];
  isStreaming: boolean;
  loading: boolean;
  agentProgress: GenerationProgress | null;
  dataVersion: number;

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
  bumpDataVersion: () => void;
  /** 重新加载当前科目的会话 ID 和列表（科目切换后调用） */
  reloadSession: () => void;
}

export const useChatStore = create<ChatStore>((set, get) => ({
  currentSessionId: loadSessionId(),
  sessions: loadSessions(),
  messages: [],
  quickCommands: [],
  isStreaming: false,
  loading: false,
  agentProgress: null,
  dataVersion: 0,

  setCurrentSession: (id) => {
    persistSessionId(id);
    set({ currentSessionId: id, messages: [] });
  },

  addMessage: (msg) =>
    set((s) => {
      const msgs = [...s.messages, msg];
      // 第一条用户消息 → 保存会话摘要
      const sessions = loadSessions();
      if (msg.role === 'user' && msgs.filter(m => m.role === 'user').length === 1) {
        const existing = sessions.find(ses => ses.id === s.currentSessionId);
        if (!existing) {
          sessions.unshift({
            id: s.currentSessionId,
            title: msg.content.slice(0, 60),
            messages: [],
            createdAt: msg.timestamp,
            updatedAt: msg.timestamp,
          });
          persistSessions(sessions);
        }
      }
      // 更新会话时间
      const sesIdx = sessions.findIndex(ses => ses.id === s.currentSessionId);
      if (sesIdx >= 0) {
        sessions[sesIdx].updatedAt = msg.timestamp;
        sessions[sesIdx].title = sessions[sesIdx].title || msg.content.slice(0, 60);
        persistSessions(sessions);
      }
      return { messages: msgs, sessions };
    }),

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
  newSession: () => {
    const state = get();
    // 有消息时保存当前会话摘要
    if (state.messages.length > 0) {
      const sessions = loadSessions();
      const existing = sessions.find(s => s.id === state.currentSessionId);
      if (!existing) {
        const firstUser = state.messages.find(m => m.role === 'user');
        sessions.unshift({
          id: state.currentSessionId,
          title: firstUser?.content?.slice(0, 60) || '新对话',
          messages: [],
          createdAt: state.messages[0]?.timestamp || Date.now(),
          updatedAt: Date.now(),
        });
        persistSessions(sessions);
        set({ sessions });
      }
    }
    const id = createSessionId();
    persistSessionId(id);
    set({ currentSessionId: id, messages: [] });
  },
  removeLastMessage: () =>
    set((s) => ({ messages: s.messages.slice(0, -1) })),

  bumpDataVersion: () =>
    set((s) => ({ dataVersion: s.dataVersion + 1 })),

  /** 科目切换后重新加载该科目下的会话 ID 和会话列表 */
  reloadSession: () => {
    const id = loadSessionId();
    const sessions = loadSessions();
    set({ currentSessionId: id, sessions, messages: [] });
  },
}));

// ================================================================
// 自动监听科目切换 → 刷新会话
// ================================================================
let prevSubjectId: string | undefined;
useSubjectStore.subscribe((state) => {
  const newId = state.activeSubject?.id;
  if (newId && newId !== prevSubjectId) {
    prevSubjectId = newId;
    // 延迟执行，等 store 状态更新完毕
    setTimeout(() => {
      useChatStore.getState().reloadSession();
    }, 0);
  }
});
