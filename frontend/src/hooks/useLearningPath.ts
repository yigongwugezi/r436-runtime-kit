import { useCallback, useEffect, useRef, useState } from 'react';
import * as knowledgeApi from '../api/knowledge';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';
import type { LearningPath, PathNodeStatus } from '../types/learningPath';

/** 根据节点状态计算总体进度 */
function computeOverallProgress(path: LearningPath): number {
  const allNodes = path.stages.flatMap(s => s.nodes);
  if (allNodes.length === 0) return 0;
  const mastered = allNodes.filter(n => n.status === 'mastered').length;
  return Math.round((mastered / allNodes.length) * 100);
}

/** 根据节点状态推断掌握度 */
function statusToMastery(status: PathNodeStatus): number {
  switch (status) {
    case 'locked': return 0;
    case 'available': return 0;
    case 'in_progress': return 40;
    case 'mastered': return 100;
  }
}

export function useLearningPath() {
  const subjectId = useSubjectStore((s) => s.activeSubject?.id);
  const dataVersion = useChatStore((state) => state.dataVersion);
  const [path, setPath] = useState<LearningPath | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lastSubjectRef = useRef<string | undefined>(undefined);
  const lastVersionRef = useRef<number>(0);

  const fetchPath = useCallback(async () => {
    if (!subjectId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await knowledgeApi.getLearningPath(subjectId);
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
  }, [subjectId]);

  const generatePath = useCallback(async (params: { subjectId?: string; targetTopics?: string[] }) => {
    setLoading(true);
    setError(null);
    try {
      const res = await knowledgeApi.generateLearningPath({
        ...params,
        subjectId: params.subjectId || subjectId,
      });
      setPath(res.path);
      return res.path;
    } catch {
      setError('路径生成失败');
      return null;
    } finally {
      setLoading(false);
    }
  }, [subjectId]);

  const updateNode = useCallback(async (nodeId: string, mastery: number) => {
    await knowledgeApi.updateNodeProgress(nodeId, mastery, subjectId);
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
  }, [subjectId]);

  /** 本地切换节点状态并同步掌握度，同时更新总体进度 */
  const updateNodeStatus = useCallback((nodeId: string, status: PathNodeStatus) => {
    setPath((current) => {
      if (!current) return current;
      const mastery = statusToMastery(status);
      const next: LearningPath = {
        ...current,
        stages: current.stages.map((stage) => ({
          ...stage,
          nodes: stage.nodes.map((node) =>
            node.id === nodeId ? { ...node, status, mastery } : node
          ),
        })),
      };
      next.overallProgress = computeOverallProgress(next);
      return next;
    });
  }, []);

  // 科目切换时重新获取学习路径
  useEffect(() => {
    if (subjectId && lastSubjectRef.current !== subjectId) {
      lastSubjectRef.current = subjectId;
      fetchPath();
    }
  }, [subjectId, fetchPath]);

  // 对话完成后自动刷新
  useEffect(() => {
    if (dataVersion <= 0 || dataVersion === lastVersionRef.current) return;
    lastVersionRef.current = dataVersion;
    fetchPath();
  }, [dataVersion, fetchPath]);

  return { path, loading, error, fetchPath, generatePath, updateNode, updateNodeStatus };
}
