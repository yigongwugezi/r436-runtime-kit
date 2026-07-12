import { useState, useEffect, useMemo, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useLearningPath } from '../hooks/useLearningPath';
import { useChatStore } from '../store/chatStore';
import { ChevronRight, Sparkles, MessageCircle, Send, Brain, BookOpen, ArrowLeft, ArrowRight, Target, Lightbulb, Layers, Clock, GraduationCap, Hash, CheckCircle2, Check, X, Loader2, HelpCircle } from 'lucide-react';
import Markdown from '../utils/markdown';
import { generateSectionQuiz, submitQuizAttempt } from '../api/assessment';
import type { Chapter, LearningStage, PathNode, Section, ContentStatus } from '../types/learningPath';
import type { LinkedQuestion, QuizResult, WeakPoint } from '../types/assessment';
import SectionResourceWorkspace from '../components/learning/SectionResourceWorkspace';
import SectionContentRouter, { type ContentType, type SectionContent } from '../components/learning/SectionContentRouter';
import GeneratePanel from '../components/learning/GeneratePanel';
import { logStudyEvent } from '../api/feedback';

const CONTENT_TYPE_OPTIONS: { value: ContentType; label: string; icon: string }[] = [
  { value: 'lecture', label: '讲义', icon: '📖' },
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

export default function LecturePage() {
  const { chapterId, sectionId } = useParams<{ chapterId?: string; sectionId?: string }>();
  const nav = useNavigate();
  const { path, updateKnowledgePoint } = useLearningPath();
  const sessionId = useChatStore((s) => s.dataSessionId);
  const [lecture, setLecture] = useState('');
  const [lectureLoaded, setLectureLoaded] = useState(false);
  const [generating, setGenerating] = useState(false);

  // ── 当前章节与小节 ──
  const chapterCtx = useMemo(() => {
    for (const stage of (path?.stages ?? [])) {
      for (const ch of (stage.chapters ?? [])) {
        if (ch.id === chapterId || ch.sections.some(section => section.id === sectionId)) return { chapter: ch, stage };
      }
      const legacyNode = sectionId ? stage.nodes?.find(node => node.id === sectionId) : undefined;
      if (legacyNode) {
        return {
          chapter: {
            id: stage.id,
            title: stage.title,
            order: stage.order,
            status: 'not_started' as ContentStatus,
            sections: [legacyNodeSection(legacyNode)],
          },
          stage,
        };
      }
      // Older generated paths only retain stage tasks. Keep their existing
      // route IDs usable without changing the persisted learning-path shape.
      if (sectionId && sectionId.startsWith(`${stage.id}_`)) {
        return {
          chapter: {
            id: stage.id,
            title: stage.title,
            order: stage.order,
            status: 'not_started' as ContentStatus,
            sections: [legacyStageSection(stage, sectionId)],
          },
          stage,
        };
      }
    }
    const routeStageId = sectionId?.match(/^(.*)_node_\d+$/)?.[1];
    if (sectionId && routeStageId) {
      const stageTitle = lecture.match(/^#\s*学习《(.+?)》核心内容/m)?.[1] || '当前章节';
      const routeStage: LearningStage = {
        id: routeStageId, title: stageTitle, order: 0, description: '', nodes: [], chapters: [], objective: '', estimatedDays: 0,
      };
      return {
        chapter: { id: routeStageId, title: stageTitle, order: 0, status: 'not_started' as ContentStatus, sections: [legacyStageSection(routeStage, sectionId)] },
        stage: routeStage,
      };
    }
    return null;
  }, [path, chapterId, sectionId, lecture]);

  const sections = chapterCtx?.chapter.sections ?? [];
  const [activeSectionId, setActiveSectionId] = useState(sectionId || sections[0]?.id || '');
  const [chatMsg, setChatMsg] = useState('');
  const [chatReply, setChatReply] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [rightTab, setRightTab] = useState<'generate' | 'resources' | 'tutor'>('tutor');
  const [genAll, setGenAll] = useState(false);
  const [prevLecture, setPrevLecture] = useState('');
  const [generatedSectionIds, setGeneratedSectionIds] = useState<Set<string>>(new Set());
  const [showRightPanel, setShowRightPanel] = useState(true);

  // ── Quiz state ──
  const [quizState, setQuizState] = useState<'idle' | 'generating' | 'answering' | 'submitted'>('idle');
  const [quizQuestions, setQuizQuestions] = useState<LinkedQuestion[]>([]);
  const [quizId, setQuizId] = useState('');
  const [quizAnswers, setQuizAnswers] = useState<Record<string, string>>({});
  const [quizResults, setQuizResults] = useState<QuizResult[]>([]);
  const [quizTotalScore, setQuizTotalScore] = useState<number | null>(null);
  const [quizSuggestion, setQuizSuggestion] = useState('');
  const [quizWeakPoints, setQuizWeakPoints] = useState<WeakPoint[]>([]);
  const [contentType, setContentType] = useState<ContentType>('lecture');

  // Reset quiz + content type when section changes
  useEffect(() => {
    setQuizState('idle');
    setQuizQuestions([]);
    setQuizId('');
    setQuizAnswers({});
    setQuizResults([]);
    setQuizTotalScore(null);
    setQuizSuggestion('');
    setQuizWeakPoints([]);
    // Reset content type to whatever the planner specified, or auto-detect
    const planned = currentSection?.contentType as ContentType | undefined;
    setContentType(planned || (lecture ? detectContentType(lecture) : 'lecture'));
  }, [activeSectionId]);

  useEffect(() => {
    setActiveSectionId(sectionId || sections[0]?.id || '');
  }, [sectionId, sections]);

  const currentSection = sections.find((s: Section) => s.id === activeSectionId);
  const currentIdx = sections.findIndex((s: Section) => s.id === activeSectionId);
  const prevSection = currentIdx > 0 ? sections[currentIdx - 1] : null;
  const nextSection = currentIdx < sections.length - 1 ? sections[currentIdx + 1] : null;

  // ── 加载已有讲义 ──
  const [loadedSectionIds, setLoadedSectionIds] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!activeSectionId) return;
    if (loadedSectionIds.has(activeSectionId)) return;
    setLecture('');
    setLectureLoaded(false);
    const url = `/api/sections/${encodeURIComponent(activeSectionId)}/lecture?sessionId=${encodeURIComponent(sessionId || '')}`;
    fetch(url)
      .then(r => r.json())
      .then(d => {
        setLoadedSectionIds(prev => new Set(prev).add(activeSectionId));
        if (d?.data?.lecture?.content) {
          setLecture(d.data.lecture.content);
          setGeneratedSectionIds(prev => new Set(prev).add(activeSectionId));
        }
      })
      .catch(() => setLoadedSectionIds(prev => new Set(prev).add(activeSectionId)))
      .finally(() => setLectureLoaded(true));
  }, [activeSectionId, sessionId]);

  const totalKps = chapterCtx?.chapter.sections?.reduce((s, sec) => s + (sec.knowledgePoints?.length ?? 0), 0) ?? 0;
  const masteredKps = chapterCtx?.chapter.sections?.reduce((s, sec) => s + (sec.knowledgePoints?.filter(k => k.status === 'mastered').length ?? 0), 0) ?? 0;
  const totalMin = chapterCtx?.chapter.sections?.reduce((s, sec) => s + (sec.estimatedMinutes ?? 45), 0) ?? 0;

  const handleGenerate = useCallback(async () => {
    if (!currentSection || !sessionId) return;
    setGenerating(true);
    try {
      const res = await fetch(`/api/sections/${encodeURIComponent(activeSectionId)}/lecture/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sessionId,
          sectionTitle: currentSection.title,
          sectionGoal: currentSection.goal || '',
          chapterId: chapterCtx?.chapter.id || '',
          stageId: chapterCtx?.stage.id || '',
          pathId: path?.id || '',
          courseId: path?.courseName || '',
          knowledgePoints: currentSection.knowledgePoints || [],
        }),
      });
      const data = await res.json();
      if (data?.data?.lecture?.content) {
        setLecture(data.data.lecture.content);
        setGeneratedSectionIds(prev => new Set(prev).add(activeSectionId));
      }
    } catch {} finally { setGenerating(false); }
  }, [currentSection, activeSectionId, sessionId, chapterCtx, path]);

  const [videoGenerating, setVideoGenerating] = useState(false);
  const [videoResult, setVideoResult] = useState<any>(null);

  const sendChat = useCallback(async (question: string, actionType = '') => {
    if (!question.trim() || !sessionId || !currentSection) return;
    setChatMsg(''); setChatLoading(true); setChatReply('');
    try {
      const res = await fetch(`/api/sections/${encodeURIComponent(activeSectionId)}/tutor/ask`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sessionId, question,
          sectionTitle: currentSection.title,
          sectionGoal: currentSection.goal || '',
          knowledgePoints: currentSection.knowledgePoints || [],
          lectureExcerpt: lecture.slice(0, 1000),
          actionType,
        }),
      });
      const data = await res.json();
      if (data?.data?.reply) setChatReply(data.data.reply);
      else if (data?.status === 'error') setChatReply(`出错了：${data.message}`);
    } catch {} finally { setChatLoading(false); }
  }, [sessionId, currentSection, activeSectionId, lecture]);

  const handleGenerateVideo = useCallback(async () => {
    if (!sessionId || !currentSection) return;
    setVideoGenerating(true); setVideoResult(null);
    try {
      const res = await fetch(`/api/sections/${encodeURIComponent(activeSectionId)}/tutor/video`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId, sectionTitle: currentSection.title }),
      });
      const data = await res.json();
      setVideoResult(data?.data?.video || {
        status: 'generation_failed',
        userMessage: data?.message || '讲解视频生成失败，请稍后重试。',
      });
    } catch {
      setVideoResult({ status: 'generation_failed', userMessage: '讲解视频生成失败，请稍后重试。' });
    } finally { setVideoGenerating(false); }
  }, [sessionId, currentSection, activeSectionId]);

  const handleSendChat = useCallback(async () => {
    await sendChat(chatMsg);
  }, [chatMsg, sendChat]);

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
  const handleQuizGenerate = async () => {
    if (!currentSection) return;
    const kpNames = (currentSection.knowledgePoints || []).map((kp: any) => kp.name || kp).filter(Boolean);
    setQuizState('generating');
    try {
      const res = await generateSectionQuiz(activeSectionId, {
        sessionId: sessionId || `lecture_${activeSectionId}`,
        title: currentSection.title || '当前小节',
        knowledgePoints: kpNames.length > 0 ? kpNames.slice(0, 5) : [chapterCtx?.chapter.title || '', currentSection.title || ''].filter(Boolean),
        lectureSummary: lecture.slice(0, 1500),
        difficulty: 'medium',
        pathId: path?.id || '',
        stageId: chapterCtx?.stage.id || '',
        chapterId: chapterCtx?.chapter.id || '',
        sectionId: activeSectionId,
      }) as any;
      const data = res?.data || res;
      if (data?.questions && data?.quiz) {
        setQuizQuestions(data.questions);
        setQuizId(data.quiz.id);
        setQuizAnswers({});
        setQuizResults([]);
        setQuizTotalScore(null);
        setQuizState('answering');
      }
    } catch (e: any) {
      alert('小测生成失败: ' + (e?.message || '请重试'));
      setQuizState('idle');
    }
  };

  const handleQuizAnswer = (questionId: string, value: string) => {
    setQuizAnswers(a => ({ ...a, [questionId]: value }));
  };

  const allAnswered = quizQuestions.every(q => quizAnswers[q.questionId]?.trim());

  const handleQuizSubmit = async () => {
    if (!allAnswered || quizState !== 'answering') return;
    const answers = quizQuestions.map(q => ({
      questionId: q.questionId,
      answer: quizAnswers[q.questionId] || '',
    }));
    try {
      const res = await submitQuizAttempt(quizId, {
        sessionId: sessionId || `lecture_${activeSectionId}`,
        answers,
      }) as any;
      const data = res?.data || res;
      if (data?.results) {
        setQuizResults(data.results);
        setQuizTotalScore(data.totalScore ?? null);
        setQuizSuggestion(data.sectionStatusSuggestion || '');
        setQuizWeakPoints(data.weakPoints || []);
        setQuizState('submitted');
      }
    } catch (e: any) {
      alert('提交失败: ' + (e?.message || '请重试'));
    }
  };

  const typeLabel = (t: string) => t === 'choice' ? '选择题' : t === 'truefalse' ? '判断题' : t === 'fill' ? '填空题' : '简答题';

  return (
    <div className="flex h-screen -m-6">
      {/* ══ 左：章节 + 小节 ══ */}
      <div className="w-44 lg:w-52 xl:w-56 bg-white border-r border-surface-200 flex flex-col flex-shrink-0">
        <div className="p-4 bg-gradient-to-b from-surface-50 to-white border-b border-surface-100">
          <button onClick={() => nav('/path')}
            className="flex items-center gap-1.5 text-xs text-surface-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg px-2 py-1 -ml-2 mb-2 transition-colors">
            <ArrowLeft size={14} />返回学习路径
          </button>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 rounded-lg bg-blue-100 flex items-center justify-center"><Hash size={13} className="text-blue-600" /></div>
            <p className="text-xs font-bold text-surface-800 leading-snug flex-1">{chapterCtx?.chapter.title || '讲义'}</p>
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
          {sections.map((sec: Section, si: number) => {
            const isActive = sec.id === activeSectionId;
            const st = sectionStatusStyle[(sec.status as ContentStatus) || 'not_started'];
            const hasLecture = (sec.lectureIds?.length ?? 0) > 0 || generatedSectionIds.has(sec.id);
            const kpCount = sec.knowledgePoints?.length ?? 0;
            return (
              <button key={sec.id} onClick={() => setActiveSectionId(sec.id)}
                className={`w-full text-left px-4 py-3 transition-all group relative ${isActive ? 'bg-blue-50' : 'hover:bg-surface-50'}`}>
                <div className={`absolute left-0 top-2 bottom-2 w-0.5 rounded-r-full transition-all ${isActive ? 'bg-blue-500' : 'bg-transparent group-hover:bg-surface-200'}`} />
                <div className="flex items-center gap-2.5">
                  <div className={`w-2.5 h-2.5 rounded-full ring-2 flex-shrink-0 ${st.dot} ${isActive ? 'scale-110' : ''} transition-transform`} />
                  <span className={`text-[10px] font-bold w-4 text-right flex-shrink-0 ${isActive ? 'text-blue-500' : 'text-surface-400'}`}>{si + 1}</span>
                  <div className="flex-1 min-w-0">
                    <p className={`text-xs truncate transition-colors ${isActive ? 'text-blue-700 font-semibold' : 'text-surface-700 group-hover:text-surface-800'}`}>{sec.title}</p>
                    <div className="flex items-center gap-2 mt-0.5 text-[10px] text-surface-400">
                      {hasLecture && <span className="text-blue-400 flex items-center gap-0.5"><BookOpen size={9} />讲义</span>}
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

      {/* ══ 中：讲义 + 小测 ══ */}
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
                  <button onClick={() => { setLecture(prevLecture); setPrevLecture(''); }}
                    className="flex items-center gap-1.5 text-xs text-surface-500 hover:text-surface-700 mb-1 transition-colors">
                    <ArrowLeft size={14} />返回讲义
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
                        onClick={() => setContentType(opt.value)}
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
                <button onClick={() => setShowRightPanel(!showRightPanel)}
                  className={`w-8 h-8 rounded-lg border transition-colors flex items-center justify-center ${showRightPanel ? 'bg-violet-50 border-violet-200 text-violet-500' : 'bg-white border-surface-200 text-surface-400 hover:bg-surface-50'}`}
                  title={showRightPanel ? '折叠功能面板' : '展开功能面板'}>
                  <MessageCircle size={14} />
                </button>
                {currentSection && (
                  <>
                    <button onClick={handleQuizGenerate} disabled={quizState === 'generating'}
                      className="flex items-center gap-1.5 px-4 py-2.5 bg-accent-500 text-white rounded-xl text-sm font-semibold hover:bg-accent-600 disabled:opacity-50 transition-all shadow-sm"
                      style={{ backgroundColor: '#14b8a6' }}>
                      <HelpCircle size={14} />{quizState === 'generating' ? '...' : '生成小测'}
                    </button>
                    <button onClick={handleGenerate} disabled={generating || loadingLecture}
                      className="flex items-center gap-1.5 px-4 py-2.5 bg-gradient-to-r from-blue-600 to-violet-600 text-white rounded-xl text-sm font-semibold hover:from-blue-700 hover:to-violet-700 disabled:opacity-50 transition-all shadow-md shadow-blue-200">
                      <Sparkles size={14} />{generating ? 'AI 正在生成…' : lecture ? '重新生成' : '生成讲义'}
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
                      <div className={`mt-4 p-3 rounded-xl ${result.isCorrect ? 'bg-success-50/50 border border-success-200' : 'bg-error-50/50 border border-error-200'}`}>
                        <div className="flex items-center gap-2 mb-1">
                          {result.isCorrect ? <Check className="w-4 h-4 text-success-500" /> : <X className="w-4 h-4 text-error-500" />}
                          <span className={`text-xs font-medium ${result.isCorrect ? 'text-success-600' : 'text-error-600'}`}>{result.isCorrect ? '正确' : '错误'}</span>
                          {result.errorLabel && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-error-100 text-error-600">{result.errorLabel}</span>}
                        </div>
                        {!result.isCorrect && result.correctAnswer && (
                          <p className="text-xs text-surface-600 mt-1">正确答案：<span className="text-success-600 font-medium">{result.correctAnswer}</span></p>
                        )}
                        {result.explanation && <p className="text-xs text-surface-500 mt-1 leading-relaxed">{result.explanation}</p>}
                        {result.feedback && <p className="text-xs text-primary-600 mt-1">💡 {result.feedback}</p>}
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
                <div className="flex justify-end pt-2">
                  <button onClick={() => { setQuizState('idle'); setQuizQuestions([]); setQuizAnswers({}); setQuizResults([]); }}
                    className="px-4 py-2 text-sm text-surface-500 hover:text-surface-700 hover:bg-surface-100 rounded-xl transition-colors">关闭小测</button>
                </div>
              )}
            </div>
          )}

          {/* ── Section content — routed by content_type ── */}
          {quizState !== 'idle' ? null : sectionContent ? (
            <div className="px-5 py-4">
              <SectionContentRouter
                content={sectionContent}
                onComplete={() => {
                  if (currentSection?.id && updateKnowledgePoint) {
                    (currentSection.knowledgePoints || []).forEach((kp: any) => {
                      updateKnowledgePoint(kp.id || kp.name, { status: 'mastered' });
                    });
                  }
                  // Emit section_complete with content_type for mode-specific analytics
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
            </div>
          ) : loadingLecture ? (
            <div className="flex items-center justify-center h-full">
              <div className="w-6 h-6 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
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
                <p className="text-sm text-surface-400 mt-1 max-w-xs">点击「生成讲义」，AI 将根据本节知识点创建专属学习材料</p>
              </div>
              <button onClick={handleGenerate} disabled={generating || loadingLecture}
                className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-blue-600 to-violet-600 text-white rounded-xl text-sm font-semibold hover:from-blue-700 hover:to-violet-700 disabled:opacity-50 transition-all shadow-md shadow-blue-200">
                <Sparkles size={15} />{generating ? '生成中…' : '开始生成讲义'}
              </button>
            </div>
          )}
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
            { key: 'generate' as const, label: '生成', icon: <Sparkles size={12} />, color: 'slate' },
            { key: 'resources' as const, label: '资源', icon: <Lightbulb size={12} />, color: 'slate' },
            { key: 'tutor' as const, label: '辅导', icon: <MessageCircle size={12} />, color: 'slate' },
          ]).map(tab => (
            <button key={tab.key} onClick={() => setRightTab(tab.key)}
              className={`flex-1 flex items-center justify-center gap-1 py-2.5 text-[10px] font-medium transition-all border-b-2 ${rightTab === tab.key ? `border-${tab.color}-500 text-${tab.color}-700 bg-${tab.color}-50` : 'border-transparent text-surface-400 hover:text-surface-600'}`}>
              {tab.icon}{tab.label}
            </button>
          ))}
        </div>

        <div className="flex-1 flex flex-col min-h-0 overflow-y-auto">
          {rightTab === 'tutor' && (
            <div className="flex flex-col flex-1 min-h-0">
              {!chatReply && !chatLoading && currentSection && (
                <div className="px-3 py-3 space-y-1.5 flex-shrink-0">
                  <div className="space-y-1.5">
                    <button onClick={() => sendChat(`请详细解释「${currentSection.knowledgePoints?.[0]?.name || '核心概念'}」的含义、原理和应用场景。`, 'concept_explanation')}
                      className="w-full p-2.5 rounded-lg bg-surface-50 hover:bg-surface-100 transition-colors text-left border border-transparent hover:border-surface-200">
                      <span className="text-xs font-medium text-surface-700">概念讲解</span>
                      <p className="text-[10px] text-surface-400 mt-0.5">"{currentSection.knowledgePoints?.[0]?.name || '核心概念'}"的含义与应用</p>
                    </button>
                    <button onClick={() => sendChat('请用图解和文字结合的方式，说明本节的核心知识结构。', 'diagram')}
                      className="w-full p-2.5 rounded-lg bg-surface-50 hover:bg-surface-100 transition-colors text-left border border-transparent hover:border-surface-200">
                      <span className="text-xs font-medium text-surface-700">图解结构</span>
                      <p className="text-[10px] text-surface-400 mt-0.5">Mermaid 知识结构图 + 文字梳理</p>
                    </button>
                    <button onClick={handleGenerateVideo} disabled={videoGenerating}
                      className="w-full p-2.5 rounded-lg bg-surface-50 hover:bg-surface-100 transition-colors text-left border border-transparent hover:border-surface-200 disabled:opacity-50">
                      <span className="text-xs font-medium text-surface-700">讲解视频</span>
                      <p className="text-[10px] text-surface-400 mt-0.5">{videoGenerating ? '生成中…' : videoResult?.script ? '已生成，点击查看' : '微课视频脚本'}</p>
                    </button>
                  </div>
                </div>
              )}
              <div className="flex-1 overflow-y-auto px-3 min-h-0">
                {chatReply ? (
                  <div className="text-xs surface-600 leading-relaxed"><Markdown content={chatReply} /></div>
                ) : !chatLoading && (
                  <p className="text-[11px] text-surface-400 px-1">点击快捷提问或输入问题，AI 结合讲义和知识点为你解答</p>
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
                lectureContent={lecture}
                sections={sections}
                legacyMindmapId={chapterCtx?.chapter.mindmapId}
              />
              <div className="mx-4 mb-4 p-3 rounded-xl bg-surface-50 border border-surface-100">
                <p className="text-[10px] font-medium text-surface-400 uppercase tracking-wide mb-2">讲义状态</p>
                {lecture ? (
                  <p className="text-xs text-emerald-600 flex items-center gap-1.5"><CheckCircle2 size={13} />已生成</p>
                ) : (
                  <p className="text-xs text-surface-400">选择小节后点击「生成讲义」</p>
                )}
              </div>
              <div className="mx-4 mb-4 p-3 rounded-xl bg-surface-50 border border-surface-100">
                <p className="text-[10px] font-medium text-surface-400 uppercase tracking-wide mb-2">章节统计</p>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="text-center p-2 bg-white rounded-lg"><p className="font-bold text-surface-700">{sections.length}</p><p className="text-[10px] text-surface-400">小节</p></div>
                  <div className="text-center p-2 bg-white rounded-lg"><p className="font-bold text-surface-700">{totalKps}</p><p className="text-[10px] text-surface-400">知识点</p></div>
                  <div className="text-center p-2 bg-white rounded-lg"><p className="font-bold text-surface-700">{masteredKps}</p><p className="text-[10px] text-surface-400">已掌握</p></div>
                  <div className="text-center p-2 bg-white rounded-lg"><p className="font-bold text-surface-700">{Math.round(totalMin / 60)}h</p><p className="text-[10px] text-surface-400">总时长</p></div>
                </div>
              </div>
            </div>
          )}

          {rightTab === 'generate' && (
            <GeneratePanel
              sessionId={sessionId || ''}
              activeSectionId={activeSectionId}
              currentSection={currentSection}
              chapterCtx={chapterCtx}
              path={path}
              lecture={lecture}
              generating={generating}
              genAll={genAll}
              onViewContent={(c: any) => {
                if (!c?.content && c?.type !== 'mindmap') return;
                setPrevLecture(lecture);
                if (c.type === 'mindmap') {
                  setLecture('```mermaid\n' + c.content + '\n```');
                } else {
                  setLecture(c.content);
                }
              }}
              onGenerateLecture={handleGenerate}
              onGenerateQuiz={handleQuizGenerate}
              onGenerateVideo={handleGenerateVideo}
              onGenerateReading={async () => {
                if (!activeSectionId || !sessionId || !currentSection) return;
                try { await fetch(`/api/sections/${encodeURIComponent(activeSectionId)}/lecture/generate`, {
                  method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ sessionId, sectionTitle: currentSection.title, sectionGoal: currentSection.goal, type: 'reading', knowledgePoints: currentSection.knowledgePoints || [] }),
                }); } catch {}
              }}
              onGeneratePractice={async () => {
                if (!activeSectionId || !sessionId || !currentSection) return;
                try { await fetch(`/api/sections/${encodeURIComponent(activeSectionId)}/lecture/generate`, {
                  method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ sessionId, sectionTitle: currentSection.title, sectionGoal: currentSection.goal, type: 'practice', knowledgePoints: currentSection.knowledgePoints || [] }),
                }); } catch {}
              }}
              onGenerateAll={async () => {
                if (!currentSection || !sessionId) return;
                setGenAll(true);
                try {
                  const res = await fetch(`/api/sections/${encodeURIComponent(activeSectionId)}/generate-all`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sessionId, sectionTitle: currentSection.title, sectionGoal: currentSection.goal || '', chapterId: chapterCtx?.chapter.id || '', stageId: chapterCtx?.stage.id || '', knowledgePoints: currentSection.knowledgePoints || [] }),
                  }).then(r => r.json());
                  const data = res?.data || res;
                  if (data?.lecture_content) setLecture(data.lecture_content);
                } catch {} finally { setGenAll(false); }
              }}
            />
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
    </div>
  );
}
