import { useCallback, useEffect, useRef, useState } from 'react';
import { getLearningTimeline } from '../api/timeline';
import type { TimelineEvent } from '../types/timeline';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';

/**
 * 学习事件时间线 Hook
 *
 * 特性：
 * - sessionId / subjectId 变化时自动刷新
 * - 支持事件类型 (type) 和时间范围 (range) 筛选 — 后端过滤
 * - 暴露 loading / error / refetch
 * - 内置不重复请求保护
 */
export function useLearningEvents(limit = 100, type?: string, range?: number) {
  const sessionId = useChatStore((s) => s.dataSessionId);
  const subjectId = useSubjectStore((s) => s.activeSubject?.id);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lastKeyRef = useRef<string | undefined>(undefined);

  const fetchEvents = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    setEvents([]);  // 切换科目时立即清空旧数据
    setTotal(0);
    try {
      const res = await getLearningTimeline(sessionId, subjectId, limit, type, range);
      setEvents(res.events || []);
      setTotal(res.total || 0);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载学习时间线失败');
      setEvents([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [sessionId, subjectId, limit, type, range]);

  useEffect(() => {
    const key = sessionId ? `${sessionId}:${subjectId}:${limit}:${type ?? ''}:${range ?? 0}` : undefined;
    if (key && lastKeyRef.current !== key) {
      lastKeyRef.current = key;
      fetchEvents();
    }
  }, [sessionId, subjectId, limit, type, range, fetchEvents]);

  return { events, total, loading, error, refetch: fetchEvents };
}
