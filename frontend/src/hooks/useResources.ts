import { useCallback, useEffect, useRef, useState } from 'react';
import * as resourcesApi from '../api/resources';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';
import type { Resource, ResourceFilter } from '../types/resource';

export function useResources() {
  const subjectId = useSubjectStore((s) => s.activeSubject?.id);
  const sessionId = useChatStore((state) => state.currentSessionId);
  const dataVersion = useChatStore((state) => state.dataVersion);
  const [resources, setResources] = useState<Resource[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<ResourceFilter>({});
  const lastReadKeyRef = useRef<string | undefined>(undefined);
  const lastVersionRef = useRef<number>(0);
  const fetchingRef = useRef(false);

  const doFetch = useCallback(async (f: ResourceFilter) => {
    if (!subjectId) return;
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    setLoading(true);
    setError(null);
    try {
      const res = await resourcesApi.getResources({ ...f, sessionId, subjectId });
      setResources(res?.resources || []);
      setTotal(res?.total || 0);
    } catch {
      setResources([]);
      setTotal(0);
      setError('资源加载失败，请确认后端已启动');
    } finally {
      setLoading(false);
      fetchingRef.current = false;
    }
  }, [sessionId, subjectId]);

  useEffect(() => {
    const readKey = subjectId ? `${sessionId}:${subjectId}` : undefined;
    if (readKey && lastReadKeyRef.current !== readKey) {
      lastReadKeyRef.current = readKey;
      setFilter({});
      doFetch({});
    }
  }, [sessionId, subjectId, doFetch]);

  useEffect(() => {
    if (dataVersion <= 0 || dataVersion === lastVersionRef.current) return;
    lastVersionRef.current = dataVersion;
    setFilter(prev => {
      doFetch(prev);
      return prev;
    });
  }, [dataVersion, doFetch]);

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
    const res = await resourcesApi.toggleBookmark(id, { sessionId, subjectId });
    setResources((prev) =>
      prev.map((resource) => (resource.id === id ? { ...resource, bookmarked: res.bookmarked } : resource)),
    );
  }, [sessionId, subjectId]);

  return {
    resources,
    total,
    loading,
    error,
    filter,
    applyFilter,
    toggleBookmark,
    refetch: () => doFetch(filter),
  };
}
