import { useCallback, useEffect, useRef, useState } from 'react';
import { useProfileStore } from '../store/profileStore';
import * as profileApi from '../api/profile';
import type { StudentProfile } from '../types/profile';

export function useProfile() {
  const store = useProfileStore();
  const [loading, setLoading] = useState(false);
  const fetchedRef = useRef(false);

  const fetchProfile = useCallback(async () => {
    setLoading(true);
    store.setLoading(true);
    try {
      const res = await profileApi.getProfile();
      if (res?.profile) {
        store.setProfile(res.profile);
      }
    } catch {
      store.setError('加载画像失败，请稍后重试');
    } finally {
      setLoading(false);
      store.setLoading(false);
    }
  }, []); // 只创建一次，避免循环触发

  const buildProfile = useCallback(
    async (message: string): Promise<StudentProfile | null> => {
      setLoading(true);
      try {
        const res = await profileApi.buildProfile({ message });
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
    [store],
  );

  useEffect(() => {
    if (!store.profile && !fetchedRef.current) {
      fetchedRef.current = true;
      fetchProfile();
    }
  }, [store.profile, fetchProfile]);

  return { ...store, loading, fetchProfile, buildProfile };
}
