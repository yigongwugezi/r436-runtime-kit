import { useCallback, useEffect, useRef, useState } from 'react';
import { useProfileStore } from '../store/profileStore';
import { useChatStore } from '../store/chatStore';
import * as profileApi from '../api/profile';
import type { StudentProfile } from '../types/profile';
import { canLoadCanonicalData } from '../utils/canonicalSessionState';

const profileRequests = new Map<string, Promise<StudentProfile | null>>();

function readProfile(sessionId: string): Promise<StudentProfile | null> {
  let request = profileRequests.get(sessionId);
  if (!request) {
    request = profileApi.getProfile({ sessionId }).then((result) => result?.profile ?? null).finally(() => profileRequests.delete(sessionId));
    profileRequests.set(sessionId, request);
  }
  return request;
}

export function useProfile() {
  const sessionId = useChatStore((state) => state.dataSessionId);
  const canonicalStatus = useChatStore((state) => state.canonicalSession.status);
  const dataVersion = useChatStore((state) => state.dataVersion);
  const profile = useProfileStore((state) => sessionId ? state.profiles[sessionId] ?? null : null);
  const profileError = useProfileStore((state) => sessionId ? state.errorMap[sessionId] ?? null : null);
  const setProfile = useProfileStore((state) => state.setProfile);
  const setStoreLoading = useProfileStore((state) => state.setLoading);
  const setStoreError = useProfileStore((state) => state.setError);
  const [loading, setLoading] = useState(true);
  const [empty, setEmpty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastReadKeyRef = useRef<string | undefined>(undefined);
  const lastVersionRef = useRef(0);
  const fetchGenRef = useRef(0);

  const fetchProfile = useCallback(async () => {
    const currentSessionId = sessionId;
    if (!canLoadCanonicalData(canonicalStatus, currentSessionId)) {
      fetchGenRef.current += 1;
      setLoading(false);
      return;
    }
    const generation = ++fetchGenRef.current;
    setLoading(true); setEmpty(false); setError(null); setStoreLoading(currentSessionId, true);
    try {
      const nextProfile = await readProfile(currentSessionId);
      if (generation !== fetchGenRef.current || useChatStore.getState().dataSessionId !== currentSessionId) return;
      if (nextProfile) {
        setProfile(currentSessionId, nextProfile);
        setEmpty(!nextProfile.profileV2);
      } else setEmpty(true);
    } catch (cause) {
      if (generation !== fetchGenRef.current || useChatStore.getState().dataSessionId !== currentSessionId) return;
      const message = cause instanceof Error ? cause.message : '加载画像失败';
      const displayMessage = message.includes('sessionId') ? '会话尚未就绪，请稍后重试' : message;
      setStoreError(currentSessionId, displayMessage); setError(displayMessage);
    } finally {
      if (generation === fetchGenRef.current) { setLoading(false); setStoreLoading(currentSessionId, false); }
    }
  }, [canonicalStatus, sessionId, setProfile, setStoreError, setStoreLoading]);

  const buildProfile = useCallback(async (message: string): Promise<StudentProfile | null> => {
    if (!sessionId) return null;
    setLoading(true);
    try {
      const result = await profileApi.buildProfile({ message, sessionId });
      if (result?.profile) setProfile(sessionId, result.profile);
      return result?.profile || null;
    } catch {
      setStoreError(sessionId, '画像构建失败'); return null;
    } finally { setLoading(false); }
  }, [sessionId, setProfile, setStoreError]);

  useEffect(() => {
    const readKey = sessionId || undefined;
    if (lastReadKeyRef.current !== readKey) { lastReadKeyRef.current = readKey; void fetchProfile(); }
  }, [canonicalStatus, sessionId, fetchProfile]);

  useEffect(() => {
    if (canonicalStatus === 'resolved' && sessionId && dataVersion > 0 && dataVersion !== lastVersionRef.current) {
      lastVersionRef.current = dataVersion; void fetchProfile();
    }
  }, [canonicalStatus, dataVersion, fetchProfile, sessionId]);

  return { profile, profileV2: profile?.profileV2 ?? null, loading, empty, error: error || profileError, fetchProfile, buildProfile };
}
