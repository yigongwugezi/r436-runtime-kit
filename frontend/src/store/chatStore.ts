import { create } from 'zustand';
import type { ChatMessage, ChatSession, QuickCommand, GenerationProgress, ChatAttachment } from '../types/chat';
import { getCurrentLearner, getStableLearnerId } from './authStore';
import { useSubjectStore } from './subjectStore';
import { readStorageItem, readStorageJson, writeStorageItem, writeStorageJson, runtimeStorageKeys } from '../utils/storageKeys';
import { ensureCanonicalSubjectSession, getCanonicalSubjectSession, getSubjectSession } from '../api/subjects';
import { createChatSession, getSessions, getSessionMessages } from '../api/chat';
import { createLogger } from '../utils/logger';
import { canonicalRequestKey } from '../utils/canonicalSessionState';

const log = createLogger('ChatStore');

/** 基于 learnerId + subjectId 生成 storage key，实现科目隔离 */
export const suffix = () => {
  const subject = useSubjectStore.getState().activeSubject;
  const learnerId = getStableLearnerId();
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

export const imageAttachmentKey = (attachment: ChatAttachment | null | undefined) =>
  attachment?.file_id || attachment?.image_url || attachment?.url || attachment?.local_path || attachment?.name || '';

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

/** 将当前消息同步到会话的 localStorage 缓存中 */
const syncMessagesToSession = (sessionId: string, messages: ChatMessage[]) => {
  const sessions = loadSessions();
  const idx = sessions.findIndex(s => s.id === sessionId);
  if (idx >= 0) {
    sessions[idx].messages = messages;
    // 同步更新 title（取第一条用户消息）
    const firstUser = messages.find(m => m.role === 'user');
    if (firstUser && !sessions[idx].title) {
      sessions[idx].title = firstUser.content.slice(0, 60);
    }
    persistSessions(sessions);
  }
};

interface ChatStore {
  currentSessionId: string;
  /** 科目级数据查询用的稳定 sessionId，新建对话时不改变 */
  dataSessionId: string;
  canonicalSession: {
    status: 'unresolved' | 'resolving' | 'resolved' | 'failed';
    subjectId: string;
    sessionId: string;
    pathId: string | null;
    source: string;
    resolvedAt: string | null;
  };
  sessions: ChatSession[];
  messages: ChatMessage[];
  quickCommands: QuickCommand[];
  isStreaming: boolean;
  loading: boolean;
  agentProgress: GenerationProgress | null;
  lastImageAttachment: import('../types/chat').ChatAttachment | null;
  imageAttachmentHistory: import('../types/chat').ChatAttachment[];
  selectedImageAttachmentId: string | null;
  /** SSE done 事件中的 debug 字段，仅开发模式展示 */
  lastDebugInfo: Record<string, any> | null;
  /** 动态进度条步骤（根据实际运行的 Agent 构建，替代硬编码 GEN_PIPELINE） */
  progressPipelineSteps: import('../types/chat').ProgressStep[];
  dataVersion: number;
  /** 聊天模式：自由学习 / 调用模式 / 规划学习 */
  chatMode: 'free' | 'planning';
  /** 联网搜索开关 */
  searchEnabled: boolean;
  /** 深度思考开关 */
  deepThinkEnabled: boolean;

  setCurrentSession: (id: string) => void;
  addMessage: (msg: ChatMessage) => void;
  updateLastAssistant: (updater: (msg: ChatMessage) => ChatMessage) => void;
  appendToLastAssistant: (chunk: string) => void;
  appendReasoningToLastAssistant: (chunk: string) => void;
  setSearchEnabled: (v: boolean) => void;
  setDeepThinkEnabled: (v: boolean) => void;
  setChatMode: (mode: 'free' | 'planning') => void;
  setStreaming: (v: boolean) => void;
  setAgentProgress: (p: GenerationProgress | null) => void;
  setLastImageAttachment: (attachment: import('../types/chat').ChatAttachment | null) => void;
  addImageAttachment: (attachment: import('../types/chat').ChatAttachment) => void;
  selectImageAttachment: (id: string | null) => void;
  setLastDebugInfo: (info: Record<string, any> | null) => void;
  setProgressPipelineSteps: (steps: import('../types/chat').ProgressStep[]) => void;
  addProgressPipelineStep: (step: import('../types/chat').ProgressStep) => void;
  setSessions: (sessions: ChatSession[]) => void;
  setQuickCommands: (cmds: QuickCommand[]) => void;
  setLoading: (v: boolean) => void;
  clearMessages: () => void;
  newSession: () => void;
  removeLastMessage: () => void;
  removeSession: (id: string) => void;
  renameSession: (id: string, title: string) => void;
  bumpDataVersion: () => void;
  resolveCanonicalSession: () => Promise<void>;
  /** 重新加载当前科目的会话 ID 和列表（科目切换后调用） */
  reloadSession: () => Promise<void>;
}

let canonicalRequest: { key: string; promise: Promise<void> } | null = null;
let canonicalAbort: AbortController | null = null;
let canonicalGeneration = 0;

export const useChatStore = create<ChatStore>((set, get) => ({
  currentSessionId: loadSessionId(),
  sessions: loadSessions(),
  messages: (() => {
    // Restore messages from localStorage session cache, so orphaned
    // streaming messages survive page reload for recovery.
    const id = loadSessionId();
    const sessions = loadSessions();
    return sessions.find(s => s.id === id)?.messages || [];
  })(),
  quickCommands: [],
  isStreaming: false,
  loading: false,
  agentProgress: null,
  lastImageAttachment: null,
  imageAttachmentHistory: [],
  selectedImageAttachmentId: null,
  lastDebugInfo: null,
  progressPipelineSteps: [],
  dataVersion: 0,
  searchEnabled: false,
  deepThinkEnabled: false,
  chatMode: 'free',
  dataSessionId: '',
  canonicalSession: { status: 'unresolved', subjectId: '', sessionId: '', pathId: null, source: '', resolvedAt: null },

  setCurrentSession: (id) => {
    log.debug(`切换会话: ${id.slice(0, 20)}...`);

    // 1. 先将当前会话的消息保存到 localStorage 缓存
    const state = get();
    if (state.messages.length > 0) {
      syncMessagesToSession(state.currentSessionId, state.messages);
    }

    // 2. 如果点击的是同一个会话 → 不清空消息，直接返回
    if (id === state.currentSessionId) {
      persistSessionId(id);
      return;
    }

    // 3. 切换不同会话 → 从 localStorage 加载缓存消息
    const sessions = loadSessions();
    const targetSession = sessions.find(s => s.id === id);
    const cachedMessages = targetSession?.messages || [];

    persistSessionId(id);
    writeStorageItem(runtimeStorageKeys.pendingGeneration, '');
    set({ currentSessionId: id, messages: cachedMessages, isStreaming: false, progressPipelineSteps: [], agentProgress: null, lastDebugInfo: null, lastImageAttachment: null, imageAttachmentHistory: [], selectedImageAttachmentId: null });
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
      // 更新会话时间 & 缓存消息
      const sesIdx = sessions.findIndex(ses => ses.id === s.currentSessionId);
      if (sesIdx >= 0) {
        sessions[sesIdx].updatedAt = msg.timestamp;
        sessions[sesIdx].title = sessions[sesIdx].title || msg.content.slice(0, 60);
        sessions[sesIdx].messages = msgs; // 缓存消息到 localStorage
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
      // 同步缓存
      syncMessagesToSession(s.currentSessionId, msgs);
      return { messages: msgs };
    }),

  appendToLastAssistant: (chunk) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last?.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, content: last.content + chunk };
      }
      syncMessagesToSession(s.currentSessionId, msgs);
      return { messages: msgs };
    }),

  appendReasoningToLastAssistant: (chunk) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last?.role === 'assistant') {
        msgs[msgs.length - 1] = {
          ...last,
          reasoningContent: (last.reasoningContent || '') + chunk,
        };
      }
      syncMessagesToSession(s.currentSessionId, msgs);
      return { messages: msgs };
    }),

  setStreaming: (v) => set({ isStreaming: v }),
  setSearchEnabled: (v) => set({ searchEnabled: v }),
  setDeepThinkEnabled: (v) => set({ deepThinkEnabled: v }),
  setChatMode: (mode) => set({ chatMode: mode }),
  setAgentProgress: (p) => set({ agentProgress: p }),
  setLastImageAttachment: (attachment) => set({ lastImageAttachment: attachment, selectedImageAttachmentId: imageAttachmentKey(attachment) || null }),
  addImageAttachment: (attachment) =>
    set((s) => {
      const id = imageAttachmentKey(attachment);
      if (!id) return { lastImageAttachment: attachment };
      const history = [attachment, ...s.imageAttachmentHistory.filter((item) => imageAttachmentKey(item) !== id)].slice(0, 8);
      return { lastImageAttachment: attachment, imageAttachmentHistory: history, selectedImageAttachmentId: id };
    }),
  selectImageAttachment: (id) =>
    set((s) => {
      const selected = id ? s.imageAttachmentHistory.find((item) => imageAttachmentKey(item) === id) || null : null;
      return { selectedImageAttachmentId: id, lastImageAttachment: selected || s.lastImageAttachment };
    }),
  setLastDebugInfo: (info) => set({ lastDebugInfo: info }),
  setProgressPipelineSteps: (steps) => set({ progressPipelineSteps: steps }),
  addProgressPipelineStep: (step) =>
    set((s) => {
      if (s.progressPipelineSteps.some((x) => x.key === step.key)) return s;
      return { progressPipelineSteps: [...s.progressPipelineSteps, step] };
    }),
  setSessions: (sessions) => set({ sessions }),
  setQuickCommands: (cmds) => set({ quickCommands: cmds }),
  setLoading: (v) => set({ loading: v }),
  clearMessages: () => set({ messages: [] }),
  newSession: () => {
    const state = get();
    log.debug('创建新会话');
    // 有消息时保存当前会话摘要和消息缓存
    if (state.messages.length > 0) {
      // 先缓存消息
      syncMessagesToSession(state.currentSessionId, state.messages);
      const sessions = loadSessions();
      const existing = sessions.find(s => s.id === state.currentSessionId);
      if (!existing) {
        const firstUser = state.messages.find(m => m.role === 'user');
        sessions.unshift({
          id: state.currentSessionId,
          title: firstUser?.content?.slice(0, 60) || '新对话',
          messages: state.messages, // 缓存消息
          createdAt: state.messages[0]?.timestamp || Date.now(),
          updatedAt: Date.now(),
        });
        persistSessions(sessions);
        set({ sessions });
      }
    }
    const id = createSessionId();
    const now = Date.now();
    const sessions = [{ id, title: '新对话', messages: [], createdAt: now, updatedAt: now }, ...loadSessions().filter((session) => session.id !== id)];
    persistSessionId(id);
    persistSessions(sessions);
    writeStorageItem(runtimeStorageKeys.pendingGeneration, '');
    set({ currentSessionId: id, sessions, messages: [], isStreaming: false, progressPipelineSteps: [], agentProgress: null, lastDebugInfo: null, lastImageAttachment: null, imageAttachmentHistory: [], selectedImageAttachmentId: null });
    void createChatSession({ sessionId: id, learnerId: getStableLearnerId() }).catch((error) => log.warn('Failed to create chat session', error));
  },
  removeLastMessage: () =>
    set((s) => {
      const msgs = s.messages.slice(0, -1);
      // 同步缓存
      syncMessagesToSession(s.currentSessionId, msgs);
      return { messages: msgs };
    }),

  removeSession: (id) =>
    set((s) => {
      const sessions = loadSessions().filter((ses) => ses.id !== id);
      persistSessions(sessions);
      // 如果删除的是当前会话，创建新会话
      if (s.currentSessionId === id) {
        const newId = createSessionId();
        persistSessionId(newId);
        return { sessions, currentSessionId: newId, messages: [], lastImageAttachment: null, imageAttachmentHistory: [], selectedImageAttachmentId: null };
      }
      return { sessions };
    }),

  renameSession: (id, title) =>
    set((s) => {
      const sessions = loadSessions();
      const idx = sessions.findIndex((ses) => ses.id === id);
      if (idx >= 0) {
        sessions[idx].title = title.slice(0, 80);
        persistSessions(sessions);
      }
      return { sessions };
    }),

  bumpDataVersion: () =>
    set((s) => ({ dataVersion: s.dataVersion + 1 })),

  resolveCanonicalSession: () => {
    const learner = getCurrentLearner();
    const subjectStore = useSubjectStore.getState();
    const subjectId = subjectStore.activeSubject?.id ?? subjectStore.activeClassSubject?.subject;
    const key = canonicalRequestKey(learner?.id, subjectId);
    if (!learner || !subjectId) {
      canonicalAbort?.abort();
      canonicalRequest = null;
      canonicalGeneration += 1;
      set({ dataSessionId: '', currentSessionId: '', sessions: [], messages: [], canonicalSession: { status: 'unresolved', subjectId: subjectId || '', sessionId: '', pathId: null, source: '', resolvedAt: null } });
      return Promise.resolve();
    }
    if (canonicalRequest?.key === key) return canonicalRequest.promise;
    if (get().canonicalSession.status === 'resolved' && get().canonicalSession.subjectId === subjectId) return Promise.resolve();

    canonicalAbort?.abort();
    const controller = new AbortController();
    canonicalAbort = controller;
    const generation = ++canonicalGeneration;
    set({ dataSessionId: '', currentSessionId: '', sessions: [], messages: [], canonicalSession: { status: 'resolving', subjectId, sessionId: '', pathId: null, source: '', resolvedAt: null } });
    const promise = getCanonicalSubjectSession(subjectId, controller.signal)
      .then((resolved) => {
        if (generation !== canonicalGeneration || controller.signal.aborted) return;
        if (!resolved) {
          return ensureCanonicalSubjectSession(subjectId).then((ensured) => {
            if (generation !== canonicalGeneration || controller.signal.aborted) return;
            set((state) => ({ currentSessionId: ensured.sessionId, dataSessionId: ensured.sessionId, dataVersion: state.dataVersion + 1, canonicalSession: { status: 'resolved', ...ensured } }));
          });
        }
        set((state) => ({ currentSessionId: resolved.sessionId, dataSessionId: resolved.sessionId, dataVersion: state.dataVersion + 1, canonicalSession: { status: 'resolved', ...resolved } }));
      })
      .catch((error) => {
        if (generation !== canonicalGeneration || controller.signal.aborted) return;
        log.warn('Failed to resolve canonical learning session', error);
        set({ canonicalSession: { status: 'failed', subjectId, sessionId: '', pathId: null, source: '', resolvedAt: null } });
      })
      .finally(() => {
        if (canonicalRequest?.key === key) canonicalRequest = null;
      });
    canonicalRequest = { key, promise };
    return promise;
  },

  /** 科目切换后重新加载该科目下的会话 ID 和会话列表。
   *  家长账户：从后端解析孩子的 session，确保数据查询使用正确的 scope。 */
  reloadSession: async () => {
    return get().resolveCanonicalSession();
    const learner = getCurrentLearner();
    const store = useSubjectStore.getState();
    const subjectId = store.activeSubject?.id ?? store.activeClassSubject?.subject ?? '';

    // Parent: resolve child's session from backend (localStorage has parent's
    // own session which points to empty data).
    if (learner?.role === 'parent' && subjectId) {
      try {
        const childSessionId = await getSubjectSession(subjectId);
        if (childSessionId) {
          // Hydrate sessions and messages from backend for the child
          let parentSessions: ChatSession[] = [];
          let parentMessages: ChatMessage[] = [];
          try {
            const backendRes = await getSessions(subjectId);
            if (backendRes?.sessions?.length) {
              parentSessions = backendRes.sessions.map((s: any) => ({
                id: s.id, title: s.title || '未命名会话', messages: s.messages || [],
                createdAt: s.created_at ? new Date(s.created_at).getTime() : Date.now(),
                updatedAt: s.updated_at ? new Date(s.updated_at).getTime() : Date.now(),
              }));
            }
            const msgRes = await getSessionMessages(childSessionId!);
            if (msgRes?.messages?.length) parentMessages = msgRes.messages;
          } catch { /* best-effort hydration */ }
          set({ currentSessionId: childSessionId!, dataSessionId: childSessionId!, sessions: parentSessions, messages: parentMessages });
          return;
        }
      } catch (err) {
        log.warn('Failed to resolve child session for parent', err);
      }
      // Child has no session yet — clear state so UI shows empty/未创建
      set({ currentSessionId: '', dataSessionId: '', sessions: [], messages: [] });
      return;
    }

    // Student/teacher: currentSessionId from localStorage (chat continuity),
    // dataSessionId from backend (so analytics/profile/path queries find the
    // correct session even when logging in from a different browser).
    const id = loadSessionId();
    const sessions = loadSessions();
    const cachedSession = sessions.find(s => s.id === id);
    const cachedMessages = cachedSession?.messages || [];

    let dataId = id;
    if (subjectId) {
      try {
        const resolvedId = await getSubjectSession(subjectId);
        dataId = resolvedId || dataId;
      } catch { /* fall back to localStorage id */ }
    }

    // ── Hydrate sessions & messages from backend ──
    // On a new browser (empty localStorage), fetch chat history from the
    // server so the user sees their existing sessions and messages.
    let effectiveSessions = sessions;
    let effectiveMessages = cachedMessages;
    if (sessions.length === 0 && subjectId) {
      try {
        const backendRes = await getSessions(subjectId);
        if (backendRes?.sessions?.length) {
          effectiveSessions = backendRes.sessions.map((s: any) => ({
            id: s.id,
            title: s.title || '未命名会话',
            messages: s.messages || [],
            createdAt: s.created_at ? new Date(s.created_at).getTime() : Date.now(),
            updatedAt: s.updated_at ? new Date(s.updated_at).getTime() : Date.now(),
          }));
          persistSessions(effectiveSessions);
          log.info(`Hydrated ${effectiveSessions.length} sessions from backend`);
          // Also load messages for the active data session
          try {
            const msgRes = await getSessionMessages(dataId);
            if (msgRes?.messages?.length) {
              effectiveMessages = msgRes.messages || [];
              // Cache messages in the hydrated session
              const activeIdx = effectiveSessions.findIndex((s: ChatSession) => s.id === dataId);
              if (activeIdx >= 0) {
                effectiveSessions[activeIdx] = { ...effectiveSessions[activeIdx], messages: effectiveMessages };
              }
              persistSessions(effectiveSessions);
              log.info(`Hydrated ${effectiveMessages.length} messages for session ${dataId}`);
            }
          } catch { /* messages fetch best-effort */ }
        }
      } catch (err) {
        log.warn('Failed to hydrate sessions from backend', err);
      }
    }

    // When the server resolves a different session than localStorage
    // (e.g. logging in from a new browser), adopt the server-resolved
    // session for both chat and data queries so the user sees all their
    // existing learning data.
    const effectiveId = dataId !== id ? dataId : id;
    if (dataId !== id) {
      persistSessionId(effectiveId);
    }
    set({ currentSessionId: effectiveId, dataSessionId: effectiveId, sessions: effectiveSessions, messages: effectiveMessages, lastImageAttachment: null, imageAttachmentHistory: [], selectedImageAttachmentId: null });
  },
}));

// ================================================================
// 自动监听科目切换 → 刷新会话
// ================================================================
let prevSubjectId: string | undefined;
let prevClassSubjectId: string | undefined;
useSubjectStore.subscribe((state) => {
  const newId = state.activeSubject?.id ?? state.activeClassSubject?.id;
  if (newId && newId !== prevSubjectId && newId !== prevClassSubjectId) {
    prevSubjectId = state.activeSubject?.id;
    prevClassSubjectId = state.activeClassSubject?.id;
    // 同步刷新，确保 React 同一次渲染中 subjectId 和 sessionId 一致
    useChatStore.getState().reloadSession();
  }
});

// React to auth changes — reload sessions on login/logout
import { useAuthStore } from './authStore';
useAuthStore.subscribe((state, prev) => {
  if (!state.isAuthenticated && state.isAuthenticated !== prev.isAuthenticated) {
    useChatStore.getState().reloadSession();
  }
});

// ================================================================
// 中断生成恢复检测
// ================================================================
/**
 * 检测当前会话是否存在孤儿流式消息（页面离开时中断的生成）。
 * 返回 orphaned sessionId，如果没有则返回 null。
 */
export function detectOrphanedStreaming(): string | null {
  const pending = readStorageJson<{ sessionId: string; userMessage: string; startedAt: number } | null>(
    runtimeStorageKeys.pendingGeneration,
    null,
  );
  if (!pending) return null;

  const state = useChatStore.getState();
  // 只在以下条件同时满足时判定为孤儿：
  // 1. pending 标记指向当前会话
  // 2. store 当前未在流式传输中（不是本标签页的活跃生成）
  // 3. 最后一条消息是 assistant 且 streaming 标记仍为 true
  if (state.currentSessionId !== pending.sessionId) return null;
  if (state.isStreaming) return null;

  const lastMsg = state.messages[state.messages.length - 1];
  if (lastMsg?.role === 'assistant' && lastMsg.streaming) {
    return pending.sessionId;
  }
  return null;
}
