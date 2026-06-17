import { useCallback, useRef } from 'react';
import { useChatStore } from '../store/chatStore';
import { streamRequest } from '../api/client';
import { sendMessage } from '../api/chat';
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

      const userMsg: ChatMessage = {
        id: uid(),
        role: 'user',
        content: content.trim(),
        timestamp: Date.now(),
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
                if (payload.stage || payload.agentName) {
                  setAgentProgress({
                    stage: payload.stage || payload.agentName,
                    progress: payload.progress || 0,
                    agentName: payload.agentName,
                    detail: payload.detail,
                  });
                }
                if (payload.content) {
                  appendToLastAssistant(payload.content);
                }
                if (payload.done) {
                  updateLastAssistant((m) => ({ ...m, streaming: false }));
                  setAgentProgress(null);
                }
              } catch {
                appendToLastAssistant(line.slice(6));
              }
            }
          }
        }

        updateLastAssistant((m) => ({ ...m, streaming: false }));
        setAgentProgress(null);
        bumpDataVersion();
      } catch (err) {
        try {
          const fallback = await sendMessage({
            message: content.trim(),
            sessionId: useChatStore.getState().currentSessionId,
          });
          updateLastAssistant((m) => ({
            ...m,
            content: fallback.reply.content,
            timestamp: fallback.reply.timestamp,
            streaming: false,
            error: undefined,
          }));
          bumpDataVersion();
        } catch (fallbackErr) {
          updateLastAssistant((m) => ({
            ...m,
            streaming: false,
            error:
              fallbackErr instanceof Error
                ? fallbackErr.message
                : err instanceof Error
                  ? err.message
                  : 'request failed',
          }));
        } finally {
          setAgentProgress(null);
        }
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
