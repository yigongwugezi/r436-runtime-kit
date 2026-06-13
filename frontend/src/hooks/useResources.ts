import { useCallback, useEffect, useState } from 'react';
import * as resourcesApi from '../api/resources';
import type { Resource, ResourceFilter } from '../types/resource';

export function useResources() {
  const [resources, setResources] = useState<Resource[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<ResourceFilter>({});

  const fetchResources = useCallback(async (f?: ResourceFilter) => {
    setLoading(true);
    try {
      const res = await resourcesApi.getResources(f);
      setResources(res?.resources || []);
      setTotal(res?.total || 0);
    } catch {
      setResources([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

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
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return { resources, total, loading, filter, applyFilter, toggleBookmark, refetch: () => fetchResources(filter) };
}
