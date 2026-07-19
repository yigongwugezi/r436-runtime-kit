import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { authHeaders } from '../api/client';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useLearningPath } from '../hooks/useLearningPath';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';
import { useLectureStore } from '../store/lectureStore';
import { ChevronLeft, ChevronRight, Sparkles, MessageCircle, Send, Brain, BookOpen, ArrowLeft, ArrowRight, Target, Lightbulb, Layers, Clock, GraduationCap, Hash, CheckCircle2, Check, X, Loader2, HelpCircle, RefreshCw, FileText, FileDown, Lock } from 'lucide-react';
import Markdown from '../utils/markdown';
import MermaidDiagram from '../utils/mermaid';
import { ensureLearningPathQuiz, generateSectionQuiz, submitLearningPathQuiz, submitQuizAttempt } from '../api/assessment';
import type { Chapter, LearningStage, PathNode, Section, ContentStatus } from '../types/learningPath';
import type { LinkedQuestion, QuizResult, WeakPoint } from '../types/assessment';
import SectionResourceWorkspace from '../components/learning/SectionResourceWorkspace';
import SectionContentRouter, { type ContentType, type SectionContent } from '../components/learning/SectionContentRouter';
import TextbookViewer from '../components/learning/TextbookViewer';
import TextbookTocPanel from '../components/learning/TextbookTocPanel';
import { getTextbookTOC, getTextbookContent } from '../api/textbooks';
import type { TextbookTOC } from '../types/textbook';
import GeneratePanel, { type GeneratePanelHandle } from '../components/learning/GeneratePanel';
import { logStudyEvent } from '../api/feedback';
import DailyTaskPage from './DailyTaskPage';
import FocusSprintPage from './FocusSprintPage';
import WorkflowProgress from '../components/common/WorkflowProgress';
import { cancelWorkflow, consumeWorkflowEvents, ensureLecture, readWorkflow, type WorkflowState } from '../api/workflows';
import { createLectureEnsureGuard } from '../utils/lectureEnsureGuard';
import { completeLearningPathTask, recordVideoTaskEvidence } from '../api/learningPath';
import { resolveTaskExecutionMode } from '../utils/taskExecutionMode';
import { requestVideoRecommendations, retryVideoRecommendations, videoRecommendationScope } from '../api/videoRecommendations';
import {
  clearWorkflowTask,
  isActiveWorkflowStatus,
  isTerminalWorkflowStatus,
  readWorkflowTask,
  saveWorkflowTask,
  workflowStateFromEvent,
  type WorkflowTaskScope,
} from '../utils/workflowTaskRecovery';

const CONTENT_TYPE_OPTIONS: { value: ContentType; label: string; icon: string }[] = [
  { value: 'lecture', label: '教材', icon: '📖' },
  { value: 'memory_drill', label: '闪卡', icon: '🃏' },
  { value: 'step_through', label: '分步', icon: '🪜' },
];

function detectContentType(md: string): ContentType {
  const first200 = md.slice(0, 200).toLowerCase();
  // Memory drill: vocabulary tables, word lists, flashcard patterns
  if (/单词|词汇|vocabulary|背记|记忆卡|闪卡/.test(first200)) return 'memory_drill';
  if (/\*\*[^*]+\*\*\s*[—\-–]/.test(md.slice(0, 500)) && md.split('\n').filter(l => /\*\*[^*]+\*\*\s*[—\-–]/.test(l)).length >= 3) return 'memory_drill';
  // Step through: step-by-step tutorials, derivations
  if (/第[一二三四五六七八九十\d]+步|step\s*\d|步骤\s*\d/i.test(first200)) return 'step_through';
  if (md.match(/^#{2,3}\s*(?:Step\s*\d|第[一二三四五六七八九十\d]+步)/gm)?.length ?? 0 >= 2) return 'step_through';
  return 'lecture';
}

function lectureContent(response: any): string {
  const value = response?.data?.lecture?.content ?? response?.lecture?.content ?? response?.data?.content ?? response?.content ?? response?.generated_content;
  return typeof value === 'string' ? value.trim() : '';
}

const sectionStatusStyle: Record<ContentStatus, { dot: string; bar: string }> = {
  not_started:  { dot: 'bg-surface-300 ring-surface-100', bar: 'bg-surface-300' },
  in_progress:  { dot: 'bg-blue-400 ring-blue-100',      bar: 'bg-blue-400' },
  mastered:     { dot: 'bg-emerald-400 ring-emerald-100', bar: 'bg-emerald-400' },
  needs_review: { dot: 'bg-amber-400 ring-amber-100',     bar: 'bg-amber-400' },
  blocked:      { dot: 'bg-red-400 ring-red-100',         bar: 'bg-red-400' },
};

function legacyNodeSection(node: PathNode): Section {
  const status: ContentStatus = node.status === 'locked'
    ? 'blocked'
    : node.status === 'available'
      ? 'not_started'
      : node.status;
  return {
    id: node.id,
    title: node.topic,
    goal: node.description || `学习${node.topic}的核心内容。`,
    estimatedMinutes: 45,
    status,
    knowledgePoints: [{
      id: node.id,
      name: node.topic,
      type: 'concept',
      mastery: node.mastery || 0,
      status,
    }],
    lectureIds: [],
  };
}

function legacyStageSection(stage: { id: string; title: string }, sectionId: string): Section {
  return {
    id: sectionId,
    title: `学习《${stage.title}》核心内容`,
    goal: `掌握${stage.title}的核心内容。`,
    estimatedMinutes: 45,
    status: 'not_started',
    knowledgePoints: [{
      id: stage.id,
      name: stage.title,
      type: 'concept',
      mastery: 0,
      status: 'not_started',
    }],
    lectureIds: [],
  };
}

function taskDayScope(path: any, taskId: string): { dayId?: string; globalDayIndex?: number; status?: string; task?: any } {
  for (const stage of path?.stages ?? []) {
    for (const day of stage?.days ?? []) {
      if ((day?.tasks ?? []).some((task: any) => (task.id || task.task_id) === taskId)) {
        const task = (day?.tasks ?? []).find((item: any) => (item.id || item.task_id) === taskId);
        return { dayId: day.id || day.dayId, globalDayIndex: day.globalDayIndex, status: task?.status, task };
      }
    }
  }
  return {};
}

export default function LecturePage() {
  const { chapterId, sectionId } = useParams<{ chapterId?: string; sectionId?: string }>();
  const nav = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { path, updateKnowledgePoint, fetchPath } = useLearningPath();
  const storedSessionId = useChatStore((s) => s.dataSessionId);
  const routeSessionId = searchParams.get('sessionId') || '';
  const sessionId = storedSessionId;
  const focusedTaskId = searchParams.get('taskId') || sectionId || '';
  const focusedStageId = searchParams.get('stageId') || '';
  const focusedPathId = searchParams.get('pathId') || '';
  const focusedSubjectId = searchParams.get('subjectId') || '';
  const focusedTaskType = searchParams.get('taskType') || 'read_doc';
  // Task URLs keep their scope for refresh/recovery.  The focused layout is
  // legacy-only; normal learning-path navigation always uses the full workspace.
  const focusedTask = searchParams.get('legacy') === '1' && Boolean(sessionId && focusedPathId && focusedStageId && focusedTaskId);
  const focusedReadingTask = ['reading', 'document', 'lecture', 'read_doc'].includes(focusedTaskType);
  const returnPathMode = ['textbook', 'daily', 'project', 'focus'].includes(searchParams.get('pathMode') || '')
    ? searchParams.get('pathMode')
    : '';
  const returnViewStage = searchParams.get('viewStage');
  const analyticsReturn = searchParams.get('returnTo') === '/analytics';

  useEffect(() => {
    if (!sessionId || !routeSessionId || routeSessionId === sessionId) return;
    const corrected = new URLSearchParams(searchParams);
    corrected.set('sessionId', sessionId);
    setSearchParams(corrected, { replace: true });
  }, [routeSessionId, searchParams, sessionId, setSearchParams]);

  const returnToPath = focusedTask
    ? analyticsReturn ? '/analytics' : `/path?sessionId=${encodeURIComponent(sessionId)}&subjectId=${encodeURIComponent(focusedSubjectId)}&pathId=${encodeURIComponent(focusedPathId)}&stage=${encodeURIComponent(focusedStageId)}&task=${encodeURIComponent(focusedTaskId)}`
    : returnPathMode
    ? `/path?mode=${encodeURIComponent(returnPathMode)}${returnViewStage ? `&viewStage=${encodeURIComponent(returnViewStage)}` : ''}`
    : '/path';

  // ── 路径模式检测 ──
  const pathMode = useMemo(() => {
    if (!path?.stages) return 'textbook';
    for (const s of path.stages) {
      if ((s as any).path_mode === 'daily') return 'daily';
      if ((s as any).plan_mode === 'focus') return 'focus';
    }
    // Fallback: check first section for task_type (daily indicator)
    const firstSection = path.stages[0]?.chapters?.[0]?.sections?.[0];
    if ((firstSection as any)?.task_type) return 'daily';
    return 'textbook';
  }, [path]);

  // ── 从 store 读取持久化状态 ──
  const store = useLectureStore();
  // ── Section download handler ──
  const handleSectionDownload = async (fmt: string) => {
    const sid = activeSectionId;
    if (!sid) return;
    setDownloadLoading(fmt);
    try {
      const resp = await fetch(`/api/sections/${sid}/lecture/download?format=${fmt}&sessionId=${sessionId || ''}`, {
        headers: authHeaders(),
      });
      if (!resp.ok) throw new Error(`下载失败 (${resp.status})`);
      const blob = await resp.blob();
      const disposition = resp.headers.get('Content-Disposition') || '';
      const match = disposition.match(/filename\*?=(?:UTF-8'')?([^;\s]+)/i);
      const filename = match ? decodeURIComponent(match[1]) : `文档_${fmt}.${fmt}`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('下载失败:', e);
    } finally {
      setDownloadLoading('');
    }
  };

  const [activeSectionId, setActiveSectionId] = useState(sectionId || '');
  const [focusedAccessDenied, setFocusedAccessDenied] = useState(false);
  const [focusedCompleting, setFocusedCompleting] = useState(false);
  const focusedGenerationRef = useRef('');
  const unavailableEnsureGuard = useRef(createLectureEnsureGuard());
  const lastEnsureScope = useRef('');

  // ── 本地临时状态 ──
  const [lectureLoaded, setLectureLoaded] = useState(false);
  const [lectureMissing, setLectureMissing] = useState(false);
  const [lectureEnsureUnavailable, setLectureEnsureUnavailable] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [lectureWorkflow, setLectureWorkflow] = useState<WorkflowState | null>(null);
  const lectureWorkflowAbort = useRef<AbortController | null>(null);
  const [chatMsg, setChatMsg] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [rightTab, setRightTab] = useState<'tutor' | 'resources' | 'toc' | 'generate'>('tutor');
  const [genAll, setGenAll] = useState(false);
  const [prevLecture, setPrevLecture] = useState('');           // 控制返回按钮显示
  const [downloadLoading, setDownloadLoading] = useState('');
  const originalLectureRef = useRef('');                         // 永远指向原始文档，不会被子卡片覆盖
  const [showRightPanel, setShowRightPanel] = useState(true);
  const [quotedText, setQuotedText] = useState('');                 // 学员划词引用
  const [quotePos, setQuotePos] = useState<{x:number;y:number}|null>(null);
  const [zoomDiagram, setZoomDiagram] = useState<string>('');        // 放大查看图解内容
  const generatePanelRef = useRef<GeneratePanelHandle>(null);

  useEffect(() => {
    if (searchParams.get('panel') === 'resources') setRightTab('resources');
  }, [searchParams]);

  // ── 派生值 ──
  const cacheKey = `${sessionId || 'anon'}:${activeSectionId}`;
  const lecture = store.lectureCache[cacheKey] || '';
  const loadedSectionIds = store.loadedSectionIds;
  const generatedSectionIds = store.generatedSectionIds;
  const contentType = store.contentType;
  const chatReply = store.chatReplyCache[`${sessionId || 'anon'}:${activeSectionId}`] || '';
  const cachedQuiz = activeSectionId ? store.quizCache[cacheKey] : undefined;

  // ── 当前章节与小节 ──
  const chapterCtx = useMemo(() => {
    for (const stage of (path?.stages ?? [])) {
      for (const ch of (stage.chapters ?? [])) {
        if (ch.id === chapterId || ch.sections.some(section => section.id === sectionId)) return { chapter: ch, stage };
      }
      const legacyNode = sectionId ? stage.nodes?.find(node => node.id === sectionId) : undefined;
      if (legacyNode) {
        return { chapter: { id: stage.id, title: stage.title, order: stage.order, status: 'not_started' as ContentStatus, sections: [legacyNodeSection(legacyNode)] }, stage };
      }
      if (sectionId && sectionId.startsWith(`${stage.id}_`)) {
        return { chapter: { id: stage.id, title: stage.title, order: stage.order, status: 'not_started' as ContentStatus, sections: [legacyStageSection(stage, sectionId)] }, stage };
      }
    }
    const routeStageId = sectionId?.match(/^(.*)_node_\d+$/)?.[1];
    if (sectionId && routeStageId) {
      const stageTitle = lecture.match(/^#\s*学习《(.+?)》核心内容/m)?.[1] || '当前章节';
      const routeStage = { id: routeStageId, title: stageTitle };
      return { chapter: { id: routeStageId, title: stageTitle, order: 0, status: 'not_started' as ContentStatus, sections: [legacyStageSection(routeStage, sectionId)] }, stage: { id: routeStageId, title: stageTitle, order: 0, description: '', nodes: [], chapters: [], objective: '', estimatedDays: 0 } as LearningStage };
    }
    return null;
  }, [path, chapterId, sectionId, lecture]);

  const sections = chapterCtx?.chapter.sections ?? [];
  // ── Quiz state（优先从缓存恢复）──
  const [quizQuestions, setQuizQuestions] = useState<LinkedQuestion[]>(cachedQuiz?.questions || []);
  const [quizId, setQuizId] = useState(cachedQuiz?.quizId || '');
  const quizSubmitIdempotencyKeyRef = useRef('');
  const [quizAnswers, setQuizAnswers] = useState<Record<string, string>>(cachedQuiz?.answers || {});
  const [quizResults, setQuizResults] = useState<QuizResult[]>(cachedQuiz?.results || []);
  const [quizTotalScore, setQuizTotalScore] = useState<number | null>(cachedQuiz?.totalScore ?? null);

  // ── Textbook mode state ──
  const activeSubject = useSubjectStore((s) => s.activeSubject);
  const workflowSubjectId = useSubjectStore((s) => s.activeSubject?.id ?? s.activeClassSubject?.subject ?? '');
  const isTextbookMode = !!activeSubject?.textbookId;
  const [textbookToc, setTextbookToc] = useState<TextbookTOC | null>(null);

  // Load textbook TOC when in textbook mode
  useEffect(() => {
    if (!isTextbookMode || !activeSubject?.id) {
      setTextbookToc(null);
      return;
    }
    getTextbookTOC(activeSubject.id)
      .then((toc) => setTextbookToc(toc))
      .catch(() => setTextbookToc(null));
  }, [isTextbookMode, activeSubject?.id]);

  // ── Textbook content for resource generation ──
  const [textbookLectureContent, setTextbookLectureContent] = useState('');

  const [quizState, setQuizState] = useState<'idle' | 'generating' | 'answering' | 'submitted'>('idle');
  const [quizSuggestion, setQuizSuggestion] = useState('');
  const [quizPathCompletion, setQuizPathCompletion] = useState<{ task?: boolean; unlocked?: boolean }>({});
  const [quizWeakPoints, setQuizWeakPoints] = useState<WeakPoint[]>([]);

  // Reset quiz & viewing state when section changes
  useEffect(() => {
    setPrevLecture('');
    setQuizState('idle');
    const qc = store.quizCache[cacheKey];
    if (qc) {
      setQuizQuestions(qc.questions); setQuizId(qc.quizId); setQuizAnswers(qc.answers);
      setQuizResults(qc.results); setQuizTotalScore(qc.totalScore);
      setQuizSuggestion(qc.suggestion || ''); setQuizWeakPoints(qc.weakPoints || []);
    } else {
      setQuizQuestions([]); setQuizId(''); setQuizAnswers({});
      setQuizResults([]); setQuizTotalScore(null);
      setQuizSuggestion(''); setQuizWeakPoints([]);
    }
    // 如果缓存的文档是卡片内容（阅读/导图/实操/视频），清掉强制重拉原始文档
    const cached = store.lectureCache[cacheKey];
    if (cached && (cached.includes('点击上方「返回文档」回到正文') || cached.trimStart().startsWith('```mermaid'))) {
      store.clearLecture(cacheKey);
    }
    const planned = currentSection?.contentType as ContentType | undefined;
    store.setContentType(planned || (lecture ? detectContentType(lecture) : 'lecture'));
  }, [activeSectionId]);

  useEffect(() => {
    setActiveSectionId(sectionId || sections[0]?.id || '');
  }, [sectionId, sections]);

  const currentSection = sections.find((s: Section) => s.id === activeSectionId);
  const currentIdx = sections.findIndex((s: Section) => s.id === activeSectionId);
  const prevSection = currentIdx > 0 ? sections[currentIdx - 1] : null;
  const nextSection = currentIdx < sections.length - 1 ? sections[currentIdx + 1] : null;
  const resourceTaskId = focusedTaskId || activeSectionId;
  const resourceDayScope = useMemo(() => taskDayScope(path, resourceTaskId), [path, resourceTaskId]);
  const completed = ['completed', 'mastered'].includes(resourceDayScope.status || '');
  const executionMode = resolveTaskExecutionMode(resourceDayScope.task || { type: focusedTaskType });
  useEffect(() => {
    if (executionMode !== 'quiz' || !sessionId || !focusedPathId || !focusedStageId || !focusedTaskId || !resourceDayScope.globalDayIndex) return;
    setQuizState('generating');
    ensureLearningPathQuiz(focusedTaskId, { sessionId, subjectId: focusedSubjectId || workflowSubjectId, pathId: focusedPathId, stageId: focusedStageId, taskId: focusedTaskId, dayId: resourceDayScope.dayId, globalDayIndex: resourceDayScope.globalDayIndex })
      .then((response: any) => {
        const quiz = response?.data?.quiz;
        if (!quiz) throw new Error('quiz unavailable');
        setQuizId(quiz.quizId); setQuizQuestions(quiz.questions); setQuizAnswers({}); setQuizResults([]); setQuizTotalScore(null); setQuizState('answering');
      })
      .catch(() => setQuizState('idle'));
  }, [executionMode, sessionId, focusedPathId, focusedStageId, focusedTaskId, focusedSubjectId, workflowSubjectId, resourceDayScope.dayId, resourceDayScope.globalDayIndex]);
  const [videoResources, setVideoResources] = useState<any[]>([]);
  const [videoStatus, setVideoStatus] = useState<'idle' | 'loading' | 'failed' | 'empty' | 'search_unavailable' | 'no_high_relevance' | 'expanded_no_results' | 'invalid_urls' | 'empty_response' | 'persisted' | 'new_search' | 'stale'>('idle');
  const [videoLectureFallback, setVideoLectureFallback] = useState(false);
  const [videoOpened, setVideoOpened] = useState(false);
  const [videoFallbackSelected, setVideoFallbackSelected] = useState(false);
  const [videoRetry, setVideoRetry] = useState(0);
  const videoRefreshRequested = useRef(false);
  const [focusedCompletionError, setFocusedCompletionError] = useState('');
  useEffect(() => { setVideoLectureFallback(false); setVideoOpened(false); setVideoFallbackSelected(false); }, [resourceTaskId]);
  const videoScope = useMemo(() => ({ sessionId, subjectId: focusedSubjectId || workflowSubjectId, pathId: focusedPathId || path?.id, stageId: focusedStageId || chapterCtx?.stage.id, taskId: resourceTaskId, dayId: resourceDayScope.dayId, globalDayIndex: resourceDayScope.globalDayIndex }), [sessionId, focusedSubjectId, workflowSubjectId, focusedPathId, path?.id, focusedStageId, chapterCtx?.stage.id, resourceTaskId, resourceDayScope.dayId, resourceDayScope.globalDayIndex]);
  const videoScopeKey = videoRecommendationScope(videoScope);
  const lectureWorkflowScope: WorkflowTaskScope = {
    workflowType: 'lecture_generation', sessionId, subjectId: workflowSubjectId,
    pathId: path?.id || '', stageId: chapterCtx?.stage.id || '', chapterId: chapterCtx?.chapter.id || '', sectionId: activeSectionId,
  };

  useEffect(() => {
    if (!sessionId || !activeSectionId) return;
    const record = readWorkflowTask(lectureWorkflowScope);
    if (!record) return;
    const controller = new AbortController();
    let active = true;
    const restore = async () => {
      try {
        const task = await readWorkflow(record.taskId, sessionId);
        if (!active) return;
        if (task.workflow_type !== record.workflowType) { clearWorkflowTask(lectureWorkflowScope); return; }
        setLectureWorkflow({ taskId: record.taskId, workflowType: task.workflow_type, status: task.status, events: [], preview: '', elapsedMs: task.elapsed_ms || 0 });
        if (isActiveWorkflowStatus(task.status)) {
          setGenerating(true);
          await consumeWorkflowEvents(record.taskId, (event) => {
            if (active) setLectureWorkflow((current) => current?.taskId === record.taskId ? workflowStateFromEvent(current, event) : current);
          }, controller.signal);
        }
        const latest = await readWorkflow(record.taskId, sessionId);
        if (!active) return;
        if (latest.status === 'completed' && latest.result?.data?.lecture?.content) {
          store.setLecture(`${sessionId}:${activeSectionId}`, latest.result.data.lecture.content);
          store.markGenerated(activeSectionId);
        }
        if (isTerminalWorkflowStatus(latest.status)) clearWorkflowTask(lectureWorkflowScope);
      } catch {
        if (active) { clearWorkflowTask(lectureWorkflowScope); setLectureWorkflow(null); }
      } finally { if (active) setGenerating(false); }
    };
    void restore();
    return () => { active = false; controller.abort(); };
  }, [sessionId, workflowSubjectId, path?.id, chapterCtx?.stage.id, chapterCtx?.chapter.id, activeSectionId]);

  // ── Textbook content for resource generation ──
  useEffect(() => {
    if (!isTextbookMode || !activeSubject?.id || !currentSection?.textbookSectionId) {
      setTextbookLectureContent('');
      return;
    }
    let cancelled = false;
    getTextbookContent(activeSubject.id, {
      sectionId: currentSection.textbookSectionId,
    })
      .then((c) => { if (!cancelled) setTextbookLectureContent(c?.content ?? ''); })
      .catch(() => { if (!cancelled) setTextbookLectureContent(''); });
    return () => { cancelled = true; };
  }, [isTextbookMode, activeSubject?.id, currentSection?.textbookSectionId]);

  // Resolved content: textbook content in textbook mode, generated lecture otherwise
  const effectiveLectureContent = isTextbookMode ? textbookLectureContent : lecture;

  // ── 加载已有文档（优先读缓存）──
  useEffect(() => {
    if ((executionMode === 'video' && !videoLectureFallback) || executionMode === 'quiz') return;
    if (!activeSectionId || !sessionId) return;
    const key = `${sessionId}:${activeSectionId}`;
    const ensureScope = [sessionId, focusedSubjectId || workflowSubjectId, focusedPathId || path?.id, focusedStageId || chapterCtx?.stage.id, focusedTaskId || activeSectionId].join('|');
    if (lastEnsureScope.current !== ensureScope) {
      unavailableEnsureGuard.current.retry(ensureScope);
      lastEnsureScope.current = ensureScope;
    }
    setLectureMissing(false);
    setLectureEnsureUnavailable(false);
    if (store.lectureCache[key]) { setLectureLoaded(true); return; }
    if (unavailableEnsureGuard.current.blocks(ensureScope)) { setLectureMissing(true); setLectureEnsureUnavailable(true); setLectureLoaded(true); return; }
    setLectureLoaded(false);
    ensureLecture(activeSectionId, { sessionId, subjectId: focusedSubjectId || workflowSubjectId, pathId: focusedPathId || path?.id, stageId: focusedStageId || chapterCtx?.stage.id, taskId: focusedTaskId || activeSectionId })
      .then(d => {
        store.markLoaded(activeSectionId);
        if (d?.status === 'running') setLectureMissing(true);
        const content = lectureContent(d);
        if (content) {
          store.setLecture(key, content);
          store.markGenerated(activeSectionId);
        }
      })
      .catch((error) => {
        if (error?.response?.status === 404) {
          unavailableEnsureGuard.current.recordError(ensureScope, 404);
          setLectureMissing(true);
          setLectureEnsureUnavailable(true);
        }
        store.markLoaded(activeSectionId);
      })
      .finally(() => setLectureLoaded(true));
  }, [activeSectionId, sessionId, focusedTask, focusedPathId, focusedStageId, focusedTaskId, executionMode, videoLectureFallback]);

  useEffect(() => {
    if (executionMode !== 'video' || videoLectureFallback || !videoScopeKey) return;
    let active = true;
    setVideoStatus('loading');
    const refresh = videoRefreshRequested.current; videoRefreshRequested.current = false;
    requestVideoRecommendations(videoScope, authHeaders(), refresh)
      .then(({ resources, status, presentationStatus }) => { if (active) { setVideoResources(resources); setVideoStatus(resources.length ? (presentationStatus === 'persisted' || presentationStatus === 'new_search' || presentationStatus === 'stale' ? presentationStatus : 'idle') : ['search_unavailable', 'no_high_relevance', 'expanded_no_results', 'invalid_urls', 'empty_response'].includes(status) ? status as typeof videoStatus : 'empty'); } })
      .catch(() => { if (active) setVideoStatus('failed'); });
    return () => { active = false; };
  }, [executionMode, videoLectureFallback, videoScopeKey, videoRetry]);
  const retryVideoSearch = () => { videoRefreshRequested.current = true; retryVideoRecommendations(videoScope); setVideoRetry((value) => value + 1); };

  const totalKps = chapterCtx?.chapter.sections?.reduce((s, sec) => s + (sec.knowledgePoints?.length ?? 0), 0) ?? 0;
  const masteredKps = chapterCtx?.chapter.sections?.reduce((s, sec) => s + (sec.knowledgePoints?.filter(k => k.status === 'mastered').length ?? 0), 0) ?? 0;
  const totalMin = chapterCtx?.chapter.sections?.reduce((s, sec) => s + (sec.estimatedMinutes ?? 45), 0) ?? 0;

  const handleGenerate = useCallback(async (cardId?: string, requirements?: string) => {
    if (executionMode === 'video' && !videoLectureFallback) return;
    if (!currentSection || !sessionId) return;
    if (generating || (lectureWorkflow && isActiveWorkflowStatus(lectureWorkflow.status))) return;
    setGenerating(true);
    const title = requirements ? `${currentSection.title || '课程教材'}（${requirements.slice(0, 20)}${requirements.length > 20 ? '…' : ''}）` : (currentSection.title || '课程教材');
    const cid = cardId || generatePanelRef.current?.beginRecord('lecture', title, requirements) || '';
    lectureWorkflowAbort.current?.abort();
    const controller = new AbortController();
    lectureWorkflowAbort.current = controller;
    try {
      const ensured = await ensureLecture(activeSectionId, {
          sessionId,
          sectionId: activeSectionId,
          sectionTitle: currentSection.title,
          sectionGoal: currentSection.goal || '',
          chapterId: chapterCtx?.chapter.id || '',
          stageId: chapterCtx?.stage.id || '',
          pathId: focusedTask ? focusedPathId : path?.id || '',
          taskId: focusedTask ? focusedTaskId : activeSectionId,
          subjectId: focusedSubjectId || workflowSubjectId || undefined,
          courseId: path?.courseName || '',
          knowledgePoints: currentSection.knowledgePoints || [],
          requirements: requirements || '',
      });
      const ensuredContent = lectureContent(ensured);
      if (ensured.status === 'ready' && ensuredContent) {
        store.setLecture(`${sessionId}:${activeSectionId}`, ensuredContent);
        store.markGenerated(activeSectionId);
        return;
      }
      if (ensured.status === 'failed' || !ensured.workflowId) throw new Error(ensured.errorMessage || '教材生成失败，请稍后重试');
      const started = { task_id: ensured.workflowId, workflow_type: 'lecture_generation', status: 'running' as const };
      setLectureWorkflow({ taskId: started.task_id, workflowType: started.workflow_type, status: started.status, events: [], preview: '', elapsedMs: 0 });
      const workflowScope: WorkflowTaskScope = { ...lectureWorkflowScope, workflowType: started.workflow_type };
      saveWorkflowTask({ ...workflowScope, taskId: started.task_id, createdAt: Date.now() });
      await consumeWorkflowEvents(started.task_id, (event) => setLectureWorkflow((current) => {
        return current && current.taskId === started.task_id ? workflowStateFromEvent(current, event) : current;
      }), controller.signal);
      const task = await readWorkflow(started.task_id, sessionId);
      const data = task.result;
      const content = lectureContent(data);
      if (content) {
        const key = `${sessionId}:${activeSectionId}`;
        store.setLecture(key, content);
        store.markGenerated(activeSectionId);
        generatePanelRef.current?.updateRecord(cid, { status: 'ready', content });
        clearWorkflowTask(workflowScope);
      } else {
        generatePanelRef.current?.updateRecord(cid, { status: 'error' });
        if (isTerminalWorkflowStatus(task.status)) clearWorkflowTask(workflowScope);
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      generatePanelRef.current?.updateRecord(cid, { status: 'error' });
    } finally { setGenerating(false); }
  }, [currentSection, activeSectionId, sessionId, chapterCtx, path, focusedTask, focusedPathId, focusedTaskId, focusedSubjectId, executionMode, videoLectureFallback]);

  const cancelLectureGeneration = useCallback(async () => {
    if (!lectureWorkflow || !sessionId) return;
    await cancelWorkflow(lectureWorkflow.taskId, sessionId).catch(() => undefined);
    lectureWorkflowAbort.current?.abort();
    setLectureWorkflow((current) => current ? { ...current, status: 'cancelled' } : current);
    setGenerating(false);
    clearWorkflowTask({ ...lectureWorkflowScope, workflowType: lectureWorkflow.workflowType });
  }, [lectureWorkflow, sessionId]);

  const [videoGenerating, setVideoGenerating] = useState(false);
  const [videoResult, setVideoResult] = useState<any>(null);

  const handleTextSelection = useCallback(() => {
    const sel = window.getSelection();
    const text = sel?.toString().trim();
    if (text && text.length > 2 && rightTab === 'tutor') {
      setQuotedText(text);
      const range = sel?.getRangeAt(0);
      if (range) {
        const rect = range.getBoundingClientRect();
        setQuotePos({ x: rect.left + rect.width / 2, y: rect.top - 8 });
      }
    } else {
      setQuotedText('');
      setQuotePos(null);
    }
  }, [rightTab]);

  const sendChat = useCallback(async (question: string, actionType = '') => {
    if (!question.trim() || !sessionId || !currentSection) return;
    setChatMsg(''); setChatLoading(true); setQuotedText(''); setQuotePos(null);
    const ck = `${sessionId}:${activeSectionId}`;
    store.setChatReply(ck, '');

    // In textbook mode, use extracted textbook content as lecture reference
    let lectureExcerpt = lecture.slice(0, 1000);
    if (isTextbookMode && activeSubject?.id && currentSection.textbookSectionId) {
      try {
        const content = await getTextbookContent(activeSubject.id, {
          sectionId: currentSection.textbookSectionId,
        });
        if (content?.content) {
          lectureExcerpt = content.content.slice(0, 1500);
        }
      } catch { /* fall back to empty/generated lecture */ }
    }
    try {
      const res = await fetch(`/api/sections/${encodeURIComponent(activeSectionId)}/tutor/ask`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          sessionId, question,
          quoted: quotedText || '',
          sectionTitle: currentSection.title,
          sectionGoal: currentSection.goal || '',
          knowledgePoints: currentSection.knowledgePoints || [],
          lectureExcerpt,
          actionType,
          pathId: focusedTask ? focusedPathId : path?.id || '',
          stageId: focusedTask ? focusedStageId : chapterCtx?.stage.id || '',
          taskId: focusedTask ? focusedTaskId : activeSectionId,
          subjectId: focusedSubjectId || undefined,
          courseId: path?.courseName || undefined,
        }),
      });
      if (res.status === 403) { setFocusedAccessDenied(true); return; }
      const data = await res.json();
      if (data?.data?.reply) store.setChatReply(ck, data.data.reply);
      else if (data?.status === 'error') store.setChatReply(ck, `出错了：${data.message}`);
    } catch {} finally { setChatLoading(false); }
  }, [sessionId, currentSection, activeSectionId, lecture, isTextbookMode, activeSubject?.id, focusedTask, focusedPathId, focusedStageId, focusedTaskId, focusedSubjectId, path?.id, chapterCtx?.stage.id]);

  const handleGenerateVideo = useCallback(async (cardId?: string, requirements?: string) => {
    if (!sessionId || !currentSection) return;
    setVideoGenerating(true); setVideoResult(null);
    const title = requirements ? `${currentSection.title || '讲解视频'}（${requirements.slice(0, 20)}${requirements.length > 20 ? '…' : ''}）` : (currentSection.title || '讲解视频');
    const cid = cardId || generatePanelRef.current?.beginRecord('video', title, requirements) || '';
    try {
      const res = await fetch(`/api/sections/${encodeURIComponent(activeSectionId)}/tutor/video`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ sessionId, sectionTitle: currentSection.title, lectureContent: effectiveLectureContent, requirements: requirements || '' }),
      });
      const data = await res.json();
      const video = data?.data?.video || {
        status: 'generation_failed',
        userMessage: data?.message || '讲解视频生成失败，请稍后重试。',
      };
      setVideoResult(video);
      if (video.status === 'completed' && video.url) {
        generatePanelRef.current?.updateRecord(cid, { status: 'ready', content: video.url });
      } else {
        generatePanelRef.current?.updateRecord(cid, { status: 'error' });
      }
      setVideoGenerating(false);
    } catch {
      setVideoResult({ status: 'generation_failed', userMessage: '讲解视频生成失败，请稍后重试。' });
      generatePanelRef.current?.updateRecord(cid, { status: 'error' });
      setVideoGenerating(false);
    }
  }, [sessionId, currentSection, activeSectionId]);

  const handleSendChat = useCallback(async () => {
    await sendChat(chatMsg);
  }, [chatMsg, sendChat]);

  const quoteAction = useCallback(async (action: string) => {
    if (!quotedText) return;
    setQuotedText(''); setQuotePos(null);
    setRightTab('tutor');
    const labelMap: Record<string,string> = { explain:'解释', diagram:'图解', quiz:'出题' };
    setChatMsg(`「${quotedText.slice(0, 100)}」${quotedText.length > 100 ? '…' : ''} - ${labelMap[action] || action}`);
    await sendChat(`""${quotedText}""`, action);
  }, [quotedText, sendChat]);

  const loadingLecture = !lectureLoaded;

  // ── Build section content object for the router ──
  const sectionContent: SectionContent | null = useMemo(() => {
    if (!lecture || !currentSection) return null;
    return {
      contentType,
      title: currentSection.title,
      goal: currentSection.goal || '',
      content: lecture,
      knowledgePoints: (currentSection.knowledgePoints || []).map((kp: any) =>
        typeof kp === 'string' ? { name: kp } : { name: kp.name, type: kp.type }
      ),
    };
  }, [lecture, currentSection, contentType]);

  // ── Quiz generation ──
  const handleQuizGenerate = async (cardId?: string, requirements?: string) => {
    if (!currentSection) return;
    setQuizQuestions([]); setQuizState('generating');
    const title = requirements ? `${currentSection.title || '练习题目'}（${requirements.slice(0, 20)}${requirements.length > 20 ? '…' : ''}）` : (currentSection.title || '练习题目');
    const cid = cardId || generatePanelRef.current?.beginRecord('quiz', title, requirements) || '';
    const kpNames = (currentSection.knowledgePoints || []).map((kp: any) => kp.name || kp).filter(Boolean);
    setQuizState('generating');

    // In textbook mode, use extracted textbook content as lecture notes reference
    let lectureSummary = lecture.slice(0, 1500);
    if (isTextbookMode && activeSubject?.id && currentSection.textbookSectionId) {
      try {
        const content = await getTextbookContent(activeSubject.id, {
          sectionId: currentSection.textbookSectionId,
        });
        if (content?.content) {
          lectureSummary = content.content.slice(0, 2000);
        }
      } catch { /* fall back to empty/generated lecture */ }
    }
    try {
      const res = await generateSectionQuiz(activeSectionId, {
        sessionId: sessionId || `lecture_${activeSectionId}`,
        title: currentSection.title || '当前小节',
        knowledgePoints: kpNames.length > 0 ? kpNames.slice(0, 5) : [chapterCtx?.chapter.title || '', currentSection.title || ''].filter(Boolean),
        lectureSummary,
        difficulty: 'medium',
        pathId: path?.id || '',
        stageId: chapterCtx?.stage.id || '',
        chapterId: chapterCtx?.chapter.id || '',
        sectionId: activeSectionId,
        requirements: requirements || '',
      }) as any;
      const data = res?.data || res;
      if (data?.questions && data?.quiz) {
        setQuizQuestions(data.questions);
        setQuizId(data.quiz.id);
        setQuizAnswers({});
        setQuizResults([]);
        setQuizTotalScore(null);
        setQuizState('answering');
        quizSubmitIdempotencyKeyRef.current = '';  // reset for new quiz
        // 保存到 store 以便跨页面恢复
        store.setQuiz(`${sessionId}:${activeSectionId}`, { questions: data.questions, quizId: data.quiz.id, answers: {}, results: [], totalScore: null, submitted: false, suggestion: '', weakPoints: [] });
        generatePanelRef.current?.updateRecord(cid, {
          status: 'ready',
          content: 'quiz_stored',
          quizData: {
            questions: data.questions,
            quizId: data.quiz.id,
            answers: {},
            results: [],
            totalScore: null,
            submitted: false,
          },
        });
      } else {
        generatePanelRef.current?.updateRecord(cid, { status: 'error' });
      }
    } catch (e: any) {
      generatePanelRef.current?.updateRecord(cid, { status: 'error' });
      alert('小测生成失败: ' + (e?.message || '请重试'));
      setQuizState('idle');
    }
  };

  const handleQuizAnswer = (questionId: string, value: string) => {
    setQuizAnswers(a => {
      const updated = { ...a, [questionId]: value };
      store.updateQuizAnswers(`${sessionId}:${activeSectionId}`, updated);
      return updated;
    });
  };

  const allAnswered = quizQuestions.every(q => quizAnswers[q.questionId]?.trim());

  const handleQuizSubmit = async () => {
    if (!allAnswered || quizState !== 'answering') return;
    const answers = quizQuestions.map(q => ({
      questionId: q.questionId,
      answer: quizAnswers[q.questionId] || '',
    }));
    try {
      if (!quizSubmitIdempotencyKeyRef.current) {
        quizSubmitIdempotencyKeyRef.current = crypto.randomUUID();
      }
      const payload = {
        sessionId: sessionId || `lecture_${activeSectionId}`,
        answers,
        idempotencyKey: quizSubmitIdempotencyKeyRef.current,
        pathId: focusedPathId || path?.id || '',
        stageId: focusedStageId || chapterCtx?.stage.id || '',
        taskId: focusedTaskId || activeSectionId,
        subjectId: focusedSubjectId || workflowSubjectId,
        dayId: resourceDayScope.dayId,
        globalDayIndex: resourceDayScope.globalDayIndex,
      };
      const res = (executionMode === 'quiz'
        ? await submitLearningPathQuiz(focusedTaskId, { ...payload, quizId })
        : await submitQuizAttempt(quizId, payload)) as any;
      const data = res?.data || res;
      if (data?.results && data.results.length > 0) {
        setQuizResults(data.results);
        setQuizTotalScore(data.totalScore ?? null);
        setQuizSuggestion(data.sectionStatusSuggestion || '');
        setQuizPathCompletion({ task: data.pathTaskCompleted, unlocked: data.nextStageUnlocked });
        setQuizWeakPoints(data.weakPoints || []);
        setQuizState('submitted');
        // 更新 store 中的答题结果
        store.setQuiz(`${sessionId}:${activeSectionId}`, { questions: quizQuestions, quizId, answers: quizAnswers, results: data.results, totalScore: data.totalScore ?? null, submitted: true, suggestion: data.sectionStatusSuggestion || '', weakPoints: data.weakPoints || [] });
      }
    } catch (e: any) {
      alert('提交失败: ' + (e?.message || '请重试'));
    }
  };

  useEffect(() => {
    if (executionMode === 'video' && !videoLectureFallback) return;
    if (!currentSection || !sessionId || !lectureLoaded || !lectureMissing || lecture || generating || lectureEnsureUnavailable) return;
    const key = `${sessionId}:${focusedSubjectId}:${focusedPathId}:${focusedStageId}:${focusedTaskId}:${activeSectionId}`;
    if (focusedGenerationRef.current === key) return;
    focusedGenerationRef.current = key;
    void handleGenerate();
  }, [currentSection, sessionId, lectureLoaded, lectureMissing, lecture, generating, lectureEnsureUnavailable, focusedSubjectId, focusedPathId, focusedStageId, focusedTaskId, activeSectionId, handleGenerate, executionMode, videoLectureFallback]);

  const recordVideoEvidence = async (resourceUrl = '', fallback = false) => {
    if (!focusedTaskId || ['completed', 'mastered'].includes(resourceDayScope.status || '') || (fallback ? videoFallbackSelected : videoOpened)) return;
    setFocusedCompletionError('');
    await recordVideoTaskEvidence(focusedTaskId, {
      sessionId, subjectId: focusedSubjectId || workflowSubjectId, pathId: focusedPathId || path?.id || '',
      stageId: focusedStageId || chapterCtx?.stage.id || '', dayId: resourceDayScope.dayId,
      globalDayIndex: resourceDayScope.globalDayIndex, ...(resourceUrl ? { resourceUrl } : {}),
    }, fallback);
    if (fallback) setVideoFallbackSelected(true); else setVideoOpened(true);
  };

  const completeFocusedTask = async () => {
    const videoReady = executionMode === 'video' && (videoOpened || (videoLectureFallback && videoFallbackSelected && !!effectiveLectureContent));
    if (!focusedTaskId || focusedCompleting || generating || !resourceDayScope.globalDayIndex || (lectureWorkflow && isActiveWorkflowStatus(lectureWorkflow.status)) || !(focusedReadingTask ? !!effectiveLectureContent : videoReady)) return;
    setFocusedCompletionError(''); setFocusedCompleting(true);
    try {
      await completeLearningPathTask(focusedTaskId, {
        sessionId, subjectId: focusedSubjectId || workflowSubjectId, pathId: focusedPathId || path?.id || '',
        stageId: focusedStageId || chapterCtx?.stage.id || '', dayId: resourceDayScope.dayId,
        globalDayIndex: resourceDayScope.globalDayIndex,
      });
      await fetchPath(true);
    } catch (error: any) {
      setFocusedCompletionError(error?.response?.data?.detail || error?.message || '完成失败，请稍后重试。');
    } finally {
      setFocusedCompleting(false);
    }
  };

  const typeLabel = (t: string) => t === 'choice' ? '选择题' : t === 'truefalse' ? '判断题' : t === 'fill' ? '填空题' : '简答题';

  // ── Mode delegation ──
  if (focusedTask) {
    return (
      <div className="min-h-screen -m-6 bg-surface-50">
        <div className="mx-auto flex min-h-screen max-w-6xl flex-col">
          <header className="flex items-center justify-between gap-3 border-b border-surface-200 bg-white px-5 py-3">
            <button onClick={() => nav(returnToPath)} className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-surface-600 hover:bg-surface-100"><ArrowLeft size={14} />返回学习路径</button>
            <span className="text-xs text-surface-400">{chapterCtx?.stage.title || '当前阶段'}</span>
          </header>
          {focusedAccessDenied ? (
            <main className="m-auto max-w-sm rounded-2xl bg-white p-8 text-center shadow-soft">
              <Lock size={28} className="mx-auto mb-3 text-amber-500" />
              <h1 className="font-bold text-surface-900">请先完成当前阶段</h1>
              <p className="mt-2 text-sm text-surface-500">此任务会在前一阶段完成后自动解锁。</p>
              <button onClick={() => nav(returnToPath)} className="mt-5 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white">返回学习路径</button>
            </main>
          ) : !currentSection ? (
            <main className="m-auto flex items-center gap-2 text-sm text-surface-500"><Loader2 size={16} className="animate-spin" />正在读取任务…</main>
          ) : (
            <main className="grid flex-1 min-h-0 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_280px]">
              <article className="min-w-0 overflow-y-auto rounded-2xl bg-white p-5 shadow-soft">
                <div className="mb-5 flex items-start justify-between gap-3">
                  <div>
                    <p className="mb-1 text-xs text-primary-600">{chapterCtx?.stage.title || '当前阶段'}</p>
                    <h1 className="text-xl font-bold text-surface-900">{currentSection.title}</h1>
                    {currentSection.goal && <p className="mt-2 flex items-start gap-1.5 text-sm text-surface-500"><Target size={15} className="mt-0.5 text-amber-500" />{currentSection.goal}</p>}
                  </div>
                  <span className={`rounded-full px-2.5 py-1 text-xs ${completed ? 'bg-emerald-50 text-emerald-600' : 'bg-blue-50 text-blue-600'}`}>{completed ? '已完成' : '进行中'}</span>
                </div>
                {currentSection.knowledgePoints?.length > 0 && <div className="mb-5 flex flex-wrap gap-2">{currentSection.knowledgePoints.map(kp => <span key={kp.id} className="rounded-full bg-surface-100 px-2.5 py-1 text-xs text-surface-600">{kp.name}</span>)}</div>}
                {executionMode === 'video' && !videoLectureFallback ? <div className="space-y-3"><h2 className="text-lg font-semibold">视频学习</h2>{videoStatus === 'loading' ? <div className="flex min-h-48 items-center gap-2 text-sm text-surface-500"><Loader2 size={16} className="animate-spin" />正在查找高相关视频…</div> : videoStatus === 'failed' ? <div className="rounded-xl border border-amber-100 bg-amber-50 p-4 text-sm text-amber-800">视频资源搜索失败。<button onClick={retryVideoSearch} className="ml-2 underline">重新搜索</button></div> : videoResources.length ? <>{videoStatus === 'persisted' && <p className="text-sm text-surface-500">已显示持久化视频。</p>}{videoStatus === 'new_search' && <p className="text-sm text-surface-500">已显示本次新搜索视频。</p>}{videoStatus === 'stale' && <p className="rounded-xl border border-amber-100 bg-amber-50 p-3 text-sm text-amber-800">本次搜索暂不可用，正在展示上次有效结果。</p>}{videoResources.map((item: any) => <a key={item.url} href={item.url} target="_blank" rel="noreferrer" onClick={() => void recordVideoEvidence(item.url)} className="block rounded-xl border border-surface-200 p-4 hover:border-primary-300"><strong>{item.title}</strong><p className="mt-1 text-sm text-surface-500">{item.source} · {item.reason}</p><span className="mt-2 inline-block text-sm text-primary-600">打开外部视频</span></a>)}</> : <div className="rounded-xl border border-surface-200 p-4 text-sm text-surface-600">{videoStatus === 'search_unavailable' ? '搜索暂不可用，请稍后重新搜索。' : '暂无高相关视频'}</div>}<button onClick={() => void recordVideoEvidence('', true).then(() => setVideoLectureFallback(true)).catch((error) => setFocusedCompletionError(error?.response?.data?.detail || error?.message || '切换失败'))} className="rounded-lg border border-primary-200 px-4 py-2 text-sm text-primary-700">切换为图文讲解</button></div>
                : !lectureLoaded || generating ? <div className="flex min-h-48 items-center justify-center gap-2 text-sm text-surface-500"><Loader2 size={16} className="animate-spin" />正在准备真实讲义…</div>
                  : effectiveLectureContent ? <Markdown content={effectiveLectureContent} />
                  : <div className="rounded-xl border border-amber-100 bg-amber-50 p-4 text-sm text-amber-800">{lectureEnsureUnavailable ? '教材服务接口不可用，请刷新或重启后端' : '讲义暂不可用。'}<button onClick={() => { const scope = [sessionId, focusedSubjectId || workflowSubjectId, focusedPathId || path?.id, focusedStageId || chapterCtx?.stage.id, focusedTaskId || activeSectionId].join('|'); unavailableEnsureGuard.current.retry(scope); setLectureEnsureUnavailable(false); focusedGenerationRef.current = ''; void handleGenerate(); }} className="ml-2 font-medium underline">重新加载</button></div>}
                <div className="mt-8 border-t border-surface-100 pt-4">
                  <button disabled={completed || focusedCompleting || !resourceDayScope.globalDayIndex || generating || !!(lectureWorkflow && isActiveWorkflowStatus(lectureWorkflow.status)) || !(focusedReadingTask ? !!effectiveLectureContent : executionMode === 'video' && (videoOpened || videoLectureFallback && videoFallbackSelected && !!effectiveLectureContent))} onClick={completeFocusedTask} className="flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"><Check size={15} />{completed ? '任务已完成' : focusedCompleting ? '保存中…' : executionMode === 'video' ? videoOpened || videoFallbackSelected ? '完成视频学习' : '请先打开视频或切换图文讲解' : focusedReadingTask ? '标记完成' : '请先完成练习'}</button>
                  {focusedCompletionError && <p className="mt-2 text-sm text-red-600">完成失败：{focusedCompletionError}</p>}
                </div>
              </article>
              <aside className="flex min-h-0 flex-col overflow-hidden rounded-2xl bg-white shadow-soft">
                <div className="flex items-center gap-2 border-b border-surface-100 px-4 py-3 text-sm font-semibold text-surface-800"><MessageCircle size={16} className="text-violet-600" />智能辅导</div>
                <div className="flex-1 overflow-y-auto p-4">
                  {chatLoading ? <div className="flex items-center gap-2 text-sm text-surface-500"><Loader2 size={15} className="animate-spin" />思考中…</div>
                    : chatReply ? <Markdown content={chatReply} />
                    : <p className="text-sm leading-6 text-surface-500">我会结合本阶段、任务目标、知识点和当前讲义回答你的问题。</p>}
                </div>
                <div className="flex gap-2 border-t border-surface-100 p-3">
                  <input value={chatMsg} onChange={e => setChatMsg(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') void handleSendChat(); }} placeholder="问问本节内容…" className="min-w-0 flex-1 rounded-lg border border-surface-200 px-3 py-2 text-sm" />
                  <button onClick={() => void handleSendChat()} disabled={chatLoading || !chatMsg.trim()} className="rounded-lg bg-violet-600 px-3 text-white disabled:opacity-50"><Send size={15} /></button>
                </div>
              </aside>
            </main>
          )}
        </div>
      </div>
    );
  }
  if (pathMode === 'daily') {
    return (
      <DailyTaskPage
        chapterId={chapterId}
        sectionId={activeSectionId}
        onBack={() => nav(returnToPath)}
      />
    );
  }
  if (pathMode === 'focus') {
    return (
      <FocusSprintPage
        sectionId={activeSectionId}
        onBack={() => nav(returnToPath)}
      />
    );
  }

  return (
    <div className="flex h-screen -m-6">
      {/* ══ 左：章节 + 小节 ══ */}
      <div className="w-44 lg:w-52 xl:w-56 bg-white border-r border-surface-200 flex flex-col flex-shrink-0">
        <div className="p-4 bg-gradient-to-b from-surface-50 to-white border-b border-surface-100">
          <button onClick={() => nav('/path')}
            className="flex items-center gap-1.5 text-xs text-surface-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg px-2 py-1 -ml-2 mb-2 transition-colors">
            <ArrowLeft size={14} />返回学习路径
          </button>
          {/* ── 路径模式标签 ── */}
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 rounded-lg bg-blue-100 flex items-center justify-center"><Hash size={13} className="text-blue-600" /></div>
            <p className="text-xs font-bold text-surface-800 leading-snug flex-1">{chapterCtx?.chapter.title || '教材'}</p>
          </div>
          <div className="flex items-center gap-3 text-[10px] text-surface-400">
            <span className="flex items-center gap-1"><Layers size={10} />{sections.length} 小节</span>
            <span className="flex items-center gap-1"><GraduationCap size={10} />{totalKps} 知识点</span>
            <span className="flex items-center gap-1"><Clock size={10} />{Math.round(totalMin / 60)}h</span>
          </div>
          {totalKps > 0 && (
            <div className="flex items-center gap-2 mt-2">
              <div className="flex-1 h-1.5 bg-surface-100 rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-blue-400 to-emerald-400 rounded-full transition-all duration-500" style={{ width: `${Math.round((masteredKps / totalKps) * 100)}%` }} />
              </div>
              <span className="text-[10px] font-medium text-surface-500">{Math.round((masteredKps / totalKps) * 100)}%</span>
            </div>
          )}
        </div>
        <div className="flex-1 overflow-y-auto">
          {lectureWorkflow && <div className="p-4 pb-0"><WorkflowProgress key={`${lectureWorkflow.taskId}:${lectureWorkflow.status}`} state={lectureWorkflow} onCancel={cancelLectureGeneration} onRetry={() => handleGenerate()} /></div>}
          {sections.map((sec: Section, si: number) => {
            const isActive = sec.id === activeSectionId;
            const st = sectionStatusStyle[(sec.status as ContentStatus) || 'not_started'];
            const hasLecture = (sec.lectureIds?.length ?? 0) > 0 || generatedSectionIds.includes(sec.id);
            const kpCount = sec.knowledgePoints?.length ?? 0;
            return (
              <button key={sec.id} onClick={() => {
                if (prevLecture && originalLectureRef.current) {
                  store.setLecture(`${sessionId || ''}:${activeSectionId}`, originalLectureRef.current);
                }
                setQuizState('idle'); setPrevLecture('');
                setActiveSectionId(sec.id);
              }}
                className={`w-full text-left px-4 py-3 transition-all group relative ${isActive ? 'bg-blue-50' : 'hover:bg-surface-50'}`}>
                <div className={`absolute left-0 top-2 bottom-2 w-0.5 rounded-r-full transition-all ${isActive ? 'bg-blue-500' : 'bg-transparent group-hover:bg-surface-200'}`} />
                <div className="flex items-center gap-2.5">
                  <div className={`w-2.5 h-2.5 rounded-full ring-2 flex-shrink-0 ${st.dot} ${isActive ? 'scale-110' : ''} transition-transform`} />
                  <span className={`text-[10px] font-bold w-4 text-right flex-shrink-0 ${isActive ? 'text-blue-500' : 'text-surface-400'}`}>{si + 1}</span>
                  <div className="flex-1 min-w-0">
                    <p className={`text-xs truncate transition-colors ${isActive ? 'text-blue-700 font-semibold' : 'text-surface-700 group-hover:text-surface-800'}`}>{sec.title}</p>
                    <div className="flex items-center gap-2 mt-0.5 text-[10px] text-surface-400">
                      {hasLecture && <span className="text-blue-400 flex items-center gap-0.5"><BookOpen size={9} />教材</span>}
                      <span>{kpCount} 知识点</span>
                    </div>
                  </div>
                  {hasLecture && isActive && <CheckCircle2 size={13} className="text-emerald-400 flex-shrink-0" />}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* ══ 中：文档 + 小测 ══ */}
      <div className="flex-1 flex flex-col min-w-0 bg-surface-50/50">
        {/* 顶部工具栏 */}
        <div className="bg-white border-b border-surface-200">
          <div className="h-1 bg-gradient-to-r from-blue-500 via-violet-500 to-amber-500" />
          <div className="px-5 py-3.5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 text-[10px] text-surface-400 mb-2">
                  <span className="text-surface-500 truncate max-w-[200px]">{chapterCtx?.chapter.title}</span>
                </div>
                {prevLecture && (
                  <button onClick={() => {
                    store.setLecture(`${sessionId || ''}:${activeSectionId}`, originalLectureRef.current);
                    setQuizState('idle');
                    setPrevLecture('');
                  }}
                    className="flex items-center gap-1.5 text-xs text-surface-500 hover:text-surface-700 mb-1 transition-colors">
                    <ArrowLeft size={14} />返回文档
                  </button>
                )}
                <h2 className="text-lg font-bold text-surface-900">{currentSection?.title || '选择小节'}</h2>
                {currentSection?.goal && (
                  <p className="text-xs text-surface-400 mt-1.5 flex items-center gap-1.5"><Target size={11} className="text-amber-500 flex-shrink-0" />{currentSection.goal}</p>
                )}
                {(currentSection?.knowledgePoints?.length ?? 0) > 0 && (
                  <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                    {currentSection!.knowledgePoints.map((kp: any) => {
                      const kpSt = sectionStatusStyle[(kp.status as ContentStatus) || 'not_started'];
                      return (
                        <span key={kp.id} onClick={() => updateKnowledgePoint(kp.id, { status: kp.status === 'mastered' ? 'not_started' : 'mastered' })}
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] cursor-pointer hover:opacity-80 transition-opacity ${kp.status === 'mastered' ? 'bg-emerald-50 text-emerald-600' : 'bg-surface-100 text-surface-500'}`}>
                          <div className={`w-1.5 h-1.5 rounded-full ${kp.status === 'mastered' ? 'bg-emerald-400' : kpSt.dot}`} />
                          {kp.name}
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="flex items-center gap-2 flex-shrink-0">
                {/* ── Content type selector ── */}
                {lecture && (
                  <div className="flex items-center gap-0.5 bg-surface-100 rounded-xl p-0.5 mr-1">
                    {CONTENT_TYPE_OPTIONS.map(opt => (
                      <button
                        key={opt.value}
                        onClick={() => store.setContentType(opt.value)}
                        className={`flex items-center gap-1 px-2.5 py-1.5 rounded-[10px] text-[10px] font-medium transition-all
                          ${contentType === opt.value
                            ? 'bg-white text-surface-800 shadow-sm'
                            : 'text-surface-400 hover:text-surface-600'}`}
                        title={opt.label}
                      >
                        <span className="text-xs">{opt.icon}</span>
                        <span className="hidden sm:inline">{opt.label}</span>
                      </button>
                    ))}
                  </div>
                )}
                {lecture && (
                  <button onClick={() => handleSectionDownload('docx')} disabled={!!downloadLoading}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl border border-surface-200 text-surface-500 hover:bg-surface-50 hover:text-surface-700 text-xs transition-all disabled:opacity-50"
                    title="下载文档 (DOCX)">
                    <FileDown size={14} />
                    {downloadLoading === 'docx' ? '…' : 'DOCX'}
                  </button>
                )}
                {lecture && (
                  <button onClick={() => handleSectionDownload('pdf')} disabled={!!downloadLoading}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl border border-surface-200 text-surface-500 hover:bg-surface-50 hover:text-surface-700 text-xs transition-all disabled:opacity-50"
                    title="下载文档 (PDF)">
                    <FileDown size={14} />
                    {downloadLoading === 'pdf' ? '…' : 'PDF'}
                  </button>
                )}
                <button onClick={() => setShowRightPanel(!showRightPanel)}
                  className={`w-8 h-8 rounded-lg border transition-colors flex items-center justify-center ${showRightPanel ? 'bg-violet-50 border-violet-200 text-violet-500' : 'bg-white border-surface-200 text-surface-400 hover:bg-surface-50'}`}
                  title={showRightPanel ? '折叠功能面板' : '展开功能面板'}>
                  <MessageCircle size={14} />
                </button>
                {currentSection && (
                  <>
                    <button onClick={() => handleQuizGenerate()} disabled={quizState === 'generating'}
                      className="flex items-center gap-1.5 px-4 py-2.5 bg-accent-500 text-white rounded-xl text-sm font-semibold hover:bg-accent-600 disabled:opacity-50 transition-all shadow-sm"
                      style={{ backgroundColor: '#14b8a6' }}>
                      <HelpCircle size={14} />{quizState === 'generating' ? '...' : '生成小测'}
                    </button>
                    <button onClick={() => handleGenerate()} disabled={generating || loadingLecture}
                      className="flex items-center gap-1.5 px-4 py-2.5 bg-gradient-to-r from-blue-600 to-violet-600 text-white rounded-xl text-sm font-semibold hover:from-blue-700 hover:to-violet-700 disabled:opacity-50 transition-all shadow-md shadow-blue-200">
                      <Sparkles size={14} />{generating ? 'AI 正在生成…' : lecture ? '重新生成' : '生成教材'}
                    </button>
                  </>
                )}
              </div>
            </div>
            {sections.length > 1 && (
              <div className="flex items-center gap-3 mt-3 pt-3 border-t border-surface-100">
                <button onClick={() => { if (prevSection) setActiveSectionId(prevSection.id); }} disabled={!prevSection}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl transition-all disabled:opacity-25 enabled:hover:bg-surface-100 enabled:hover:text-blue-600 text-surface-500">
                  <ArrowLeft size={13} /><span className="hidden sm:inline">上一节</span>
                </button>
                <div className="flex-1 flex items-center justify-center gap-1">
                  {sections.map((_, i) => (
                    <div key={i} className={`w-1.5 h-1.5 rounded-full transition-all ${i === currentIdx ? 'bg-blue-500 scale-125' : i < currentIdx ? 'bg-emerald-400' : 'bg-surface-200'}`} />
                  ))}
                </div>
                <button onClick={() => { if (nextSection) setActiveSectionId(nextSection.id); }} disabled={!nextSection}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl transition-all disabled:opacity-25 enabled:hover:bg-surface-100 enabled:hover:text-blue-600 text-surface-500">
                  <span className="hidden sm:inline">下一节</span><ArrowRight size={13} />
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {/* ── Quiz Panel ── */}
          {quizState !== 'idle' && (
            <div className="p-4 border-b border-gray-200 bg-gray-50/50">
              {quizState === 'submitted' && quizTotalScore !== null && (
                <div className={`p-4 rounded-2xl mb-4 ${quizTotalScore >= 80 ? 'bg-success-50 border border-success-200' : quizTotalScore >= 50 ? 'bg-warning-50 border border-warning-200' : 'bg-error-50 border border-error-200'}`}>
                  <div className="flex items-center gap-3">
                    <div className={`w-12 h-12 rounded-full flex items-center justify-center text-xl font-bold ${quizTotalScore >= 80 ? 'bg-success-100 text-success-600' : quizTotalScore >= 50 ? 'bg-warning-100 text-warning-600' : 'bg-error-100 text-error-600'}`}>
                      {quizTotalScore}
                    </div>
                    <div>
                      <p className="font-semibold text-surface-800">
                        {quizTotalScore >= 80 ? '🎉 表现优秀！' : quizTotalScore >= 50 ? '📖 继续努力' : '💪 需要复习'}
                      </p>
                      <p className="text-xs text-surface-500">
                        建议状态：{quizSuggestion === 'mastered' ? '已掌握' : quizSuggestion === 'in_progress' ? '学习中' : '需复习'}
                      </p>
                      {quizPathCompletion.task && <p className="mt-1 text-xs text-success-700">学习路径任务已完成{quizPathCompletion.unlocked ? '，下一阶段已解锁' : ''}</p>}
                    </div>
                  </div>
                </div>
              )}

              {quizState === 'submitted' && quizWeakPoints.length > 0 && (
                <div className="p-4 bg-error-50/30 rounded-2xl border border-error-200 mb-4">
                  <h4 className="text-sm font-semibold text-error-700 mb-3">薄弱知识点</h4>
                  {quizWeakPoints.map((wp, i) => (
                    <div key={i} className="flex items-center justify-between py-2 border-b border-error-100 last:border-0">
                      <div className="flex-1 min-w-0">
                        <span className="text-xs text-surface-700 truncate block">{wp.name}</span>
                        {wp.suggestedAction && (
                          <span className="text-[10px] text-surface-400 mt-0.5 block truncate">{wp.suggestedAction}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-error-100 text-error-600 font-medium">错{wp.errorCount}次</span>
                        {wp.masteryEstimate != null && (
                          <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${wp.masteryEstimate >= 60 ? 'bg-warning-100 text-warning-600' : 'bg-error-100 text-error-600'}`}>掌握{wp.masteryEstimate}%</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {quizState === 'generating' && (
                <div className="flex items-center gap-3 p-4 text-surface-500">
                  <Loader2 size={18} className="animate-spin text-accent-500" />
                  <span className="text-sm">正在生成小测题目…</span>
                </div>
              )}

              {(quizState === 'answering' || quizState === 'submitted') && quizQuestions.map((q, idx) => {
                const result = quizResults.find(r => r.questionId === q.questionId);
                const answer = quizAnswers[q.questionId] || '';
                const isSubmitted = quizState === 'submitted';

                return (
                  <div key={q.questionId} className="bg-white rounded-2xl shadow-soft p-5 mb-4">
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-sm font-bold text-primary-600">#{idx + 1}</span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary-50 text-primary-600 font-medium">{typeLabel(q.type)}</span>
                      {q.difficulty && (
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${q.difficulty === 'easy' ? 'bg-success-50 text-success-600' : q.difficulty === 'hard' ? 'bg-error-50 text-error-600' : 'bg-warning-50 text-warning-600'}`}>
                          {q.difficulty === 'easy' ? '简单' : q.difficulty === 'hard' ? '困难' : '中等'}
                        </span>
                      )}
                      {result && (
                        <span className={`ml-auto text-sm font-bold ${result.isCorrect ? 'text-success-500' : 'text-error-500'}`}>{result.score}分</span>
                      )}
                    </div>
                    <div className="text-sm text-surface-800 mb-4 leading-relaxed"><Markdown content={q.stem} /></div>

                    {q.type === 'choice' && q.options && (
                      <div className="space-y-2">
                        {q.options.map((opt: string, oi: number) => {
                          const letter = String.fromCharCode(65 + oi);
                          const isSelected = answer === letter;
                          const isCorrectAnswer = result?.correctAnswer === letter;
                          let cls = 'border-2 hover:shadow-sm';
                          if (isSubmitted && isCorrectAnswer) cls += ' border-success-400 bg-success-50/70';
                          else if (isSubmitted && isSelected && !result?.isCorrect) cls += ' border-error-400 bg-error-50/70';
                          else if (isSelected && !isSubmitted) cls += ' border-primary-400 bg-primary-50/70';
                          else cls += ' border-surface-200 hover:border-primary-300 bg-white';
                          return (
                            <button key={letter} disabled={isSubmitted} onClick={() => handleQuizAnswer(q.questionId, letter)}
                              className={`w-full text-left px-4 py-3 rounded-xl transition-all flex items-center gap-3 ${cls}`}>
                              <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${isSelected && !isSubmitted ? 'bg-primary-500 text-white' : isSubmitted && isCorrectAnswer ? 'bg-success-500 text-white' : isSubmitted && isSelected ? 'bg-error-500 text-white' : 'bg-surface-100 text-surface-500'}`}>{letter}</span>
                              <span className="text-sm"><Markdown content={opt} /></span>
                              {isSubmitted && isCorrectAnswer && <Check className="w-4 h-4 text-success-500 ml-auto" />}
                              {isSubmitted && isSelected && !result?.isCorrect && <X className="w-4 h-4 text-error-500 ml-auto" />}
                            </button>
                          );
                        })}
                      </div>
                    )}

                    {q.type === 'truefalse' && (
                      <div className="flex gap-4">
                        {['true', 'false'].map(v => {
                          const isSelected = answer === v;
                          const isCorrectAnswer = result?.correctAnswer === v;
                          let cls = 'border-2 flex-1 px-6 py-4 rounded-xl text-sm font-medium transition-all';
                          if (isSubmitted && isCorrectAnswer) cls += ' border-success-400 bg-success-50/70';
                          else if (isSubmitted && isSelected && !result?.isCorrect) cls += ' border-error-400 bg-error-50/70';
                          else if (isSelected && !isSubmitted) cls += ' border-primary-400 bg-primary-50/70';
                          else cls += ' border-surface-200 hover:border-primary-300';
                          return (
                            <button key={v} disabled={isSubmitted} onClick={() => handleQuizAnswer(q.questionId, v)} className={cls}>
                              {v === 'true' ? '✓ 正确' : '✗ 错误'}
                            </button>
                          );
                        })}
                      </div>
                    )}

                    {(q.type === 'fill' || q.type === 'shortanswer') && (
                      <textarea value={answer} onChange={e => handleQuizAnswer(q.questionId, e.target.value)} disabled={isSubmitted}
                        rows={q.type === 'shortanswer' ? 4 : 2} placeholder="输入你的答案…"
                        className="w-full px-4 py-3 bg-surface-50 border-2 border-surface-200 rounded-xl resize-none focus:border-primary-400 focus:outline-none disabled:opacity-60 text-sm" />
                    )}

                    {result && (
                      <div className={`mt-4 p-4 rounded-xl ${result.isCorrect ? 'bg-success-50/70 border border-success-200' : 'bg-error-50/70 border border-error-200'}`}>
                        <div className="flex items-center gap-2 mb-2">
                          {result.isCorrect ? <Check className="w-4 h-4 text-success-500" /> : <X className="w-4 h-4 text-error-500" />}
                          <span className={`text-xs font-semibold ${result.isCorrect ? 'text-success-600' : 'text-error-600'}`}>{result.isCorrect ? '回答正确' : '回答错误'}</span>
                          {result.errorLabel && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-error-100 text-error-600">{result.errorLabel}</span>}
                        </div>
                        {!result.isCorrect && result.correctAnswer && (
                          <p className="text-xs text-surface-700 mb-1">✅ 正确答案：<span className="text-success-600 font-semibold">{result.correctAnswer}</span></p>
                        )}
                        {result.explanation ? (
                          <p className="text-xs text-surface-600 mt-1 leading-relaxed">📖 {result.explanation}</p>
                        ) : null}
                        {result.feedback ? (
                          <p className="text-xs text-primary-600 mt-1 leading-relaxed">💡 {result.feedback}</p>
                        ) : isSubmitted ? (
                          <p className="text-xs text-surface-400 mt-1">得分：{result.score}分</p>
                        ) : null}
                      </div>
                    )}
                  </div>
                );
              })}

              {quizState === 'answering' && (
                <div className="flex items-center justify-between pt-2">
                  <span className="text-xs text-surface-400">
                    {allAnswered ? '已完成所有题目' : `已答 ${Object.keys(quizAnswers).filter(k => quizAnswers[k]?.trim()).length} / ${quizQuestions.length} 题`}
                  </span>
                  <button onClick={handleQuizSubmit} disabled={!allAnswered}
                    className="px-6 py-2.5 bg-accent-500 text-white rounded-xl text-sm font-medium hover:bg-accent-600 disabled:opacity-40 transition-colors shadow-sm"
                    style={{ backgroundColor: allAnswered ? '#14b8a6' : undefined }}>提交批改</button>
                </div>
              )}

              {quizState === 'submitted' && (
                <div className="flex items-center justify-between pt-2">
                  <button onClick={() => {
                    const resetAnswers: Record<string, string> = {};
                    setQuizAnswers(resetAnswers);
                    setQuizResults([]);
                    setQuizTotalScore(null);
                    setQuizSuggestion('');
                    setQuizWeakPoints([]);
                    setQuizState('answering');
                    store.setQuiz(`${sessionId}:${activeSectionId}`, { questions: quizQuestions, quizId, answers: resetAnswers, results: [], totalScore: null, submitted: false, suggestion: '', weakPoints: [] });
                  }}
                    className="flex items-center gap-1.5 px-4 py-2 text-sm text-primary-600 hover:text-primary-700 hover:bg-primary-50 rounded-xl transition-colors">
                    <RefreshCw size={14} />重新答题
                  </button>
                  <button onClick={() => { setQuizState('idle'); setPrevLecture(''); }}
                    className="px-4 py-2 text-sm text-surface-500 hover:text-surface-700 hover:bg-surface-100 rounded-xl transition-colors">关闭小测</button>
                </div>
              )}
            </div>
          )}

          {/* ── Textbook mode: PDF viewer ── */}
          {executionMode === 'video' && !videoLectureFallback ? (
            <div className="mx-auto flex h-full w-full max-w-2xl flex-col justify-center gap-4 p-6">
              <h3 className="text-xl font-semibold text-surface-900">视频学习</h3>
              {videoStatus === 'loading' ? <div className="flex items-center gap-2 text-sm text-surface-500"><Loader2 size={16} className="animate-spin" />正在查找高相关视频…</div>
                : videoStatus === 'failed' ? <div className="rounded-xl border border-amber-100 bg-amber-50 p-4 text-sm text-amber-800">视频资源搜索失败，请稍后重试或返回学习路径。<button onClick={retryVideoSearch} className="ml-2 underline">重新搜索</button></div>
                : videoResources.length ? videoResources.map((item: any) => <a key={item.url} href={item.url} target="_blank" rel="noreferrer" onClick={() => void recordVideoEvidence(item.url)} className="rounded-xl border border-surface-200 bg-white p-4 hover:border-primary-300"><strong>{item.title}</strong><p className="mt-1 text-sm text-surface-500">{item.source} · {item.reason}</p><span className="mt-2 inline-block text-sm text-primary-600">打开外部视频</span></a>)
                : <p className="rounded-xl border border-surface-200 bg-white p-4 text-sm text-surface-600">暂未找到与当前任务高度相关的视频资源</p>}
              <button onClick={() => void recordVideoEvidence('', true).then(() => setVideoLectureFallback(true))} className="w-fit rounded-lg border border-primary-200 px-4 py-2 text-sm text-primary-700">切换为图文讲解</button>
              <button disabled={completed || focusedCompleting || !(videoOpened || videoFallbackSelected && !!effectiveLectureContent)} onClick={completeFocusedTask} className="w-fit rounded-lg bg-primary-600 px-4 py-2 text-sm text-white disabled:cursor-not-allowed disabled:opacity-60">{completed ? '本任务已完成' : focusedCompleting ? '保存中…' : videoOpened || videoFallbackSelected ? '完成视频学习' : '请先打开视频或切换图文讲解'}</button>
            </div>
          ) : isTextbookMode && activeSubject && currentSection ? (
            <TextbookViewer
              subjectId={activeSubject.id}
              pageStart={currentSection.textbookPageStart ?? 1}
              pageEnd={currentSection.textbookPageEnd ?? (currentSection.textbookPageStart ?? 1) + 5}
            />
          ) : quizState !== 'idle' ? null : sectionContent ? (
            /* ── Section content — routed by content_type ── */
            <div className="px-5 py-4 relative" onMouseUp={handleTextSelection}>
              {executionMode === 'video' && videoLectureFallback && <p className="mb-3 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700">当前使用图文讲解替代视频学习</p>}
              <SectionContentRouter
                content={sectionContent}
                onComplete={() => {
                  if (currentSection?.id && updateKnowledgePoint) {
                    (currentSection.knowledgePoints || []).forEach((kp: any) => {
                      updateKnowledgePoint(kp.id || kp.name, { status: 'mastered' });
                    });
                  }
                  if (executionMode === 'video') return;
                  logStudyEvent({
                    sessionId: sessionId || '',
                    event: 'section_complete',
                    resourceId: activeSectionId,
                    metadata: {
                      title: currentSection?.title || '',
                      content_type: contentType,
                      task_type: (currentSection as any)?.task_type || '',
                    },
                  }).catch(() => {});
                }}
              />
              {/* ── 划词引用栏 ── */}
              {quotedText && quotePos && (
                <div className="absolute z-50 -translate-x-1/2 bg-white border border-surface-200 rounded-xl shadow-lg px-2 py-1.5 flex items-center gap-1" style={{ left: quotePos.x, top: quotePos.y }}>
                  <span className="text-[10px] text-surface-400 truncate max-w-[120px] px-1">{quotedText.slice(0, 30)}{quotedText.length > 30 ? '…' : ''}</span>
                  <span className="w-px h-4 bg-surface-200" />
                  <button onClick={() => quoteAction('explain')} className="px-2 py-1 text-[10px] font-medium text-surface-600 hover:text-violet-600 hover:bg-violet-50 rounded-md transition-colors">解释</button>
                  <button onClick={() => quoteAction('diagram')} className="px-2 py-1 text-[10px] font-medium text-surface-600 hover:text-blue-600 hover:bg-blue-50 rounded-md transition-colors">图解</button>
                  <button onClick={() => quoteAction('quiz')} className="px-2 py-1 text-[10px] font-medium text-surface-600 hover:text-amber-600 hover:bg-amber-50 rounded-md transition-colors">出题</button>
                </div>
              )}
            </div>
          ) : loadingLecture ? (
            <div className="flex items-center justify-center h-full">
              <div className="w-6 h-6 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : !isTextbookMode ? (
            /* ── No textbook mode: show generate lecture prompt ── */
            <div className="flex flex-col items-center justify-center h-full gap-5">
              <div className="relative">
                <div className="w-24 h-24 rounded-3xl bg-gradient-to-br from-blue-100 via-violet-100 to-amber-100 flex items-center justify-center shadow-lg shadow-blue-100">
                  <Brain size={40} className="text-blue-500" />
                </div>
                <div className="absolute -bottom-1 -right-1 w-8 h-8 rounded-full bg-white shadow-md flex items-center justify-center">
                  <Sparkles size={14} className="text-amber-500" />
                </div>
              </div>
              <div className="text-center">
                <p className="text-base font-semibold text-surface-700">准备开始学习</p>
                <p className="text-sm text-surface-400 mt-1 max-w-xs">点击「生成教材」，AI 将按正式出版教材的标准编写本节内容</p>
              </div>
              <button onClick={() => handleGenerate()} disabled={generating || loadingLecture}
                className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-blue-600 to-violet-600 text-white rounded-xl text-sm font-semibold hover:from-blue-700 hover:to-violet-700 disabled:opacity-50 transition-all shadow-md shadow-blue-200">
                <Sparkles size={15} />{generating ? '生成中…' : '开始生成教材'}
              </button>
            </div>
          ) : null}
        </div>
      </div>

      {/* ══ 右：功能面板 ══ */}
      {showRightPanel && (
      <div className="w-64 lg:w-72 xl:w-80 bg-white border-l border-surface-200 flex flex-col flex-shrink-0 overflow-hidden relative">
        <button onClick={() => setShowRightPanel(false)}
          className="absolute top-2 right-2 z-10 w-6 h-6 rounded-md hover:bg-surface-100 flex items-center justify-center text-surface-400 hover:text-surface-600 transition-colors"
          title="折叠功能面板">
          <ChevronRight size={14} />
        </button>
        <div className="flex border-b border-surface-200 flex-shrink-0">
          {([
            ...(isTextbookMode
              ? [{ key: 'toc' as const, label: '教材目录', icon: <BookOpen size={12} />, color: 'blue' }]
              : []),
            { key: 'generate' as const, label: '生成', icon: <Sparkles size={12} />, color: 'slate' },
            { key: 'tutor' as const, label: '智能辅导', icon: <MessageCircle size={12} />, color: 'violet' },
            { key: 'resources' as const, label: '相关资源', icon: <Lightbulb size={12} />, color: 'amber' },
          ]).map(tab => (
            <button key={tab.key} onClick={() => setRightTab(tab.key)}
              className={`flex-1 flex items-center justify-center gap-1 py-2.5 text-[10px] font-medium transition-all border-b-2 ${rightTab === tab.key ? `border-${tab.color}-500 text-${tab.color}-700 bg-${tab.color}-50` : 'border-transparent text-surface-400 hover:text-surface-600'}`}>
              {tab.icon}{tab.label}
            </button>
          ))}
        </div>

        <div className="flex-1 flex flex-col min-h-0 overflow-y-auto">
          {rightTab === 'toc' && isTextbookMode && activeSubject && (
            <TextbookTocPanel
              chapters={textbookToc?.chapters ?? []}
              currentSectionId={currentSection?.textbookSectionId}
              currentPageStart={currentSection?.textbookPageStart}
              onSectionClick={(_chId, secId, pageStart) => {
                // Find the learning path section that matches this textbook section
                for (const stage of path?.stages ?? []) {
                  for (const ch of stage.chapters ?? []) {
                    for (const sec of ch.sections) {
                      if ((sec as any).textbookSectionId === secId) {
                        nav(`/lecture/section/${sec.id}`);
                        return;
                      }
                    }
                  }
                }
              }}
            />
          )}
          {rightTab === 'tutor' && (
            <div className="flex flex-col flex-1 min-h-0">
              {!chatReply && !chatLoading && currentSection && (
                <div className="px-3 py-3 space-y-1.5 flex-shrink-0">
                  {quotedText && (
                    <div className="p-2 rounded-lg bg-violet-50 border border-violet-100">
                      <p className="text-[10px] text-violet-600 font-medium mb-0.5">已引用</p>
                      <p className="text-[11px] text-violet-800 line-clamp-2">「{quotedText}」</p>
                    </div>
                  )}
                  <div className="space-y-1.5">
                    <button onClick={() => sendChat(quotedText ? `""${quotedText}""` : `请详细解释「${currentSection.knowledgePoints?.[0]?.name || '核心概念'}」的含义、原理和应用场景。`, quotedText ? 'explain' : 'concept_explanation')}
                      className="w-full p-2.5 rounded-lg bg-surface-50 hover:bg-surface-100 transition-colors text-left border border-transparent hover:border-surface-200">
                      <span className="text-xs font-medium text-surface-700">文字解答</span>
                      <p className="text-[10px] text-surface-400 mt-0.5">{quotedText ? '针对选中内容逐步讲解' : `"${currentSection.knowledgePoints?.[0]?.name || '核心概念'}"的含义与应用`}</p>
                    </button>
                    <button onClick={() => sendChat(quotedText ? `""${quotedText}"" 请用图解说明` : '请用图解和文字结合的方式，说明本节的核心知识结构。', 'diagram')}
                      className="w-full p-2.5 rounded-lg bg-surface-50 hover:bg-surface-100 transition-colors text-left border border-transparent hover:border-surface-200">
                      <span className="text-xs font-medium text-surface-700">图解说明</span>
                      <p className="text-[10px] text-surface-400 mt-0.5">{quotedText ? '为选中内容生成图解' : 'Mermaid 知识结构图 + 文字梳理'}</p>
                    </button>
                    <button onClick={() => handleGenerateVideo()} disabled={videoGenerating}
                      className="w-full p-2.5 rounded-lg bg-surface-50 hover:bg-surface-100 transition-colors text-left border border-transparent hover:border-surface-200 disabled:opacity-50">
                      <span className="text-xs font-medium text-surface-700">讲解动画</span>
                      <p className="text-[10px] text-surface-400 mt-0.5">
                        {videoGenerating && videoResult?.status === 'submitted' ? '动画正在生成中…' :
                         videoGenerating ? '提交中…' :
                         videoResult?.status === 'completed' ? '动画已生成，点击查看' :
                         videoResult?.script ? '已生成脚本，点击查看' : 'Manim 数学动画'}
                      </p>
                    </button>
                  </div>
                </div>
              )}
              <div className="flex-1 overflow-y-auto px-3 min-h-0">
                {chatReply ? (
                  <div>
                    <button onClick={() => { store.setChatReply(`${sessionId || 'anon'}:${activeSectionId}`, ''); setChatMsg(''); }}
                      className="flex items-center gap-1 text-[10px] text-surface-400 hover:text-surface-600 mb-2 transition-colors">
                      <ChevronLeft size={12} /> 返回
                    </button>
                    <div className="text-xs surface-600 leading-relaxed cursor-zoom-in" onClick={() => setZoomDiagram(chatReply)}>
                      <Markdown content={chatReply} />
                      <p className="text-[10px] text-surface-300 mt-2">点击内容可放大查看</p>
                    </div>
                  </div>
                ) : !chatLoading && (
                  <p className="text-[11px] text-surface-400 px-1">点击快捷提问或输入问题，AI 结合文档和知识点为你解答</p>
                )}
                {chatLoading && (
                  <div className="flex items-center gap-2 text-xs text-surface-500 px-1"><div className="w-3 h-3 border-2 border-surface-300 border-t-transparent rounded-full animate-spin" />思考中…</div>
                )}
              </div>
              <div className="p-3 border-t border-surface-100 flex-shrink-0">
                <div className="flex gap-1.5">
                  <input value={chatMsg} onChange={e => setChatMsg(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') handleSendChat(); }} placeholder="输入问题…"
                    className="flex-1 px-3 py-2 bg-surface-50 border border-surface-200 rounded-lg text-xs focus:outline-none focus:border-violet-300 focus:ring-2 focus:ring-violet-100 transition-all" />
                  <button onClick={handleSendChat} disabled={chatLoading} className="px-3 py-2 bg-violet-600 text-white rounded-lg hover:bg-violet-700 disabled:opacity-50 transition-colors shadow-sm"><Send size={13} /></button>
                </div>
              </div>
            </div>
          )}

          {rightTab === 'resources' && (
            <div className="space-y-3">
              <SectionResourceWorkspace
                sessionId={sessionId}
                pathId={path?.id || ''}
                stageId={chapterCtx?.stage.id || ''}
                chapterId={chapterCtx?.chapter.id || ''}
              chapterTitle={chapterCtx?.chapter.title || ''}
              section={currentSection}
              taskId={resourceTaskId}
              dayId={resourceDayScope.dayId}
              globalDayIndex={resourceDayScope.globalDayIndex}
              lectureContent={effectiveLectureContent}
                sections={sections}
                legacyMindmapId={chapterCtx?.chapter.mindmapId}
              />
            </div>
          )}

          {rightTab === 'generate' && (
            <>
            <GeneratePanel
              ref={generatePanelRef}
              sessionId={sessionId || ''}
              activeSectionId={activeSectionId}
              currentSection={currentSection}
              chapterCtx={chapterCtx}
              lecture={lecture}
              generating={generating}
              genAll={genAll}
              onViewContent={(c: any) => {
                if (c.status !== 'ready') return;
                const sk = `${sessionId || ''}:${activeSectionId}`;
                // 首次离开文档时保存原始文档（连续点卡片不会覆盖）
                if (!prevLecture) {
                  originalLectureRef.current = store.lectureCache[sk] || '';
                }
                setPrevLecture('1'); // 任意非空值，触发返回按钮显示
                if (c.type === 'quiz' && c.quizData?.questions?.length) {
                  const stored = store.quizCache[sk];
                  const qd = (stored && stored.quizId === c.quizData.quizId) ? stored : c.quizData;
                  setQuizQuestions(qd.questions || []);
                  setQuizId(qd.quizId || '');
                  setQuizAnswers(qd.answers || {});
                  setQuizResults(qd.results || []);
                  setQuizTotalScore(qd.totalScore ?? null);
                  setQuizState(qd.submitted ? 'submitted' : 'answering');
                } else if (c.type === 'lecture' && c.content) {
                  store.setLecture(sk, c.content);
                } else if (c.type === 'mindmap' && c.content) {
                  store.setLecture(sk, `> 🧠 以下为**思维导图**。点击上方「返回文档」回到正文。\n\n\`\`\`mermaid\n${c.content}\n\`\`\``);
                } else if (c.type === 'reading' && c.content) {
                  store.setLecture(sk, `> 📖 以下为**拓展阅读**内容，与文档互补。点击上方「返回文档」回到正文。\n\n${c.content}`);
                } else if (c.type === 'practice' && c.content) {
                  store.setLecture(sk, `> 💻 以下为**实操案例**内容。点击上方「返回文档」回到正文。\n\n${c.content}`);
                } else if (c.type === 'video' && c.content) {
                  const isVideoUrl = /\.(mp4|webm)(\?|$)/i.test(c.content) || c.content.startsWith('/api/multimodal/file/');
                  if (isVideoUrl) {
                    store.setLecture(sk, `> 🎬 教学视频已生成\n>\n> [▶ 点击播放视频](${c.content})\n>\n> 点击上方「返回文档」回到正文。`);
                  } else {
                    store.setLecture(sk, `> 🎬 以下为**教学视频**内容。点击上方「返回文档」回到正文。\n\n${c.content}`);
                  }
                }
              }}
              onGenerateLecture={(cardId, req) => handleGenerate(cardId, req)}
              onGenerateQuiz={(cardId, req) => handleQuizGenerate(cardId, req)}
              onGenerateVideo={(cardId, req) => handleGenerateVideo(cardId, req)}
              onGenerateReading={async (cardId: string, requirements?: string) => {
                if (!activeSectionId || !sessionId || !currentSection) return;
                try {
                  const res = await fetch(`/api/sections/${encodeURIComponent(activeSectionId)}/lecture/generate`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
                    body: JSON.stringify({ sessionId, sectionTitle: currentSection.title, sectionGoal: currentSection.goal, type: 'reading', knowledgePoints: currentSection.knowledgePoints || [], lectureContent: effectiveLectureContent.slice(0, 3000), requirements: requirements || '' }),
                  });
                  const data = await res.json();
                  const ok = !!data?.data?.lecture?.content;
                  generatePanelRef.current?.updateRecord(cardId, { status: ok ? 'ready' : 'error', content: data?.data?.lecture?.content || '' });
                } catch {
                  generatePanelRef.current?.updateRecord(cardId, { status: 'error' });
                }
              }}
              onGeneratePractice={async (cardId: string, requirements?: string) => {
                if (!activeSectionId || !sessionId || !currentSection) return;
                try {
                  const res = await fetch(`/api/sections/${encodeURIComponent(activeSectionId)}/lecture/generate`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
                    body: JSON.stringify({ sessionId, sectionTitle: currentSection.title, sectionGoal: currentSection.goal, type: 'practice', knowledgePoints: currentSection.knowledgePoints || [], lectureContent: effectiveLectureContent.slice(0, 3000), requirements: requirements || '' }),
                  });
                  const data = await res.json();
                  const ok = !!data?.data?.lecture?.content;
                  generatePanelRef.current?.updateRecord(cardId, { status: ok ? 'ready' : 'error', content: data?.data?.lecture?.content || '' });
                } catch {
                  generatePanelRef.current?.updateRecord(cardId, { status: 'error' });
                }
              }}
              onGenerateMindmap={async (cardId: string, requirements?: string) => {
                if (!activeSectionId || !sessionId || !currentSection) return;
                try {
                  const { generateSectionMindmap } = await import('../api/sectionResources');
                  const r = await generateSectionMindmap(activeSectionId, {
                    sessionId, pathId: path?.id || '', stageId: chapterCtx?.stage.id || '',
                    sectionTitle: currentSection.title,
                    knowledgePoints: currentSection.knowledgePoints || [],
                    lectureContent: effectiveLectureContent, regenerate: false,
                  });
                  const mm = (r as any)?.mindmap || r;
                  generatePanelRef.current?.updateRecord(cardId, { status: 'ready', content: mm?.mermaidDef || '' });
                } catch {
                  generatePanelRef.current?.updateRecord(cardId, { status: 'error' });
                }
              }}
              onGenerateAll={async () => {
                if (!currentSection || !sessionId) return;
                setGenAll(true);
                try {
                  const res = await fetch(`/api/sections/${encodeURIComponent(activeSectionId)}/generate-all`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
                    body: JSON.stringify({ sessionId, sectionTitle: currentSection.title, sectionGoal: currentSection.goal || '', chapterId: chapterCtx?.chapter.id || '', stageId: chapterCtx?.stage.id || '', knowledgePoints: currentSection.knowledgePoints || [], lectureContent: effectiveLectureContent }),
                  }).then(r => r.json());
                  const data = res?.data || res;
                  if (data?.lecture_content) store.setLecture(`${sessionId}:${activeSectionId}`, data.lecture_content);
                  // Check for async video task
                  const videoResource = (data?.resources || []).find((r: any) => r.task_id);
                  if (videoResource?.task_id) {
                    setVideoResult({ status: 'submitted', task_id: videoResource.task_id, script: videoResource.content, userMessage: '视频正在生成中…' });
                    setVideoGenerating(true);
                    const poll = async () => {
                      for (let i = 0; i < 30; i++) {
                        await new Promise(r => setTimeout(r, 10000));
                        try {
                          const pr = await fetch(`/api/video/task/${encodeURIComponent(videoResource.task_id)}`, { headers: authHeaders() });
                          const pd = await pr.json();
                          const pollData = pd?.data || pd;
                          if (pollData.status === 'success' && pollData.video_url) {
                            setVideoResult((prev: any) => ({ ...prev, status: 'completed', url: pollData.video_url, userMessage: '视频已生成！' }));
                            setVideoGenerating(false);
                            return;
                          }
                          if (pollData.status === 'failed') {
                            setVideoResult((prev: any) => ({ ...prev, status: 'generation_failed', userMessage: pollData.message || '视频生成失败' }));
                            setVideoGenerating(false);
                            return;
                          }
                        } catch { /* retry */ }
                      }
                      setVideoResult((prev: any) => ({ ...prev, status: 'generation_failed', userMessage: '视频生成超时，请稍后重试。' }));
                      setVideoGenerating(false);
                    };
                    poll();
                  }
                } catch {} finally { setGenAll(false); }
              }}
            />
            {/* ── 资源卡片生成（小结卡/概念对比/例题详解等）── */}
            <ResourceCardGenerator
              sessionId={sessionId || ''}
              section={currentSection}
              pathId={path?.id || ''}
              stageId={chapterCtx?.stage.id || ''}
              chapterId={chapterCtx?.chapter.id || ''}
              taskId={resourceTaskId}
              dayId={resourceDayScope.dayId}
              globalDayIndex={resourceDayScope.globalDayIndex}
              lectureContent={effectiveLectureContent}
            />
            </>
          )}
        </div>
      </div>
      )}
      {!showRightPanel && (
        <button onClick={() => setShowRightPanel(true)}
          className="absolute right-4 top-4 z-10 w-8 h-8 rounded-lg bg-white border border-surface-200 shadow-sm flex items-center justify-center hover:bg-surface-50 transition-colors"
          title="展开功能面板">
          <MessageCircle size={14} className="text-surface-400" />
        </button>
      )}

      {/* ── 图解放大层 ── */}
      {zoomDiagram && (
        <div className="fixed inset-0 z-[100] bg-black/50 flex items-center justify-center p-8" onClick={() => setZoomDiagram('')}>
          <div className="relative bg-white rounded-2xl p-8 w-[85vw] h-[85vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <button onClick={() => setZoomDiagram('')} className="absolute top-4 right-4 w-8 h-8 rounded-full bg-surface-100 hover:bg-surface-200 flex items-center justify-center text-surface-500 z-10"><X size={16} /></button>
            <div className="text-sm leading-relaxed"><Markdown content={zoomDiagram} /></div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── 资源卡片生成器（小结卡/概念对比/例题详解等）──
function ResourceCardGenerator({ sessionId, section, pathId, stageId, chapterId, taskId, dayId, globalDayIndex, lectureContent }: {
  sessionId: string; section: any; pathId: string; stageId: string; chapterId: string; taskId: string; dayId?: string; globalDayIndex?: number; lectureContent: string;
}) {
  const subjectId = useSubjectStore.getState().activeSubject?.id;
  const [generated, setGenerated] = useState<any[]>([]);
  const [generating, setGenerating] = useState<string | null>(null);
  const [selectedType, setSelectedType] = useState('summary_card');
  const [preview, setPreview] = useState<any>(null);

  useEffect(() => {
    if (!sessionId || !section?.id || !pathId || !stageId || !taskId) { setGenerated([]); return; }
    let active = true;
    const controller = new AbortController();
    import('../api/sectionResources').then(({ getGeneratedSectionResources }) =>
      getGeneratedSectionResources(section.id, sessionId, subjectId, { pathId, stageId, taskId, dayId, globalDayIndex }, controller.signal).then(items => active && setGenerated(items)).catch(() => active && setGenerated([]))
    );
    return () => { active = false; controller.abort(); };
  }, [sessionId, section?.id, subjectId, pathId, stageId, taskId, dayId, globalDayIndex]);

  const generate = async (resourceType: string) => {
    if (!sessionId || !section) return;
    setGenerating(resourceType);
    try {
      const { generateSectionResource } = await import('../api/sectionResources');
      const result = await generateSectionResource(section.id, {
        sessionId, resourceType, pathId, stageId, chapterId, sectionTitle: section.title,
        subjectId, knowledgePoints: section.knowledgePoints, lectureContent,
        regenerate: generated.some(item => item.resourceType === resourceType),
      });
      setGenerated(items => [result.resource, ...items.filter(item => item.id !== result.resource.id)]);
      setPreview(result.resource);
    } catch {} finally { setGenerating(null); }
  };

  const labels: Record<string, string> = {
    summary_card: '总结卡片', concept_comparison: '概念对比', worked_example: '例题详解',
    mistake_checklist: '易错清单', review_notes: '复习笔记', knowledge_map: '知识结构图',
    process_flow: '学习流程图', concept_diagram: '概念对比图', execution_trace: '执行过程图', code_trace: '代码运行轨迹',
  };

  return (
    <div className="border-t border-surface-100 pt-4 mt-4 space-y-2">
      <div className="flex items-center gap-2">
        <Sparkles size={14} className="text-amber-500" />
        <p className="text-xs font-semibold text-surface-700">生成本节学习卡片</p>
      </div>
      <p className="text-[10px] text-surface-400">LLM 生成，保存到当前会话的资源库。</p>
      <div className="flex gap-2">
        <select value={selectedType} onChange={e => setSelectedType(e.target.value)}
          className="min-w-0 flex-1 rounded-lg border border-surface-200 bg-white px-2 py-2 text-xs text-surface-600">
          {['summary_card','concept_comparison','worked_example','mistake_checklist','review_notes','knowledge_map','process_flow','concept_diagram','execution_trace','code_trace'].map(t =>
            <option key={t} value={t}>{labels[t] || t}</option>
          )}
        </select>
        <button onClick={() => generate(selectedType)} disabled={!!generating || !section}
          className="inline-flex items-center gap-1 rounded-lg bg-amber-600 px-3 py-2 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-40">
          {generating === selectedType ? <Loader2 size={13} className="animate-spin" /> : <FileText size={13} />}
          生成
        </button>
      </div>
      {generated.length > 0 && <div className="space-y-1.5 pt-1">
        {generated.map(item => (
          <button key={item.id} onClick={() => setPreview(item)}
            className={`w-full rounded-lg border px-2.5 py-2 text-left text-xs transition-colors ${preview?.id === item.id ? 'border-amber-200 bg-amber-50 text-amber-700' : 'border-surface-100 bg-surface-50 text-surface-600 hover:bg-surface-100'}`}>
            <span className="font-medium">{item.title}</span>
          </button>
        ))}
      </div>}
      {preview && (
        <div className="space-y-2 rounded-xl border border-surface-200 bg-white p-3">
          <p className="text-xs font-semibold text-surface-700">{preview.title}</p>
          {preview.mermaidDef && <div className="rounded-lg border border-surface-100 bg-white p-2"><MermaidDiagram definition={preview.mermaidDef} /></div>}
          <div className="prose prose-sm max-w-none text-xs"><Markdown content={preview.content} /></div>
        </div>
      )}
    </div>
  );
}
