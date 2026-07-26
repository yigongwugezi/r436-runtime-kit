import { useCallback, useEffect, useRef, useState } from 'react';
import { useProfileStore } from '../store/profileStore';
import { useChatStore } from '../store/chatStore';
import * as profileApi from '../api/profile';
import type { StudentProfile } from '../types/profile';
import { canLoadCanonicalData } from '../utils/canonicalSessionState';

const profileRequests = new Map<string, Promise<StudentProfile | null>>();

function readProfile(sessionId: string, subjectId: string): Promise<StudentProfile | null> {
  const requestKey = `${sessionId}|${subjectId}`;
  let request = profileRequests.get(requestKey);
  if (!request) {
    request = profileApi.getProfile({ sessionId, subjectId }).then((result) => result?.profile ?? null).finally(() => profileRequests.delete(requestKey));
    profileRequests.set(requestKey, request);
  }
  return request;
}

export function useProfile() {
  const sessionId = useChatStore((state) => state.dataSessionId);
  const canonicalStatus = useChatStore((state) => state.canonicalSession.status);
  const subjectId = useChatStore((state) => state.canonicalSession.subjectId);
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
    const currentSubjectId = subjectId;
    if (!canLoadCanonicalData(canonicalStatus, currentSessionId) || !currentSubjectId) {
      fetchGenRef.current += 1;
      setLoading(false);
      return;
    }
    const generation = ++fetchGenRef.current;
    setLoading(true); setEmpty(false); setError(null); setStoreLoading(currentSessionId, true);
    try {
      const nextProfile = await readProfile(currentSessionId, currentSubjectId);
      const currentCanonical = useChatStore.getState().canonicalSession;
      if (generation !== fetchGenRef.current || useChatStore.getState().dataSessionId !== currentSessionId || currentCanonical.subjectId !== currentSubjectId) return;
      if (nextProfile) {
        setProfile(currentSessionId, nextProfile);
        setEmpty(!nextProfile.profileV2);
      } else setEmpty(true);
    } catch (cause) {
      const currentCanonical = useChatStore.getState().canonicalSession;
      if (generation !== fetchGenRef.current || useChatStore.getState().dataSessionId !== currentSessionId || currentCanonical.subjectId !== currentSubjectId) return;
      const message = cause instanceof Error ? cause.message : '加载画像失败';
      const displayMessage = message.includes('sessionId') ? '会话尚未就绪，请稍后重试' : message;
      setStoreError(currentSessionId, displayMessage); setError(displayMessage);
    } finally {
      if (generation === fetchGenRef.current) { setLoading(false); setStoreLoading(currentSessionId, false); }
    }
  }, [canonicalStatus, sessionId, subjectId, setProfile, setStoreError, setStoreLoading]);

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
    const readKey = sessionId && subjectId ? `${sessionId}|${subjectId}` : undefined;
    if (lastReadKeyRef.current !== readKey) { lastReadKeyRef.current = readKey; void fetchProfile(); }
  }, [canonicalStatus, sessionId, subjectId, fetchProfile]);

  useEffect(() => {
    if (canonicalStatus === 'resolved' && sessionId && subjectId && dataVersion > 0 && dataVersion !== lastVersionRef.current) {
      lastVersionRef.current = dataVersion; void fetchProfile();
    }
  }, [canonicalStatus, dataVersion, fetchProfile, sessionId, subjectId]);

  return { profile, profileV2: profile?.profileV2 ?? null, loading, empty, error: error || profileError, fetchProfile, buildProfile };
}
