import { useCallback, useEffect, useRef, useState } from 'react';
import { useProfileStore } from '../store/profileStore';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';
import * as profileApi from '../api/profile';
import type { StudentProfile } from '../types/profile';

export function useProfile() {
  const store = useProfileStore();
  const subjectId = useSubjectStore((s) => s.activeSubject?.id);
  const sessionId = useChatStore((state) => state.currentSessionId);
  const dataVersion = useChatStore((state) => state.dataVersion);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lastReadKeyRef = useRef<string | undefined>(undefined);
  const lastVersionRef = useRef<number>(0);

  const fetchProfile = useCallback(async () => {
    if (!subjectId) return;
    setLoading(true);
    setError(null);
    store.setLoading(subjectId, true);
    try {
      const res = await profileApi.getProfile({ sessionId, subjectId });
      if (res?.profile) {
        store.setProfile(subjectId, res.profile);
      } else {
        store.setError(subjectId, '画像数据为空');
        setError('画像数据为空');
      }
    } catch {
      const msg = '加载画像失败，请稍后重试';
      store.setError(subjectId, msg);
      setError(msg);
    } finally {
      setLoading(false);
      store.setLoading(subjectId, false);
    }
  }, [sessionId, subjectId, store]);

  const buildProfile = useCallback(
    async (message: string): Promise<StudentProfile | null> => {
      if (!subjectId) return null;
      setLoading(true);
      try {
        const res = await profileApi.buildProfile({ message, sessionId, subjectId });
        if (res?.profile) {
          store.setProfile(subjectId, res.profile);
        }
        return res?.profile || null;
      } catch {
        store.setError(subjectId, '画像构建失败');
        return null;
      } finally {
        setLoading(false);
      }
    },
    [sessionId, subjectId, store],
  );

  // 科目切换时重新获取画像
  useEffect(() => {
    const readKey = subjectId ? `${sessionId}:${subjectId}` : undefined;
    if (readKey && lastReadKeyRef.current !== readKey) {
      lastReadKeyRef.current = readKey;
      fetchProfile();
    }
  }, [sessionId, subjectId, fetchProfile]);

  // 对话完成后自动刷新画像
  useEffect(() => {
    if (dataVersion > 0 && dataVersion !== lastVersionRef.current) {
      lastVersionRef.current = dataVersion;
      fetchProfile();
    }
  }, [dataVersion, fetchProfile]);

  // 返回当前科目的数据
  const profile = subjectId ? store.profiles[subjectId] ?? null : null;
  const profileError = subjectId ? store.errorMap[subjectId] ?? null : null;

  return { profile, loading, error: error || profileError, fetchProfile, buildProfile };
}
