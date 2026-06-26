import { useCallback, useEffect, useRef, useState } from 'react';
import * as resourcesApi from '../api/resources';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';
import type { Resource, ResourceFilter } from '../types/resource';

export function useResources(initialFilter?: ResourceFilter) {
  const subjectId = useSubjectStore((s) => s.activeSubject?.id);
  const sessionId = useChatStore((state) => state.dataSessionId);
  const dataVersion = useChatStore((state) => state.dataVersion);
  const [resources, setResources] = useState<Resource[]>([]);
  const [total, setTotal] = useState(0);
  const [completedCount, setCompletedCount] = useState(0);
  const [incompleteCount, setIncompleteCount] = useState(0);
  const [completionRate, setCompletionRate] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<ResourceFilter>(initialFilter || {});
  const lastReadKeyRef = useRef<string | undefined>(undefined);
  const lastInitialFilterRef = useRef<string | undefined>(undefined);
  const fetchingRef = useRef(false);
  const pendingFilterRef = useRef<ResourceFilter | undefined>(undefined);

  const doFetch = useCallback(async (f: ResourceFilter) => {
    if (!sessionId) return;
    if (fetchingRef.current) {
      pendingFilterRef.current = f;
      return;
    }
    fetchingRef.current = true;
    pendingFilterRef.current = undefined;
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, any> = { ...f, sessionId };
      if (subjectId) params.subjectId = subjectId;
      const res = await resourcesApi.getResources(params as any);
      if (pendingFilterRef.current === undefined) {
        setResources(res?.resources || []);
        setTotal(res?.total || 0);
        setCompletedCount(res?.completedCount ?? 0);
        setIncompleteCount(res?.incompleteCount ?? 0);
        setCompletionRate(res?.completionRate ?? 0);
      }
    } catch (e) {
      if (pendingFilterRef.current === undefined) {
        setResources([]);
        setTotal(0);
        setCompletedCount(0);
        setIncompleteCount(0);
        setCompletionRate(0);
        setError(e instanceof Error ? e.message : '资源加载失败');
      }
    } finally {
      setLoading(false);
      fetchingRef.current = false;
      if (pendingFilterRef.current) {
        doFetch(pendingFilterRef.current);
      }
    }
  }, [sessionId, subjectId]);

  // ── 统一触发获取：mount / session / subject / dataVersion / initialFilter 任一变化 → 拉数据
  // 用 session 级 version 做 readKey，确保：
  //   1. 首次挂载时必拉（lastReadKeyRef 初始为 undefined）
  //   2. 切换 sessionId 时必拉（readKey 含 sessionId）
  //   3. dataVersion 变化时必拉（dataVersion 含在 readKey 中）
  //   4. subjectId 作为可选过滤（含在 readKey 中）
  const readKey = sessionId
    ? `${sessionId}:${dataVersion}:${subjectId || ''}`
    : undefined;
  useEffect(() => {
    const initialFilterKey = JSON.stringify(initialFilter || {});
    if (
      readKey &&
      (lastReadKeyRef.current !== readKey ||
        lastInitialFilterRef.current !== initialFilterKey)
    ) {
      lastReadKeyRef.current = readKey;
      lastInitialFilterRef.current = initialFilterKey;
      const f = initialFilter || {};
      setFilter(f);
      doFetch(f);
    }
  }, [readKey, doFetch, initialFilter]);

  const applyFilter = useCallback(
    (updates: Partial<ResourceFilter>) => {
      setFilter(prev => {
        const next = { ...prev, ...updates };
        doFetch(next);
        return next;
      });
    },
    [doFetch],
  );

  const toggleBookmark = useCallback(async (id: string) => {
    const params: Record<string, string> = { sessionId };
    if (subjectId) params.subjectId = subjectId;
    const res = await resourcesApi.toggleBookmark(id, params as any);
    setResources((prev) =>
      prev.map((resource) => (resource.id === id ? { ...resource, bookmarked: res.bookmarked } : resource)),
    );
  }, [sessionId, subjectId]);

  const updateResource = useCallback((id: string, updates: Partial<Resource>) => {
    setResources((prev) =>
      prev.map((r) => (r.id === id ? { ...r, ...updates } : r))
    );
  }, []);

  return {
    resources,
    total,
    completedCount,
    incompleteCount,
    completionRate,
    loading,
    error,
    filter,
    applyFilter,
    toggleBookmark,
    updateResource,
    refetch: () => doFetch(filter),
  };
}
