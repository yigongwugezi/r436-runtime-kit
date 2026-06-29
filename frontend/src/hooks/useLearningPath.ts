import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import * as learningPathApi from '../api/learningPath';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';
import type { LearningPath, PathNodeStatus } from '../types/learningPath';

function computeOverallProgress(path: LearningPath): number {
  const allNodes = path.stages.flatMap(s => s.nodes);
  if (allNodes.length === 0) return 0;
  const mastered = allNodes.filter(n => n.status === 'mastered').length;
  return Math.round((mastered / allNodes.length) * 100);
}

function statusToMastery(status: PathNodeStatus): number {
  switch (status) { case 'locked': return 0; case 'available': return 0; case 'in_progress': return 40; case 'mastered': return 100; }
}

export function useLearningPath() {
  const location = useLocation();
  const subjectId = useSubjectStore((s) => s.activeSubject?.id);
  const sessionId = useChatStore((state) => state.dataSessionId);
  const dataVersion = useChatStore((state) => state.dataVersion);
  const [path, setPath] = useState<LearningPath | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lastVersionRef = useRef<number>(0);

  const fetchPath = useCallback(async () => {
    if (!subjectId) return;
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    setPath(null);  // 切换科目时立即清空旧路径
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
    setLoading(true); setError(null);
    try {
      const res = await learningPathApi.generateLearningPath({ ...params, sessionId, subjectId: params.subjectId || subjectId });
      setPath(res.path);
      return res.path;
    } catch (e) {
      setError(e instanceof Error ? e.message : '路径生成失败');
      return null;
    } finally { setLoading(false); }
  }, [sessionId, subjectId]);

  const updateNode = useCallback(async (nodeId: string, mastery: number) => {
    await learningPathApi.updateNodeProgress(nodeId, mastery, { sessionId, subjectId });
    setPath((current) => {
      if (!current) return current;
      return { ...current, stages: current.stages.map((stage) => ({ ...stage, nodes: stage.nodes.map((node) => (node.id === nodeId ? { ...node, mastery } : node)) })) };
    });
  }, [sessionId, subjectId]);

  const updateNodeStatus = useCallback(async (nodeId: string, status: PathNodeStatus) => {
    const mastery = statusToMastery(status);
    try { await learningPathApi.updateNodeProgress(nodeId, mastery, { sessionId, subjectId, status }); } catch {}
    setPath((current) => {
      if (!current) return current;
      const next: LearningPath = { ...current, stages: current.stages.map((stage) => ({ ...stage, nodes: stage.nodes.map((node) => (node.id === nodeId ? { ...node, status, mastery } : node)) })) };
      next.overallProgress = computeOverallProgress(next);
      return next;
    });
  }, [sessionId, subjectId]);

  useEffect(() => { fetchPath(); const onVisible = () => { if (document.visibilityState === 'visible') fetchPath(); }; document.addEventListener('visibilitychange', onVisible); return () => document.removeEventListener('visibilitychange', onVisible); }, [sessionId, subjectId, location.key, fetchPath]);

  useEffect(() => { if (dataVersion <= 0 || dataVersion === lastVersionRef.current) return; lastVersionRef.current = dataVersion; fetchPath(); }, [dataVersion, fetchPath]);

  return { path, loading, error, fetchPath, generatePath, updateNode, updateNodeStatus };
}
