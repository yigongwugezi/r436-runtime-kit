import { useCallback, useEffect, useState, useRef } from 'react';
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
        setError('学习路径数据为空');
      }
    } catch {
      setError('加载学习路径失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  }, [currentSessionId]);

  const generatePath = useCallback(async (params: { sessionId?: string; targetTopics?: string[] }) => {
    setLoading(true);
    try {
      const res = await knowledgeApi.generateLearningPath({ ...params, sessionId: params.sessionId || currentSessionId });
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
    if (!path) return;
    setPath({
      ...path,
      stages: path.stages.map((s) => ({
        ...s,
        nodes: s.nodes.map((n) => (n.id === nodeId ? { ...n, mastery } : n)),
      })),
    });
  }, [currentSessionId, path]);

  useEffect(() => { fetchPath(); }, [fetchPath]);

  // 对话完成后：直接刷新路径（后端已在对话中完成生成和持久化）
  useEffect(() => {
    if (dataVersion <= 0 || dataVersion === lastVersionRef.current) return;
    lastVersionRef.current = dataVersion;
    // Just refresh — agents already ran and persisted results on the server side
    fetchPath();
  }, [dataVersion, fetchPath]);

  return { path, loading, error, fetchPath, generatePath, updateNode };
}
