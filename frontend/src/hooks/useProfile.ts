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

  const fetchProfile = useCallback(async () => {
    if (!sessionId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    store.setLoading(sessionId, true);
    try {
      const res = await profileApi.getProfile({ sessionId });
      if (res?.profile) {
        store.setProfile(sessionId, res.profile);
      } else {
        const message = '画像数据为空';
        store.setError(sessionId, message);
        setError(message);
      }
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : '加载画像失败';
      store.setError(sessionId, message);
      setError(message);
    } finally {
      setLoading(false);
      store.setLoading(sessionId, false);
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
    if (dataVersion > 0 && dataVersion !== lastVersionRef.current) {
      lastVersionRef.current = dataVersion;
      void fetchProfile();
    }
  }, [dataVersion, fetchProfile]);

  const profile = sessionId ? store.profiles[sessionId] ?? null : null;
  const profileError = sessionId ? store.errorMap[sessionId] ?? null : null;
  return { profile, profileV2: profile?.profileV2 ?? null, loading, error: error || profileError, fetchProfile, buildProfile };
}
