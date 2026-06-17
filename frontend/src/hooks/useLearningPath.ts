import { useCallback, useEffect, useRef, useState } from 'react';
import * as knowledgeApi from '../api/knowledge';
import { useChatStore } from '../store/chatStore';
import type { LearningPath } from '../types/learningPath';

export function useLearningPath() {
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const dataVersion = useChatStore((state) => state.dataVersion);
  const [path, setPath] = useState<LearningPath | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lastVersionRef = useRef<number>(0);

  const fetchPath = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await knowledgeApi.getLearningPath(currentSessionId);
      if (res?.path) {
        setPath(res.path);
      } else {
        setPath(null);
        setError('学习路径数据为空');
      }
    } catch {
      setPath(null);
      setError('加载学习路径失败，请确认后端已启动');
    } finally {
      setLoading(false);
    }
  }, [currentSessionId]);

  const generatePath = useCallback(async (params: { sessionId?: string; targetTopics?: string[] }) => {
    setLoading(true);
    setError(null);
    try {
      const res = await knowledgeApi.generateLearningPath({
        ...params,
        sessionId: params.sessionId || currentSessionId,
      });
      setPath(res.path);
      return res.path;
    } catch {
      setError('路径生成失败');
      return null;
    } finally {
      setLoading(false);
    }
  }, [currentSessionId]);

  const updateNode = useCallback(async (nodeId: string, mastery: number) => {
    await knowledgeApi.updateNodeProgress(nodeId, mastery, currentSessionId);
    setPath((current) => {
      if (!current) return current;
      return {
        ...current,
        stages: current.stages.map((stage) => ({
          ...stage,
          nodes: stage.nodes.map((node) => (node.id === nodeId ? { ...node, mastery } : node)),
        })),
      };
    });
  }, [currentSessionId]);

  useEffect(() => {
    fetchPath();
  }, [fetchPath]);

  // Chat generation already runs agents on the backend; this hook only refreshes persisted data.
  useEffect(() => {
    if (dataVersion <= 0 || dataVersion === lastVersionRef.current) return;
    lastVersionRef.current = dataVersion;
    fetchPath();
  }, [dataVersion, fetchPath]);

  return { path, loading, error, fetchPath, generatePath, updateNode };
}
