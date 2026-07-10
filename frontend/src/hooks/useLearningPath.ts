import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import * as learningPathApi from '../api/learningPath';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';
import type { LearningPath, PathNodeStatus, ContentStatus, Chapter, Section, KnowledgePoint } from '../types/learningPath';
import { contentStatusToProgress, legacyStatusToContent } from '../types/learningPath';

function computeOverallProgress(path: LearningPath): number {
  // 优先从章节层级计算
  const allKps = path.stages.flatMap(s =>
    s.chapters?.flatMap(ch =>
      ch.sections?.flatMap(sec => sec.knowledgePoints ?? []) ?? []
    ) ?? []
  );
  if (allKps.length > 0) {
    return Math.round((allKps.filter(k => k.status === 'mastered').length / allKps.length) * 100);
  }
  // 旧格式兜底
  const allNodes = path.stages.flatMap(s => s.nodes);
  if (allNodes.length === 0) return 0;
  return Math.round((allNodes.filter(n => n.status === 'mastered' || (n.status as string) === 'completed').length / allNodes.length) * 100);
}

function statusToMastery(status: PathNodeStatus | ContentStatus): number {
  switch (status) {
    case 'locked': case 'available': case 'not_started': return 0;
    case 'blocked': return 5;
    case 'in_progress': return 40;
    case 'needs_review': return 70;
    case 'mastered': return 100;
  }
}

/** Map over every node in the chapter hierarchy, applying transforms at each level.
 *  Each transform receives the existing node and returns the updated node (or the same node). */
function mapPathHierarchy(
  path: LearningPath,
  mapChapter: (ch: Chapter) => Chapter,
  mapSection: (sec: Section) => Section,
  mapKnowledgePoint: (kp: KnowledgePoint) => KnowledgePoint,
): LearningPath {
  return {
    ...path,
    stages: path.stages.map(stage => ({
      ...stage,
      chapters: stage.chapters.map(ch => ({
        ...mapChapter(ch),
        sections: ch.sections.map(sec => ({
          ...mapSection(sec),
          knowledgePoints: sec.knowledgePoints.map(mapKnowledgePoint),
        })),
      })),
    })),
  };
}

export function useLearningPath() {
  const location = useLocation();
  const subjectId = useSubjectStore((s) => s.activeSubject?.id ?? s.activeClassSubject?.subject);
  const sessionId = useChatStore((state) => state.dataSessionId);
  const dataVersion = useChatStore((state) => state.dataVersion);
  const [path, setPath] = useState<LearningPath | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lastVersionRef = useRef<number>(0);

  const fetchPath = useCallback(async () => {
    if (!subjectId || !sessionId) { setLoading(false); return; }
    setLoading(true); setError(null); setPath(null);
    try {
      const res = await learningPathApi.getLearningPath({ sessionId, subjectId });
      setPath(res?.path ?? null);
      if (!res?.path) setError('学习路径数据为空');
    } catch (e) {
      setPath(null);
      setError(e instanceof Error ? e.message : '加载学习路径失败');
    } finally { setLoading(false); }
  }, [sessionId, subjectId]);

  const generatePath = useCallback(async (params: { subjectId?: string; targetTopics?: string[] }) => {
    setLoading(true); setError(null);
    try {
      const res = await learningPathApi.generateLearningPath({ ...params, sessionId, subjectId: params.subjectId || subjectId });
      setPath(res.path);
      return res.path;
    } catch (e) { setError(e instanceof Error ? e.message : '路径生成失败'); return null; }
    finally { setLoading(false); }
  }, [sessionId, subjectId]);

  const updateNode = useCallback(async (nodeId: string, mastery: number) => {
    await learningPathApi.updateNodeProgress(nodeId, mastery, { sessionId, subjectId });
    setPath((c) => c ? { ...c, stages: c.stages.map(s => ({ ...s, nodes: s.nodes.map(n => n.id === nodeId ? { ...n, mastery } : n) })) } : c);
  }, [sessionId, subjectId]);

  const updateNodeStatus = useCallback(async (nodeId: string, status: PathNodeStatus) => {
    try { await learningPathApi.updateNodeProgress(nodeId, statusToMastery(status), { sessionId, subjectId, status }); } catch {}
    setPath((c) => {
      if (!c) return c;
      const next: LearningPath = { ...c, stages: c.stages.map(stage => ({
        ...stage,
        nodes: stage.nodes.map(n => n.id === nodeId ? { ...n, status, mastery: statusToMastery(status) } : n),
        chapters: stage.chapters.map(ch => ({
          ...ch,
          sections: ch.sections.map(sec => ({
            ...sec,
            knowledgePoints: sec.knowledgePoints.map(kp => kp.id === nodeId ? { ...kp, status: legacyStatusToContent(status), mastery: statusToMastery(status) } : kp),
          })),
        })),
      })) };
      next.overallProgress = computeOverallProgress(next);
      return next;
    });
  }, [sessionId, subjectId]);

  const updateKnowledgePoint = useCallback(async (kpId: string, updates: { mastery?: number; status?: ContentStatus }) => {
    if (updates.status) {
      try { await learningPathApi.updateNodeProgress(kpId, updates.mastery ?? contentStatusToProgress(updates.status), { sessionId, subjectId, status: updates.status }); } catch {}
    }
    setPath((current) => {
      if (!current) return current;
      const next = mapPathHierarchy(
        current,
        (ch) => ch,
        (sec) => sec,
        (kp) => kp.id === kpId ? { ...kp, ...updates } : kp,
      );
      next.overallProgress = computeOverallProgress(next);
      return next;
    });
  }, [sessionId, subjectId]);

  const updateChapterStatus = useCallback(async (chapterId: string, newStatus: ContentStatus) => {
    try { await learningPathApi.updateNodeProgress(chapterId, contentStatusToProgress(newStatus), { sessionId, subjectId, status: newStatus }); } catch {}
    setPath((current) => {
      if (!current) return current;
      const next = mapPathHierarchy(
        current,
        (ch) => ch.id === chapterId ? { ...ch, status: newStatus } : ch,
        (sec) => sec,
        (kp) => kp,
      );
      next.overallProgress = computeOverallProgress(next);
      return next;
    });
  }, [sessionId, subjectId]);

  const updateSectionStatus = useCallback(async (sectionId: string, newStatus: ContentStatus) => {
    try { await learningPathApi.updateNodeProgress(sectionId, contentStatusToProgress(newStatus), { sessionId, subjectId, status: newStatus }); } catch {}
    setPath((current) => {
      if (!current) return current;
      const next = mapPathHierarchy(
        current,
        (ch) => ch,
        (sec) => sec.id === sectionId ? { ...sec, status: newStatus } : sec,
        (kp) => kp,
      );
      next.overallProgress = computeOverallProgress(next);
      return next;
    });
  }, [sessionId, subjectId]);

  useEffect(() => { fetchPath(); const onVisible = () => { if (document.visibilityState === 'visible') fetchPath(); }; document.addEventListener('visibilitychange', onVisible); return () => document.removeEventListener('visibilitychange', onVisible); }, [sessionId, subjectId, location.key, fetchPath]);
  useEffect(() => { if (dataVersion <= 0 || dataVersion === lastVersionRef.current) return; lastVersionRef.current = dataVersion; fetchPath(); }, [dataVersion, fetchPath]);

  return { path, loading, error, fetchPath, generatePath, updateNode, updateNodeStatus, updateKnowledgePoint, updateChapterStatus, updateSectionStatus };
}
