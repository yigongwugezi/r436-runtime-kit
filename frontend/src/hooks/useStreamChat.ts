import { useCallback, useRef } from 'react';
import { useChatStore } from '../store/chatStore';
import { streamRequest } from '../api/client';
import type { ChatMessage } from '../types/chat';
import { uid } from '../utils/format';

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

  const send = useCallback(
    async (content: string) => {
      if (isStreaming || !content.trim()) return;

      // 添加用户消息
      const userMsg: ChatMessage = {
        id: uid(),
        role: 'user',
        content: content.trim(),
        timestamp: Date.now(),
      };
      addMessage(userMsg);

      // 添加 AI 占位消息
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

      try {
        const reader = await streamRequest('/chat/stream', {
          message: content.trim(),
          sessionId: useChatStore.getState().currentSessionId,
        });

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
                // 处理进度消息
                if (payload.stage || payload.agentName) {
                  setAgentProgress({
                    stage: payload.stage || payload.agentName,
                    progress: payload.progress || 0,
                    agentName: payload.agentName,
                    detail: payload.detail,
                  });
                }
                // 处理内容消息
                if (payload.content) {
                  appendToLastAssistant(payload.content);
                }
                // 处理完成标记
                if (payload.done) {
                  updateLastAssistant((m) => ({ ...m, streaming: false }));
                  setAgentProgress(null);
                }
              } catch {
                // 非 JSON 片段直接拼接
                appendToLastAssistant(line.slice(6));
              }
            }
          }
        }

        updateLastAssistant((m) => ({ ...m, streaming: false }));
        setAgentProgress(null);
        // 对话完成，触发画像/路径/资源页面刷新
        bumpDataVersion();
      } catch (err) {
        updateLastAssistant((m) => ({
          ...m,
          streaming: false,
          error: err instanceof Error ? err.message : '请求失败',
        }));
        setAgentProgress(null);
      } finally {
        setStreaming(false);
      }
    },
    [addMessage, appendToLastAssistant, updateLastAssistant, setStreaming, setAgentProgress, isStreaming, bumpDataVersion],
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
    updateLastAssistant((m) => ({ ...m, streaming: false }));
    setAgentProgress(null);
    setStreaming(false);
  }, [updateLastAssistant, setStreaming, setAgentProgress]);

  return { send, abort, isStreaming };
}
