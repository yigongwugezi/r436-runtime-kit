import { useCallback, useEffect, useRef, useState } from 'react';
import { useProfileStore } from '../store/profileStore';
import { useChatStore } from '../store/chatStore';
import * as profileApi from '../api/profile';
import type { StudentProfile } from '../types/profile';

export function useProfile() {
  const store = useProfileStore();
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const dataVersion = useChatStore((state) => state.dataVersion);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const fetchedSessionRef = useRef<string | null>(null);
  const lastVersionRef = useRef<number>(0);

  const fetchProfile = useCallback(async () => {
    setLoading(true);
    setError(null);
    store.setLoading(true);
    try {
      const res = await profileApi.getProfile(currentSessionId);
      if (res?.profile) {
        store.setProfile(res.profile);
      } else {
        store.setError('画像数据为空');
        setError('画像数据为空');
      }
    } catch {
      const msg = '加载画像失败，请稍后重试';
      store.setError(msg);
      setError(msg);
    } finally {
      setLoading(false);
      store.setLoading(false);
    }
  }, [currentSessionId, store]);

  const buildProfile = useCallback(
    async (message: string): Promise<StudentProfile | null> => {
      setLoading(true);
      try {
        const res = await profileApi.buildProfile({ message, sessionId: currentSessionId });
        if (res?.profile) {
          store.setProfile(res.profile);
        }
        return res?.profile || null;
      } catch {
        store.setError('画像构建失败');
        return null;
      } finally {
        setLoading(false);
      }
    },
    [currentSessionId, store],
  );

  useEffect(() => {
    if (fetchedSessionRef.current !== currentSessionId) {
      fetchedSessionRef.current = currentSessionId;
      fetchProfile();
    }
  }, [currentSessionId, fetchProfile]);

  // 对话完成后自动刷新画像
  useEffect(() => {
    if (dataVersion > 0 && dataVersion !== lastVersionRef.current) {
      lastVersionRef.current = dataVersion;
      fetchProfile();
    }
  }, [dataVersion, fetchProfile]);

  return { ...store, loading, error, fetchProfile, buildProfile };
}
