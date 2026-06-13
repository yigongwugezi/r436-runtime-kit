import { useCallback, useEffect, useState } from 'react';
import * as knowledgeApi from '../api/knowledge';
import type { LearningPath } from '../types/learningPath';

export function useLearningPath() {
  const [path, setPath] = useState<LearningPath | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchPath = useCallback(async () => {
    setLoading(true);
    try {
      const res = await knowledgeApi.getLearningPath();
      setPath(res.path);
    } finally {
      setLoading(false);
    }
  }, []);

  const generatePath = useCallback(async (params: { sessionId?: string; targetTopics?: string[] }) => {
    setLoading(true);
    try {
      const res = await knowledgeApi.generateLearningPath(params);
      setPath(res.path);
      return res.path;
    } finally {
      setLoading(false);
    }
  }, []);

  const updateNode = useCallback(async (nodeId: string, mastery: number) => {
    await knowledgeApi.updateNodeProgress(nodeId, mastery);
    if (!path) return;
    setPath({
      ...path,
      stages: path.stages.map((s) => ({
        ...s,
        nodes: s.nodes.map((n) => (n.id === nodeId ? { ...n, mastery } : n)),
      })),
    });
  }, [path]);

  useEffect(() => { fetchPath(); }, [fetchPath]);

  return { path, loading, fetchPath, generatePath, updateNode };
}
