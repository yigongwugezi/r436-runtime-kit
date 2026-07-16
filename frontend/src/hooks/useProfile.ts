import { useCallback, useEffect, useRef, useState } from 'react';
import { useProfileStore } from '../store/profileStore';
import { useChatStore } from '../store/chatStore';
import * as profileApi from '../api/profile';
import type { StudentProfile } from '../types/profile';

/** Read a profile from the current session's server-owned scope.
 *
 * A browser's previously selected subject is UI state, not permission to
 * attach that subject to a newly created conversation.
 */
export function useProfile() {
  const store = useProfileStore();
  const sessionId = useChatStore((state) => state.dataSessionId);
  const dataVersion = useChatStore((state) => state.dataVersion);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lastReadKeyRef = useRef<string | undefined>(undefined);
  const lastVersionRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  /** 递增计数器，用于判断 fetchProfile 返回时是否还有更新的请求已发出。 */
  const fetchGenRef = useRef(0);

  const fetchProfile = useCallback(async () => {
    const currentSessionId = sessionId;
    if (!currentSessionId) {
      setLoading(false);
      return;
    }

    // 取消上一次未完成的请求
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    // 记录此次请求的代数
    const gen = ++fetchGenRef.current;

    setLoading(true);
    setError(null);
    store.setLoading(currentSessionId, true);
    try {
      const res = await profileApi.getProfile({ sessionId: currentSessionId });

      // 请求完成后如果已有更新的 fetch 发出，则丢弃旧结果
      if (gen !== fetchGenRef.current || controller.signal.aborted) return;
      // 如果 sessionId 在此期间发生了变化，也丢弃
      if (useChatStore.getState().dataSessionId !== currentSessionId) return;

      if (res?.profile) {
        store.setProfile(currentSessionId, res.profile);
      } else {
        const message = '画像数据为空';
        store.setError(currentSessionId, message);
        setError(message);
      }
    } catch (cause) {
      if (gen !== fetchGenRef.current || controller.signal.aborted) return;
      if (useChatStore.getState().dataSessionId !== currentSessionId) return;

      const message = cause instanceof Error ? cause.message : '加载画像失败';
      // 如果后端报 sessionId 为空（实际是竞态导致），转成更友好的提示
      const displayMessage = message.includes('sessionId')
        ? '会话尚未就绪，请稍后重试'
        : message;
      store.setError(currentSessionId, displayMessage);
      setError(displayMessage);
    } finally {
      if (gen === fetchGenRef.current && !controller.signal.aborted) {
        setLoading(false);
        store.setLoading(currentSessionId, false);
      }
    }
  }, [sessionId, store]);

  const buildProfile = useCallback(async (message: string): Promise<StudentProfile | null> => {
    if (!sessionId) return null;
    setLoading(true);
    try {
      const res = await profileApi.buildProfile({ message, sessionId });
      if (res?.profile) store.setProfile(sessionId, res.profile);
      return res?.profile || null;
    } catch {
      store.setError(sessionId, '画像构建失败');
      return null;
    } finally {
      setLoading(false);
    }
  }, [sessionId, store]);

  useEffect(() => {
    const readKey = sessionId || undefined;
    if (lastReadKeyRef.current !== readKey) {
      lastReadKeyRef.current = readKey;
      void fetchProfile();
    }
  }, [sessionId, fetchProfile]);

  useEffect(() => {
    if (sessionId && dataVersion > 0 && dataVersion !== lastVersionRef.current) {
      lastVersionRef.current = dataVersion;
      void fetchProfile();
    }
  }, [dataVersion, fetchProfile, sessionId]);

  const profile = sessionId ? store.profiles[sessionId] ?? null : null;
  const profileError = sessionId ? store.errorMap[sessionId] ?? null : null;
  return { profile, profileV2: profile?.profileV2 ?? null, loading, error: error || profileError, fetchProfile, buildProfile };
}
