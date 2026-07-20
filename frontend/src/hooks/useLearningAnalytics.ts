import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { getAnalytics } from '../api/analytics';
import type { AnalyticsSummary } from '../types/analytics';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';
import { canLoadCanonicalData } from '../utils/canonicalSessionState';

/**
 * 学习分析数据 Hook
 *
 * 特性：
 * - 科目切换时自动重新获取
 * - dataVersion 变化时自动刷新
 * - 页面可见性变化时自动刷新
 * - 暴露 loading / error / refetch
 * - 内置请求去重
 */
export function useLearningAnalytics() {
  const location = useLocation();
  const subjectId = useSubjectStore((s) => s.activeSubject?.id ?? s.activeClassSubject?.subject);
  const sessionId = useChatStore((state) => state.dataSessionId);
  const canonicalStatus = useChatStore((state) => state.canonicalSession.status);
  const dataVersion = useChatStore((state) => state.dataVersion);
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lastSubjectRef = useRef<string | undefined>(undefined);
  const lastVersionRef = useRef<number>(0);
  const lastKeyRef = useRef<string | undefined>(undefined);
  const abortRef = useRef<AbortController | null>(null);

  const fetchAnalytics = useCallback(async () => {
    if (!subjectId || !canLoadCanonicalData(canonicalStatus, sessionId)) { setLoading(false); return; }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    setAnalytics(null);  // 切换科目时立即清空旧数据
    try {
      const data = await getAnalytics({ sessionId, subjectId }, controller.signal);
      if (controller.signal.aborted || useChatStore.getState().dataSessionId !== sessionId) return;
      setAnalytics(data);
    } catch (e) {
      if (controller.signal.aborted) return;
      setError(e instanceof Error ? e.message : '加载分析数据失败');
    } finally {
      setLoading(false);
    }
  }, [canonicalStatus, subjectId, sessionId]);

  // 每次进入页面时刷新 + 科目切换
  useEffect(() => {
    const key = subjectId ? `${sessionId}:${subjectId}` : 'none';
    if (canonicalStatus === 'resolved' && subjectId) {
      if (lastKeyRef.current !== key || !analytics) {
        lastKeyRef.current = key;
        fetchAnalytics();
      }
    } else {
      setLoading(false);
      setError(null);
      setAnalytics(null);
    }
    const onVisible = () => {
      if (document.visibilityState === 'visible' && canonicalStatus === 'resolved' && subjectId) {
        fetchAnalytics();
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canonicalStatus, subjectId, location.key, fetchAnalytics]);

  // 对话完成后自动刷新
  useEffect(() => {
    if (canonicalStatus === 'resolved' && dataVersion > 0 && dataVersion !== lastVersionRef.current) {
      lastVersionRef.current = dataVersion;
      fetchAnalytics();
    }
  }, [canonicalStatus, dataVersion, fetchAnalytics]);
  useEffect(() => () => abortRef.current?.abort(), []);

  return { analytics, loading, error, refetch: fetchAnalytics };
}
