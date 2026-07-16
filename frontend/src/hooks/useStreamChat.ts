import { useCallback, useRef } from 'react';
import { imageAttachmentKey, useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';
import { getStableLearnerId } from '../store/authStore';
import { streamRequest } from '../api/client';
import { sendMessage } from '../api/chat';
import type { ChatAttachment, ChatMessage } from '../types/chat';
import { uid } from '../utils/format';
import { createLogger } from '../utils/logger';
import { runtimeStorageKeys, writeStorageJson, writeStorageItem } from '../utils/storageKeys';

const log = createLogger('StreamChat');

const IMAGE_REFERENCE_RE = /(这张图|这张图片|上面这张图|刚才那张图|图中|图片里|这道题|这页笔记|题图|错题图|继续讲第\s*[0-9一二两三四五六七八九十]+\s*题)/;

const DEBUG_FIELDS = ['action', 'confidence', 'should_run_pipeline', 'skip_pipeline',
  'skip_reason', 'agents_run', 'final_reply_owner', 'reply_source', 'fallback_used',
  'llm_retry_count', 'pipeline_executed', 'learning_path_created', 'resources_created',
  'questions_created', 'current_agent', 'warnings'];

function setDebugInfoFromPayload(payload: Record<string, unknown>) {
  const debugInfo: Record<string, unknown> = {};
  for (const key of DEBUG_FIELDS) {
    if (key in payload) debugInfo[key] = payload[key];
  }
  if (Object.keys(debugInfo).length > 0) {
    useChatStore.getState().setLastDebugInfo(debugInfo);
  }
}

function applyCurrentSubject(value: unknown) {
  if (!value || typeof value !== 'object') return;
  const source = value as Record<string, unknown>;
  const id = String(source.id || '').trim();
  const name = String(source.name || '').trim();
  if (!id || !name) return;
  const now = Date.now();
  useSubjectStore.getState().setActive({
    id,
    name,
    description: typeof source.description === 'string' ? source.description : undefined,
    createdAt: Number(source.created_at) || now,
    updatedAt: Number(source.updated_at) || now,
  });
}

export function useStreamChat() {
  const {
    addMessage,
    appendToLastAssistant,
    updateLastAssistant,
    setStreaming,
    setAgentProgress,
    isStreaming,
    bumpDataVersion,
  } = useChatStore();
  const abortRef = useRef<AbortController | null>(null);
  const userAbortedRef = useRef(false);  // distinguish user stop-click from page-unload abort

  const send = useCallback(
    async (content: string, attachments: ChatAttachment[] = [], options: { ignoreImageContext?: boolean; imageProvider?: string } = {}) => {
      if (isStreaming || (!content.trim() && attachments.length === 0)) return;
      const text = content.trim() || '识别这张图片';
      const store = useChatStore.getState();
      const ignoreImageContext = options.ignoreImageContext === true;
      const selectedImageAttachment = store.imageAttachmentHistory.find(
        (item) => imageAttachmentKey(item) === store.selectedImageAttachmentId,
      ) || store.lastImageAttachment;
      const requestAttachments =
        !ignoreImageContext && attachments.length === 0 && selectedImageAttachment && IMAGE_REFERENCE_RE.test(text)
          ? [{ ...selectedImageAttachment, reused_from_last: true }]
          : attachments;
      if (attachments[0]) store.addImageAttachment(attachments[0]);

      const userMsg: ChatMessage = {
        id: uid(),
        role: 'user',
        content: text,
        timestamp: Date.now(),
        attachments: requestAttachments,
      };
      addMessage(userMsg);

      const aiMsg: ChatMessage = {
        id: uid(),
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
        streaming: true,
      };
      addMessage(aiMsg);

      setStreaming(true);
      setAgentProgress(null);
      useChatStore.getState().setProgressPipelineSteps([]);

      // 写入 pending marker，用于跨页面导航恢复
      writeStorageJson(runtimeStorageKeys.pendingGeneration, {
        sessionId: useChatStore.getState().currentSessionId,
        userMessage: text,
        startedAt: Date.now(),
      });

      // 创建 AbortController，支持用户点击停止按钮
      const controller = new AbortController();
      abortRef.current = controller;

      let hasRealAgentProgress = false;  // 追踪是否真的有智能体执行了

      try {
        const reader = await streamRequest('/api/chat/stream', {
          message: text,
          sessionId: useChatStore.getState().currentSessionId,
          learnerId: getStableLearnerId(),
          attachments: requestAttachments,
          ignore_image_context: ignoreImageContext,
          image_provider: options.imageProvider || '',
        }, controller.signal);

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const payload = JSON.parse(line.slice(6));
                if (payload.stage || payload.agentName) {
                  // 标记是否真正进入智能体阶段（非初始"理解需求"和"保存结果"）
                  if (payload.agentName && !['understanding', 'saving'].includes(payload.agentName)) {
                    hasRealAgentProgress = true;
                    // 动态构建进度条步骤
                    useChatStore.getState().addProgressPipelineStep({
                      key: payload.agentName,
                      label: payload.stage || payload.agentName,
                    });
                  }
                  setAgentProgress({
                    stage: payload.stage || payload.agentName,
                    progress: payload.progress || 0,
                    agentName: payload.agentName,
                    detail: payload.detail,
                    error: payload.error,
                    done: payload.done,
                  });
                }
                if (payload.isClarification) {
                  updateLastAssistant((m) => ({ ...m, isClarification: true }));
                }
                if (payload.content) {
                  appendToLastAssistant(payload.content);
                }
                if (payload.done) {
                  // Store debug info from final event (dev-only, §13.2)
                  setDebugInfoFromPayload(payload);
                  applyCurrentSubject(payload.current_subject);

                  // Clear pending marker — generation ended
                  writeStorageItem(runtimeStorageKeys.pendingGeneration, '');
                  if (payload.error) {
                    updateLastAssistant((m) => ({
                      ...m,
                      streaming: false,
                      error: payload.error,
                    }));
                    // 失败状态 5 秒后自动收起
                    setTimeout(() => setAgentProgress(null), 5000);
                  } else {
                    updateLastAssistant((m) => ({
                      ...m,
                      streaming: false,
                      multimodalResult: payload.multimodal_result || m.multimodalResult,
                    }));
                    // 确保 agentProgress 标记为完成（done 事件可能不带 agentName）
                    const cur = useChatStore.getState().agentProgress;
                    if (cur && !cur.done) {
                      if (hasRealAgentProgress) {
                        setAgentProgress({ ...cur, done: true, progress: 100 });
                      } else {
                        setAgentProgress(null);
                      }
                    }
                    // 成功状态不清除 — 跳转按钮常驻，新对话开始时会自动重置
                  }
                }
              } catch (parseErr) {
                log.debug('SSE 非 JSON 行', line.slice(0, 80), parseErr);
                appendToLastAssistant(line.slice(6));
              }
            }
          }
        }

        bumpDataVersion();
      } catch (err) {
        // 用户主动停止 — 不需要回退，直接结束
        if (err instanceof DOMException && err.name === 'AbortError') {
          // userAbortedRef=true → user clicked stop button → clear marker
          // userAbortedRef=false → page unload/refresh → keep marker for recovery
          if (userAbortedRef.current) {
            log.debug('用户主动停止生成');
            writeStorageItem(runtimeStorageKeys.pendingGeneration, '');
            userAbortedRef.current = false;
          } else {
            log.debug('页面离开导致流中断，保留 pending marker 用于恢复');
          }
          updateLastAssistant((m) => ({ ...m, streaming: false }));
          setAgentProgress(null);
          return;
        }
        log.warn('流式请求失败，尝试非流式回退', err instanceof Error ? err.message : err);
        try {
          const fallback = await sendMessage({
            message: text,
            sessionId: useChatStore.getState().currentSessionId,
            learnerId: getStableLearnerId(),
            attachments: requestAttachments,
            ignore_image_context: ignoreImageContext,
            image_provider: options.imageProvider || '',
          });
          log.info('非流式回退成功');
          setDebugInfoFromPayload(fallback as unknown as Record<string, unknown>);
          applyCurrentSubject(fallback.current_subject);
          writeStorageItem(runtimeStorageKeys.pendingGeneration, '');
          const cur = useChatStore.getState().agentProgress;
          if (cur && !cur.done) setAgentProgress({ ...cur, done: true, progress: 100 });
          updateLastAssistant((m) => ({
            ...m,
            content: fallback.reply.content,
            timestamp: fallback.reply.timestamp,
            streaming: false,
            multimodalResult: fallback.multimodal_result || m.multimodalResult,
            error: undefined,
          }));
          bumpDataVersion();
        } catch (fallbackErr) {
          log.error('非流式回退也失败', fallbackErr instanceof Error ? fallbackErr.message : fallbackErr);
          updateLastAssistant((m) => ({
            ...m,
            streaming: false,
            error:
              fallbackErr instanceof Error
                ? fallbackErr.message
                : err instanceof Error
                  ? err.message
                  : '请求失败，请检查后端服务是否运行',
          }));
          // Show error progress briefly
          setAgentProgress({
            stage: '生成失败',
            progress: 0,
            agentName: 'failed',
            error: fallbackErr instanceof Error ? fallbackErr.message : '请求失败',
            done: true,
          });
          setTimeout(() => setAgentProgress(null), 5000);
        }
      } finally {
        setStreaming(false);
        // pending marker cleared selectively:
        // - success path (payload.done) → cleared above
        // - user abort path (abort function) → cleared before calling abort()
        // - page-unload path (AbortError, userAbortedRef=false) → NOT cleared (preserved for recovery)
      }
    },
    [addMessage, appendToLastAssistant, updateLastAssistant, setStreaming, setAgentProgress, isStreaming, bumpDataVersion],
  );

  const abort = useCallback(() => {
    // Mark as user-initiated so AbortError handler knows to clear pending marker
    userAbortedRef.current = true;
    writeStorageItem(runtimeStorageKeys.pendingGeneration, '');
    abortRef.current?.abort();
    updateLastAssistant((m) => ({ ...m, streaming: false }));
    setAgentProgress(null);
    setStreaming(false);
  }, [updateLastAssistant, setStreaming, setAgentProgress]);

  return { send, abort, isStreaming };
}
