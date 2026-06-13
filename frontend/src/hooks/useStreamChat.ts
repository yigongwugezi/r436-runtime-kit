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
    isStreaming,
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
          // 处理 SSE 格式: data: {...}\n\n
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const payload = JSON.parse(line.slice(6));
                if (payload.content) {
                  appendToLastAssistant(payload.content);
                }
                if (payload.done) {
                  updateLastAssistant((m) => ({ ...m, streaming: false }));
                }
              } catch {
                // 非 JSON 片段直接拼接
                appendToLastAssistant(line.slice(6));
              }
            }
          }
        }

        updateLastAssistant((m) => ({ ...m, streaming: false }));
      } catch (err) {
        updateLastAssistant((m) => ({
          ...m,
          streaming: false,
          error: err instanceof Error ? err.message : '请求失败',
        }));
      } finally {
        setStreaming(false);
      }
    },
    [addMessage, appendToLastAssistant, updateLastAssistant, setStreaming, isStreaming],
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
    updateLastAssistant((m) => ({ ...m, streaming: false }));
    setStreaming(false);
  }, [updateLastAssistant, setStreaming]);

  return { send, abort, isStreaming };
}
