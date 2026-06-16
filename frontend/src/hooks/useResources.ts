import { useCallback, useEffect, useState, useRef } from 'react';
import * as resourcesApi from '../api/resources';
import * as knowledgeApi from '../api/knowledge';
import { useChatStore } from '../store/chatStore';
import { useProfileStore } from '../store/profileStore';
import type { Resource, ResourceFilter } from '../types/resource';

export function useResources() {
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const dataVersion = useChatStore((state) => state.dataVersion);
  const profile = useProfileStore((state) => state.profile);
  const [resources, setResources] = useState<Resource[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<ResourceFilter>({});
  const lastVersionRef = useRef<number>(0);
  const lastRegenRef = useRef<string>('');

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
      prev.map((r) => (r.id === id ? { ...r, bookmarked: res.bookmarked } : r)),
    );
  }, []);

  useEffect(() => {
    fetchResources(filter);
  }, [fetchResources, filter]);

  // 对话完成后：检查课程变更，自动触发资源生成
  useEffect(() => {
    if (dataVersion <= 0 || dataVersion === lastVersionRef.current) return;
    lastVersionRef.current = dataVersion;

    const courseDim = profile?.dimensions?.find(d => d.key === 'knowledge_base');
    const courseKey = courseDim?.description || courseDim?.label || '';
    if (!courseKey || courseKey === lastRegenRef.current) {
      fetchResources(filter);
      return;
    }

    // 课程变了 → 生成新资源
    lastRegenRef.current = courseKey;
    resourcesApi.generateResource({ type: 'lecture', topic: courseKey, sessionId: currentSessionId })
      .catch(() => {})
      .finally(() => fetchResources(filter));
  }, [dataVersion, profile, filter, fetchResources, currentSessionId]);

  return { resources, total, loading, error, filter, applyFilter, toggleBookmark, refetch: () => fetchResources(filter) };
}
