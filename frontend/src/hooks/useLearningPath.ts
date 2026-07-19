import { useCallback, useEffect, useRef, useState } from 'react';
import * as learningPathApi from '../api/learningPath';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';
import type { LearningPath, PathNodeStatus, ContentStatus, Chapter, Section, KnowledgePoint } from '../types/learningPath';
import { contentStatusToProgress, legacyStatusToContent } from '../types/learningPath';
import { consumeWorkflowEvents, readWorkflow, startWorkflow, type WorkflowState } from '../api/workflows';
import { normalizeLearningPathForClient } from '../utils/learningPathViewModel';

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
  const subjectId = useSubjectStore((s) => s.activeSubject?.id ?? s.activeClassSubject?.subject);
  const sessionId = useChatStore((state) => state.dataSessionId);
  const dataVersion = useChatStore((state) => state.dataVersion);
  const [path, setPath] = useState<LearningPath | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generationWorkflow, setGenerationWorkflow] = useState<WorkflowState | null>(null);
  const lastVersionRef = useRef<number>(0);
  const pathVersionRef = useRef<number>(0);
  const hasDataRef = useRef(false);
  const initialLoadRef = useRef(true);
  const requestIdRef = useRef(0);

  const fetchPath = useCallback(async (force: boolean = false, overrideSessionId?: string) => {
    const effectiveSessionId = overrideSessionId || sessionId;
    if (!effectiveSessionId) { setLoading(false); return; }
    const requestId = ++requestIdRef.current;
    if (force) { hasDataRef.current = false; pathVersionRef.current = -1; }
    if (force || !hasDataRef.current) { setLoading(true); setError(null); }
    try {
      const res = await learningPathApi.getLearningPath({ sessionId: effectiveSessionId, subjectId });
      const p = normalizeLearningPathForClient(res?.path ?? null);
      const finalPath = p;
      if (requestId !== requestIdRef.current) return;
      // Merge path: only update if pathVersion changed (structural change)
      // or if force (initial load / explicit refresh)
      if (finalPath) {
        const newVersion = finalPath.pathVersion ?? 0;
        if (force || newVersion !== pathVersionRef.current) {
          pathVersionRef.current = newVersion;
          setPath(finalPath);
        }
      } else {
        setPath(finalPath);
      }
      hasDataRef.current = !!finalPath;
      if (!finalPath && !hasDataRef.current) setError('学习路径数据为空');
    } catch (e) {
      if (requestId !== requestIdRef.current) return;
      if (!hasDataRef.current) { setPath(null); setError(e instanceof Error ? e.message : '加载学习路径失败'); }
    } finally {
      if (requestId !== requestIdRef.current) return;
      if (force || !hasDataRef.current) setLoading(false);
      initialLoadRef.current = false;
    }
  }, [sessionId, subjectId]);

  const generatePath = useCallback(async (params: { subjectId?: string; targetTopics?: string[]; planMode?: string; pathMode?: string; totalDays?: number; weekends?: boolean; dynamicAdjust?: boolean; reviewEnabled?: boolean; userMessage?: string }) => {
    setLoading(true); setError(null);
    try {
      const started = await startWorkflow('learning_path_generation', { ...params, sessionId, subjectId: params.subjectId || subjectId });
      setGenerationWorkflow({ taskId: started.task_id, workflowType: started.workflow_type, status: started.status, events: [], preview: '', elapsedMs: 0 });
      await consumeWorkflowEvents(started.task_id, (event) => setGenerationWorkflow((current) => {
        if (!current || event.sequence <= (current.events[current.events.length - 1]?.sequence || 0)) return current;
        const status = event.event === 'workflow_completed' ? 'completed' : event.event === 'workflow_cancelled' ? 'cancelled' : event.event === 'workflow_failed' ? 'failed' : 'running';
        return { ...current, status, events: [...current.events, event], elapsedMs: event.elapsed_ms };
      }));
      const task = await readWorkflow(started.task_id, sessionId);
      const next = normalizeLearningPathForClient(task.result?.data?.path ?? null);
      setPath(next);
      return next;
    } catch (e) { setError(e instanceof Error ? e.message : '路径生成失败'); return null; }
    finally { setLoading(false); }
  }, [sessionId, subjectId]);

  const updateNode = useCallback(async (nodeId: string, mastery: number) => {
    await learningPathApi.updateNodeProgress(nodeId, mastery, { sessionId, subjectId, pathId: path?.id });
    setPath((c) => c ? { ...c, stages: c.stages.map(s => ({ ...s, nodes: s.nodes.map(n => n.id === nodeId ? { ...n, mastery } : n) })) } : c);
  }, [sessionId, subjectId, path?.id]);

  const updateNodeStatus = useCallback(async (nodeId: string, status: PathNodeStatus) => {
    try { await learningPathApi.updateNodeProgress(nodeId, statusToMastery(status), { sessionId, subjectId, pathId: path?.id, status }); } catch {}
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

  /** 级联：向上传播 mastered 状态 */
  const cascadeStatus = useCallback((path: LearningPath): LearningPath => {
    return {
      ...path,
      stages: path.stages.map(stage => {
        const updatedChapters = stage.chapters.map(ch => {
          const allSectionsMastered = ch.sections.length > 0 && ch.sections.every(s => s.status === 'mastered');
          const updatedSections = ch.sections.map(sec => {
            const allKpsMastered = sec.knowledgePoints.length > 0 && sec.knowledgePoints.every(k => k.status === 'mastered');
            return allKpsMastered && sec.status !== 'mastered' ? { ...sec, status: 'mastered' as ContentStatus } : sec;
          });
          return allSectionsMastered && ch.status !== 'mastered'
            ? { ...ch, status: 'mastered' as ContentStatus, sections: updatedSections }
            : { ...ch, sections: updatedSections };
        });
        const allChaptersMastered = updatedChapters.length > 0 && updatedChapters.every(c => c.status === 'mastered');
        return { ...stage, chapters: updatedChapters };
      }),
    };
  }, []);

  const updateKnowledgePoint = useCallback(async (kpId: string, updates: { mastery?: number; status?: ContentStatus }) => {
    if (updates.status) {
      try { await learningPathApi.updateNodeProgress(kpId, updates.mastery ?? contentStatusToProgress(updates.status), { sessionId, subjectId, pathId: path?.id, status: updates.status }); } catch {}
    }
    setPath((current) => {
      if (!current) return current;
      let next = mapPathHierarchy(current, (ch) => ch, (sec) => sec, (kp) => kp.id === kpId ? { ...kp, ...updates } : kp);
      if (updates.status === 'mastered') next = cascadeStatus(next);
      next.overallProgress = computeOverallProgress(next);
      return next;
    });
  }, [sessionId, subjectId, cascadeStatus, path?.id]);

  const updateChapterStatus = useCallback(async (chapterId: string, newStatus: ContentStatus) => {
    try { await learningPathApi.updateNodeProgress(chapterId, contentStatusToProgress(newStatus), { sessionId, subjectId, pathId: path?.id, status: newStatus }); } catch {}
    setPath((current) => {
      if (!current) return current;
      let next = mapPathHierarchy(current, (ch) => ch.id === chapterId ? { ...ch, status: newStatus } : ch, (sec) => sec, (kp) => kp);
      if (newStatus === 'mastered') next = cascadeStatus(next);
      next.overallProgress = computeOverallProgress(next);
      return next;
    });
  }, [sessionId, subjectId, cascadeStatus, path?.id]);

  const updateSectionStatus = useCallback(async (sectionId: string, newStatus: ContentStatus) => {
    try { await learningPathApi.updateNodeProgress(sectionId, contentStatusToProgress(newStatus), { sessionId, subjectId, pathId: path?.id, status: newStatus }); } catch {}
    setPath((current) => {
      if (!current) return current;
      let next = mapPathHierarchy(current, (ch) => ch, (sec) => sec.id === sectionId ? { ...sec, status: newStatus } : sec, (kp) => kp);
      if (newStatus === 'mastered') next = cascadeStatus(next);
      next.overallProgress = computeOverallProgress(next);
      return next;
    });
  }, [sessionId, subjectId, cascadeStatus, path?.id]);

  useEffect(() => {
    requestIdRef.current += 1;
    hasDataRef.current = false;
    pathVersionRef.current = -1;
    setPath(null);
    setError(null);
    fetchPath(true);
  }, [sessionId, subjectId, fetchPath]);
  useEffect(() => { if (dataVersion <= 0 || dataVersion === lastVersionRef.current) return; lastVersionRef.current = dataVersion; fetchPath(true); }, [dataVersion, fetchPath]);

  /** 从 workflow 完成结果直接设置路径，不依赖 API 二次查询 */
  const applyPathFromWorkflow = useCallback((rawPath: any) => {
    const normalized = normalizeLearningPathForClient(rawPath);
    if (normalized && normalized.stages?.length) {
      pathVersionRef.current = normalized.pathVersion ?? Date.now();
      hasDataRef.current = true;
      setPath(normalized);
      setLoading(false);
      setError(null);
    }
  }, []);

  return { path, loading, error, generationWorkflow, fetchPath, generatePath, applyPathFromWorkflow, updateNode, updateNodeStatus, updateKnowledgePoint, updateChapterStatus, updateSectionStatus };
}
