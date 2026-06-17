import { useCallback, useEffect, useRef, useState } from 'react';
import * as resourcesApi from '../api/resources';
import { useChatStore } from '../store/chatStore';
import type { Resource, ResourceFilter } from '../types/resource';

export function useResources() {
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const dataVersion = useChatStore((state) => state.dataVersion);
  const [resources, setResources] = useState<Resource[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<ResourceFilter>({});
  const lastVersionRef = useRef<number>(0);

  const fetchResources = useCallback(async (f?: ResourceFilter) => {
    setLoading(true);
    setError(null);
    try {
      const res = await resourcesApi.getResources({ ...f, sessionId: currentSessionId });
      setResources(res?.resources || []);
      setTotal(res?.total || 0);
    } catch {
      setResources([]);
      setTotal(0);
      setError('资源加载失败，请确认后端已启动');
    } finally {
      setLoading(false);
    }
  }, [currentSessionId]);

  const applyFilter = useCallback(
    (updates: Partial<ResourceFilter>) => {
      const next = { ...filter, ...updates };
      setFilter(next);
      fetchResources(next);
    },
    [filter, fetchResources],
  );

  const toggleBookmark = useCallback(async (id: string) => {
    const res = await resourcesApi.toggleBookmark(id);
    setResources((prev) =>
      prev.map((resource) => (resource.id === id ? { ...resource, bookmarked: res.bookmarked } : resource)),
    );
  }, []);

  useEffect(() => {
    fetchResources(filter);
  }, [fetchResources, filter]);

  // Chat generation updates dataVersion; pages should refresh only, not silently generate data.
  useEffect(() => {
    if (dataVersion <= 0 || dataVersion === lastVersionRef.current) return;
    lastVersionRef.current = dataVersion;
    fetchResources(filter);
  }, [dataVersion, filter, fetchResources]);

  return {
    resources,
    total,
    loading,
    error,
    filter,
    applyFilter,
    toggleBookmark,
    refetch: () => fetchResources(filter),
  };
}
