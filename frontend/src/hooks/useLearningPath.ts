import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import * as learningPathApi from '../api/learningPath';
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
  const location = useLocation();
  const subjectId = useSubjectStore((s) => s.activeSubject?.id);
  const sessionId = useChatStore((state) => state.dataSessionId);
  const dataVersion = useChatStore((state) => state.dataVersion);
  const [path, setPath] = useState<LearningPath | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lastReadKeyRef = useRef<string | undefined>(undefined);
  const lastVersionRef = useRef<number>(0);

  const fetchPath = useCallback(async () => {
    if (!subjectId) return;
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await learningPathApi.getLearningPath({ sessionId, subjectId });
      if (res?.path) {
        setPath(res.path);
      } else {
        setPath(null);
        setError('学习路径数据为空');
      }
    } catch (e) {
      setPath(null);
      setError(e instanceof Error ? e.message : '加载学习路径失败');
    } finally {
      setLoading(false);
    }
  }, [sessionId, subjectId]);

  const generatePath = useCallback(async (params: { subjectId?: string; targetTopics?: string[] }) => {
    setLoading(true);
    setError(null);
    try {
      const res = await learningPathApi.generateLearningPath({
        ...params,
        sessionId,
        subjectId: params.subjectId || subjectId,
      });
      setPath(res.path);
      return res.path;
    } catch (e) {
      setError(e instanceof Error ? e.message : '路径生成失败');
      return null;
    } finally {
      setLoading(false);
    }
  }, [sessionId, subjectId]);

  const updateNode = useCallback(async (nodeId: string, mastery: number) => {
    await learningPathApi.updateNodeProgress(nodeId, mastery, { sessionId, subjectId });
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
  }, [sessionId, subjectId]);

  /** 切换节点状态 + 同步掌握度 + 更新总体进度 + 持久化到后端 */
  const updateNodeStatus = useCallback(async (nodeId: string, status: PathNodeStatus) => {
    const mastery = statusToMastery(status);
    // 先持久化到后端
    try {
      await learningPathApi.updateNodeProgress(nodeId, mastery, {
        sessionId,
        subjectId,
        status,
      });
    } catch { /* 后端不可用时静默降级，本地更新仍然生效 */ }
    // 再更新本地状态
    setPath((current) => {
      if (!current) return current;
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
  }, [sessionId, subjectId]);

  // 每次路由进入该页面时重新获取学习路径（确保从资源库返回后看到节点进度更新）
  useEffect(() => {
    const readKey = subjectId ? `${sessionId}:${subjectId}` : undefined;
    if (readKey) {
      fetchPath();
    }
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        fetchPath();
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, subjectId, location.key, fetchPath]);

  // 对话完成后自动刷新
  useEffect(() => {
    if (dataVersion <= 0 || dataVersion === lastVersionRef.current) return;
    lastVersionRef.current = dataVersion;
    fetchPath();
  }, [dataVersion, fetchPath]);

  return { path, loading, error, fetchPath, generatePath, updateNode, updateNodeStatus };
}
