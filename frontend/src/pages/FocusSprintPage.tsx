import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLearningPath } from '../hooks/useLearningPath';
import { useChatStore } from '../store/chatStore';
import { useLectureStore } from '../store/lectureStore';
import {
  ArrowLeft, Zap, Target, Trophy, CheckCircle2, Sparkles,
  ChevronRight, HelpCircle, RefreshCw, MessageCircle, Lightbulb, Send
} from 'lucide-react';
import Markdown from '../utils/markdown';
import SectionContentRouter, { type SectionContent } from '../components/learning/SectionContentRouter';
import SectionResourceWorkspace from '../components/learning/SectionResourceWorkspace';
import { generateSectionQuiz, submitQuizAttempt } from '../api/assessment';
import { logStudyEvent } from '../api/feedback';
import { focusQuickActions, type ActionItem } from '../utils/adaptiveActions';
import type { Section, LearningStage } from '../types/learningPath';
import type { LinkedQuestion, QuizResult } from '../types/assessment';

// ══════════════════════════════════════════════════════════════════════
// Types
// ══════════════════════════════════════════════════════════════════════

interface Props {
  sectionId?: string;
  onBack: () => void;
}

type SprintStatus = 'locked' | 'active' | 'mastered';

interface SprintInfo {
  stage: LearningStage;
  index: number;
  status: SprintStatus;
  focus: string;
  reason: string;
  sections: Section[];
  completed: number;
  total: number;
  pct: number;
}

// ══════════════════════════════════════════════════════════════════════
// Helpers
// ══════════════════════════════════════════════════════════════════════

function collectSprints(stages: LearningStage[]): SprintInfo[] {
  return stages.map((s, i) => {
    const sections = (s.chapters || []).flatMap(ch => ch.sections || []) as Section[];
    const done = sections.filter(sec => sec.status === 'mastered').length;
    const pct = sections.length > 0 ? Math.round((done / sections.length) * 100) : 0;
    let status: SprintStatus = 'locked';
    if (i === 0 || stages[i - 1]?.chapters?.every(ch =>
      (ch.sections || []).every(sec => sec.status === 'mastered')
    )) {
      status = pct === 100 ? 'mastered' : 'active';
    }
    return {
      stage: s, index: i, status,
      focus: (s as any).focus || '',
      reason: (s as any).reason || '',
      sections, completed: done, total: sections.length, pct,
    };
  });
}

// ══════════════════════════════════════════════════════════════════════
// Sprint sidebar — weak point list with status
// ══════════════════════════════════════════════════════════════════════

function SprintSidebar({ sprints, activeIdx, onSelect }: {
  sprints: SprintInfo[]; activeIdx: number; onSelect: (idx: number) => void;
}) {
  const totalDone = sprints.filter(s => s.status === 'mastered').length;

  return (
    <div className="bg-white rounded-2xl shadow-soft overflow-hidden">
      <div className="bg-gradient-to-br from-amber-500 to-orange-500 px-4 py-3">
        <p className="text-sm font-bold text-white font-display">精进突破</p>
        <p className="text-white/70 text-[10px] mt-0.5">{totalDone}/{sprints.length} 已攻克</p>
        <div className="mt-2 h-1.5 bg-white/20 rounded-full overflow-hidden">
          <div className="h-full bg-white rounded-full transition-all duration-700"
            style={{ width: `${sprints.length > 0 ? (totalDone / sprints.length) * 100 : 0}%` }} />
        </div>
      </div>
      <div className="divide-y divide-surface-100 max-h-[500px] overflow-y-auto">
        {sprints.map(sp => {
          const isActive = sp.index === activeIdx;
          return (
            <button
              key={sp.stage.id || sp.index}
              onClick={() => sp.status !== 'locked' && onSelect(sp.index)}
              disabled={sp.status === 'locked'}
              className={`w-full flex items-start gap-3 px-4 py-3 text-left transition-colors
                ${sp.status === 'locked' ? 'opacity-40 cursor-not-allowed' :
                  isActive ? 'bg-amber-50' : 'hover:bg-surface-50'}`}
            >
              <div className={`w-7 h-7 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5
                ${sp.status === 'mastered' ? 'bg-emerald-100 text-emerald-600' :
                  isActive ? 'bg-amber-200 text-amber-700' :
                  'bg-surface-100 text-surface-400'}`}>
                {sp.status === 'mastered' ? <CheckCircle2 size={14} /> :
                  <span className="text-[10px] font-bold">{sp.index + 1}</span>}
              </div>
              <div className="flex-1 min-w-0">
                <p className={`text-xs font-semibold truncate ${isActive ? 'text-amber-800' : 'text-surface-700'}`}>
                  {sp.stage.title}
                </p>
                {sp.focus && (
                  <p className="text-[10px] text-surface-400 mt-0.5 flex items-center gap-1">
                    <Target size={9} />{sp.focus}
                  </p>
                )}
                <div className="flex items-center gap-2 mt-1.5">
                  <div className="flex-1 h-1 bg-surface-100 rounded-full overflow-hidden">
                    <div className="h-full bg-amber-400 rounded-full transition-all"
                      style={{ width: `${sp.pct}%` }} />
                  </div>
                  <span className="text-[9px] text-surface-400 tabular-nums">{sp.completed}/{sp.total}</span>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// Sprint header — focus area + progress
// ══════════════════════════════════════════════════════════════════════

function SprintHeader({ sprint }: { sprint: SprintInfo }) {
  return (
    <div className="bg-white rounded-2xl shadow-soft p-5 mb-5 animate-fade-in">
      <div className="flex items-start gap-4">
        <div className={`w-14 h-14 rounded-2xl flex items-center justify-center flex-shrink-0 shadow-lg
          ${sprint.status === 'mastered'
            ? 'bg-gradient-to-br from-emerald-400 to-emerald-500 shadow-emerald-500/20'
            : 'bg-gradient-to-br from-amber-500 to-orange-500 shadow-amber-500/20'}`}>
          {sprint.status === 'mastered' ? <Trophy size={24} className="text-white" /> : <Zap size={24} className="text-white" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="px-2.5 py-0.5 rounded-lg bg-surface-100 text-[10px] font-bold text-surface-500">
              冲刺 {sprint.index + 1}/{sprint.completed + (sprint.status === 'mastered' ? 0 : 1)}
            </span>
            {sprint.status === 'active' && (
              <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 text-[10px] font-bold animate-pulse">进行中</span>
            )}
            {sprint.status === 'mastered' && (
              <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-[10px] font-bold">
                <CheckCircle2 size={9} className="inline mr-0.5" />已攻克
              </span>
            )}
          </div>
          <h2 className="text-lg font-bold text-surface-900 font-display">{sprint.stage.title}</h2>
          {sprint.focus && (
            <p className="text-sm text-surface-500 mt-1 flex items-center gap-1.5">
              <Target size={13} className="text-amber-500 flex-shrink-0" />攻克薄弱点：{sprint.focus}
            </p>
          )}
          {sprint.reason && (
            <p className="text-xs text-surface-400 mt-1">{sprint.reason}</p>
          )}
        </div>
        <div className="text-right flex-shrink-0">
          <div className="text-3xl font-bold text-surface-800 font-display">{sprint.pct}%</div>
          <p className="text-xs text-surface-400">{sprint.completed}/{sprint.total} 项</p>
        </div>
      </div>
      <div className="mt-3 h-2 bg-surface-100 rounded-full overflow-hidden">
        <div className="h-full bg-gradient-to-r from-amber-500 to-orange-500 rounded-full transition-all duration-700"
          style={{ width: `${sprint.pct}%` }} />
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// Quick quiz panel — generate + answer inline
// ══════════════════════════════════════════════════════════════════════

function QuickQuiz({ sectionId, section, sessionId, lecture }: {
  sectionId: string; section?: Section; sessionId: string; lecture: string;
}) {
  const [questions, setQuestions] = useState<LinkedQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [results, setResults] = useState<QuizResult[]>([]);
  const [generating, setGenerating] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const generate = useCallback(async () => {
    setGenerating(true); setQuestions([]); setAnswers({}); setResults([]); setSubmitted(false);
    try {
      const kps = (section?.knowledgePoints || []).map((kp: any) => kp.name || kp).filter(Boolean);
      const res: any = await generateSectionQuiz(sectionId, {
        sessionId, title: section?.title || '练习', knowledgePoints: kps.slice(0, 5),
        lectureSummary: lecture.slice(0, 1500), difficulty: 'medium',
        pathId: '', stageId: '', chapterId: '', sectionId, requirements: '',
      });
      const data = res?.data || res;
      if (data?.questions) setQuestions(data.questions);
    } catch { /* fail silently */ }
    finally { setGenerating(false); }
  }, [sectionId, section, sessionId, lecture]);

  const submit = useCallback(async () => {
    if (questions.length === 0) return;
    try {
      const res: any = await submitQuizAttempt(sectionId, {
        sessionId,
        answers: questions.map(q => ({ questionId: q.questionId, answer: answers[q.questionId] || '' })),
      });
      const data = res?.data || res;
      if (data?.results) { setResults(data.results); setSubmitted(true); }
    } catch { /* fail silently */ }
  }, [questions, answers, sessionId, sectionId]);

  const score = results.filter(r => r.isCorrect).length;
  const mastered = score === questions.length && questions.length > 0;

  return (
    <div className="bg-white rounded-2xl shadow-soft p-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-bold text-surface-700 font-display flex items-center gap-1.5">
          <HelpCircle size={14} className="text-amber-500" />知识检验
        </h4>
        {submitted && (
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold
            ${mastered ? 'bg-emerald-100 text-emerald-600' : 'bg-amber-100 text-amber-600'}`}>
            {score}/{questions.length} 正确
          </span>
        )}
      </div>

      {generating ? (
        <div className="flex items-center gap-2 text-xs text-surface-400 py-4">
          <div className="w-3 h-3 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />生成题目中…
        </div>
      ) : questions.length === 0 ? (
        <button onClick={generate}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-amber-50 border border-amber-200
            text-amber-700 text-xs font-semibold hover:bg-amber-100 active:scale-[0.98] transition-all">
          <Zap size={13} />生成针对性练习
        </button>
      ) : (
        <div className="space-y-3 max-h-[400px] overflow-y-auto">
          {questions.map((q, qi) => {
            const result = results.find(r => r.questionId === q.questionId);
            return (
              <div key={q.questionId} className="p-3 rounded-xl bg-surface-50 border border-surface-200">
                <p className="text-xs font-medium text-surface-700 mb-2">
                  <span className="text-amber-500 font-bold mr-1">Q{qi + 1}.</span>
                  <Markdown content={q.stem} />
                </p>
                {q.type === 'choice' && q.options && (
                  <div className="space-y-1">
                    {q.options.map((opt: string, oi: number) => {
                      const letter = String.fromCharCode(65 + oi);
                      const sel = answers[q.questionId] === letter;
                      const correct = result?.correctAnswer === letter;
                      let cls = 'border px-3 py-1.5 rounded-lg text-[10px] transition-all ';
                      if (submitted && correct) cls += 'border-emerald-300 bg-emerald-50 text-emerald-700';
                      else if (submitted && sel && !result?.isCorrect) cls += 'border-red-300 bg-red-50 text-red-700';
                      else if (sel && !submitted) cls += 'border-amber-300 bg-amber-50 text-amber-700';
                      else cls += 'border-surface-200 hover:border-surface-300 text-surface-600';
                      return (
                        <button key={letter} disabled={submitted}
                          onClick={() => setAnswers(a => ({ ...a, [q.questionId]: letter }))}
                          className={cls}>{letter}. {opt}</button>
                      );
                    })}
                  </div>
                )}
                {(q.type === 'fill' || q.type === 'shortanswer') && (
                  <textarea value={answers[q.questionId] || ''} disabled={submitted}
                    onChange={e => setAnswers(a => ({ ...a, [q.questionId]: e.target.value }))}
                    rows={2} placeholder="输入答案…" className="w-full px-3 py-2 bg-white border border-surface-200 rounded-lg text-[10px] resize-none disabled:opacity-50" />
                )}
                {result && (
                  <div className={`mt-2 text-[10px] ${result.isCorrect ? 'text-emerald-600' : 'text-red-500'}`}>
                    {result.isCorrect ? '✓ 正确' : `✗ 正确答案：${result.correctAnswer}`}
                    {result.explanation && <span className="text-surface-400 ml-1">— {result.explanation}</span>}
                  </div>
                )}
              </div>
            );
          })}
          {!submitted ? (
            <button onClick={submit}
              disabled={questions.some(q => !answers[q.questionId]?.trim())}
              className="w-full py-2.5 bg-amber-500 text-white rounded-xl text-xs font-semibold hover:bg-amber-600 disabled:opacity-40 transition-all active:scale-[0.98]">
              提交检验
            </button>
          ) : (
            <button onClick={generate}
              className="w-full flex items-center justify-center gap-1.5 py-2.5 bg-surface-100 text-surface-600 rounded-xl text-xs font-medium hover:bg-surface-200 transition-all">
              <RefreshCw size={12} />{mastered ? '重新练习' : '再来一组'}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// Right panel with tabs: practice / tutor / resources / generate
// ══════════════════════════════════════════════════════════════════════

function SprintToolsPanel({ sessionId, sectionId, section, lecture, sections, pathId, chapterTitle }: {
  sessionId: string; sectionId: string; section: Section;
  lecture: string; sections: Section[]; pathId: string; chapterTitle: string;
}) {
  const [tab, setTab] = useState<'tool' | 'practice' | 'tutor' | 'resources'>('tool');
  const [tutorPrompt, setTutorPrompt] = useState('');
  const [generating, setGenerating] = useState<string | null>(null);
  const store = useLectureStore();

  const actions = useMemo(() =>
    focusQuickActions(section.knowledgePoints?.[0]?.name || section.title, section.title),
  [section]);

  const handleAction = async (action: ActionItem) => {
    if (action.tutorPrompt) { setTutorPrompt(action.tutorPrompt); setTab('tutor'); return; }
    if (!action.genType) return;
    if (generating) return;
    setGenerating(action.key);
    try {
      const body: Record<string, any> = {
        sessionId, sectionTitle: section.title, sectionGoal: section.goal || '',
        knowledgePoints: section.knowledgePoints || [],
        lectureContent: lecture.slice(0, 3000),
        type: action.genType,
        requirements: '这是精进突破模式，请生成简洁、直击重点的内容。',
      };
      const res = await fetch(`/api/sections/${encodeURIComponent(sectionId)}/lecture/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data?.data?.lecture?.content) {
        store.setLecture(`${sessionId}:${sectionId}`, data.data.lecture.content);
        store.markGenerated(sectionId);
      }
    } catch { /* ok */ }
    finally { setGenerating(null); }
  };

  return (
    <div className="w-60 lg:w-64 xl:w-72 bg-white border-l border-surface-200 flex flex-col flex-shrink-0 overflow-hidden">
      <div className="flex border-b border-surface-200 flex-shrink-0">
        {[
          { key: 'tool' as const, label: '工具', icon: <Zap size={12} /> },
          { key: 'practice' as const, label: '检验', icon: <HelpCircle size={12} /> },
          { key: 'tutor' as const, label: '辅导', icon: <MessageCircle size={12} /> },
          { key: 'resources' as const, label: '资源', icon: <Lightbulb size={12} /> },
        ].map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`flex-1 flex items-center justify-center gap-1 py-2.5 text-[10px] font-medium transition-all border-b-2
              ${tab === t.key ? 'border-amber-500 text-amber-700 bg-amber-50' : 'border-transparent text-surface-400 hover:text-surface-600'}`}>
            {t.icon}{t.label}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto min-h-0">
        {tab === 'tool' && (
          <div className="p-3 space-y-1.5">
            <p className="text-[10px] font-semibold text-surface-400 uppercase tracking-wider px-1">快捷操作</p>
            {actions.map(a => (
              <button key={a.key} onClick={() => handleAction(a)} disabled={!!generating}
                className="w-full flex items-start gap-2.5 p-2.5 rounded-xl bg-surface-50 hover:bg-white hover:border-surface-200 border border-transparent active:scale-[0.98] transition-all disabled:opacity-50">
                <span className="text-sm flex-shrink-0">{a.icon}</span>
                <div className="text-left min-w-0">
                  <p className="text-[11px] font-medium text-surface-700">{a.label}</p>
                  <p className="text-[10px] text-surface-400">{a.desc}</p>
                </div>
                {generating === a.key && (
                  <div className="w-3.5 h-3.5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin flex-shrink-0 ml-auto" />
                )}
              </button>
            ))}
          </div>
        )}
        {tab === 'practice' && (
          <div className="p-3">
            <QuickQuiz sectionId={sectionId} section={section} sessionId={sessionId} lecture={lecture} />
          </div>
        )}
        {tab === 'tutor' && section && (
          <div className="flex flex-col h-full p-3">
            <MiniSprintTutor sessionId={sessionId} section={section} lecture={lecture} initialPrompt={tutorPrompt} />
          </div>
        )}
        {tab === 'resources' && (
          <SectionResourceWorkspace
            sessionId={sessionId} pathId={pathId} stageId="" chapterId=""
            chapterTitle={chapterTitle} section={section}
            lectureContent={lecture} sections={sections}
          />
        )}
      </div>
    </div>
  );
}

function MiniSprintTutor({ sessionId, section, lecture, initialPrompt }: {
  sessionId: string; section: Section; lecture: string;
  initialPrompt?: string;
}) {
  const [msg, setMsg] = useState('');
  const [reply, setReply] = useState('');
  const [loading, setLoading] = useState(false);
  const promptedRef = useRef(false);

  useEffect(() => {
    if (initialPrompt && initialPrompt.trim() && !promptedRef.current) {
      promptedRef.current = true;
      ask(initialPrompt);
    }
  }, [initialPrompt]);

  const ask = useCallback(async (question: string) => {
    if (!question.trim()) return;
    setMsg(''); setLoading(true); setReply('');
    try {
      const res = await fetch(`/api/sections/${encodeURIComponent(section.id)}/tutor/ask`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sessionId, question,
          sectionTitle: section.title, sectionGoal: section.goal || '',
          knowledgePoints: section.knowledgePoints || [],
          lectureExcerpt: lecture.slice(0, 1000),
        }),
      });
      const data = await res.json();
      setReply(data?.data?.reply || '暂时无法回答。');
    } catch { setReply('出错了。');
    } finally { setLoading(false); }
  }, [sessionId, section, lecture]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto min-h-0">
        {reply ? (
          <div className="text-xs text-surface-600 leading-relaxed">
            <Markdown content={reply} />
            <button onClick={() => { setReply(''); promptedRef.current = false; }} className="text-[10px] text-surface-400 hover:text-surface-600 mt-1">清除</button>
          </div>
        ) : (
          <div className="space-y-1.5">
            <p className="text-[11px] text-surface-400">针对当前薄弱点提问：</p>
            {[
              { label: '讲解核心概念', q: `请讲解「${section.knowledgePoints?.[0]?.name || section.title}」的核心要点` },
              { label: '常见错误分析', q: `在学习「${section.title}」时，学生常犯哪些错误？怎么避免？` },
              { label: '解题技巧', q: `关于「${section.title}」，有哪些高效的解题技巧？` },
            ].map((sq, i) => (
              <button key={i} onClick={() => ask(sq.q)}
                className="w-full text-left px-3 py-2 rounded-xl bg-surface-50 hover:bg-surface-100 border border-transparent hover:border-surface-200 text-[10px] text-surface-600 transition-all">
                {sq.label}
              </button>
            ))}
          </div>
        )}
        {loading && (
          <div className="flex items-center gap-2 text-xs text-surface-400 mt-2">
            <div className="w-3 h-3 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />思考中…
          </div>
        )}
      </div>
      <div className="flex gap-1.5 pt-2 border-t border-surface-100 mt-2">
        <input value={msg} onChange={e => setMsg(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') ask(msg); }}
          placeholder="问 AI…" className="flex-1 px-3 py-2 bg-surface-50 border border-surface-200 rounded-lg text-xs focus:outline-none focus:border-amber-300" />
        <button onClick={() => ask(msg)} disabled={loading}
          className="px-3 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 disabled:opacity-50">
          <Send size={13} />
        </button>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// FocusSprintPage — main component
// ══════════════════════════════════════════════════════════════════════

export default function FocusSprintPage({ sectionId, onBack }: Props) {
  const nav = useNavigate();
  const { path, updateKnowledgePoint } = useLearningPath();
  const sessionId = useChatStore(s => s.dataSessionId) || '';
  const store = useLectureStore();

  const sprints = useMemo(() =>
    path?.stages ? collectSprints(path.stages) : [],
  [path]);

  const activeSprintIdx = useMemo(() => {
    if (!sectionId) {
      const firstActive = sprints.findIndex(s => s.status === 'active');
      return firstActive >= 0 ? firstActive : 0;
    }
    const idx = sprints.findIndex(s => s.sections.some(sec => sec.id === sectionId));
    return idx >= 0 ? idx : 0;
  }, [sprints, sectionId]);

  const activeSprint = sprints[activeSprintIdx];
  const sections = activeSprint?.sections || [];
  const activeSectionIdx = useMemo(() => {
    if (!sectionId) return 0;
    const idx = sections.findIndex(s => s.id === sectionId);
    return idx >= 0 ? idx : 0;
  }, [sections, sectionId]);
  const currentSection = sections[activeSectionIdx];

  const cacheKey = `${sessionId}:${currentSection?.id || sectionId}`;
  const lecture = store.lectureCache[cacheKey] || '';
  const [lectureLoaded, setLectureLoaded] = useState(false);
  const autoGenRef = useRef(false);

  useEffect(() => {
    if (!currentSection?.id || !sessionId) return;
    const key = `${sessionId}:${currentSection.id}`;
    if (store.lectureCache[key]) { setLectureLoaded(true); return; }
    setLectureLoaded(false);
    autoGenRef.current = false;
    fetch(`/api/sections/${encodeURIComponent(currentSection.id)}/lecture?sessionId=${encodeURIComponent(sessionId)}`)
      .then(r => r.json())
      .then(d => {
        store.markLoaded(currentSection.id);
        if (d?.data?.lecture?.content) {
          store.setLecture(key, d.data.lecture.content);
          store.markGenerated(currentSection.id);
        }
      })
      .catch(() => store.markLoaded(currentSection.id))
      .finally(() => setLectureLoaded(true));
  }, [currentSection?.id, sessionId]);

  // Auto-generate practice content when first entering a sprint section
  useEffect(() => {
    if (!lectureLoaded || !currentSection || !sessionId) return;
    const key = `${sessionId}:${currentSection.id}`;
    if (store.lectureCache[key] || autoGenRef.current) return;
    autoGenRef.current = true;
    const timer = setTimeout(() => handleGenerate(), 400);
    return () => clearTimeout(timer);
  }, [lectureLoaded, currentSection?.id, sessionId]);

  const sectionContent: SectionContent | null = useMemo(() => {
    if (!lecture || !currentSection) return null;
    return {
      contentType: 'lecture',
      title: currentSection.title,
      goal: currentSection.goal || '',
      content: lecture,
      knowledgePoints: (currentSection.knowledgePoints || []).map((kp: any) =>
        typeof kp === 'string' ? { name: kp } : { name: kp.name, type: kp.type }
      ),
    };
  }, [lecture, currentSection]);

  const [generating, setGenerating] = useState(false);
  const handleGenerate = useCallback(async () => {
    if (!currentSection || !sessionId) return;
    setGenerating(true);
    try {
      const res = await fetch(`/api/sections/${encodeURIComponent(currentSection.id)}/lecture/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sessionId, sectionTitle: currentSection.title, sectionGoal: currentSection.goal || '',
          courseId: path?.courseName || '', knowledgePoints: currentSection.knowledgePoints || [],
          requirements: '这是精进突破模式的一道练习任务，请生成简洁、直击重点的内容，侧重要点和练习。',
        }),
      });
      const data = await res.json();
      if (data?.data?.lecture?.content) {
        store.setLecture(`${sessionId}:${currentSection.id}`, data.data.lecture.content);
        store.markGenerated(currentSection.id);
      }
    } catch { /* ok */ }
    finally { setGenerating(false); }
  }, [currentSection, sessionId, path?.courseName]);

  const handleMaster = useCallback(async () => {
    if (!currentSection) return;
    (currentSection.knowledgePoints || []).forEach((kp: any) => {
      updateKnowledgePoint(kp.id || kp.name, { status: 'mastered' });
    });
    logStudyEvent({
      sessionId, event: 'sprint_section_mastered',
      resourceId: currentSection.id,
      metadata: { title: currentSection.title, sprint_idx: activeSprintIdx },
    }).catch(() => {});
    const next = sections.find((s, i) => i > activeSectionIdx && s.status !== 'mastered');
    if (next) nav(`/lecture/section/${encodeURIComponent(next.id)}`);
  }, [currentSection, sections, activeSectionIdx, activeSprintIdx, sessionId, updateKnowledgePoint, nav]);

  const goToSection = useCallback((secId: string) => {
    nav(`/lecture/section/${encodeURIComponent(secId)}`);
  }, [nav]);

  const goToSprint = useCallback((idx: number) => {
    const s = sprints[idx];
    if (s?.sections[0]) nav(`/lecture/section/${encodeURIComponent(s.sections[0].id)}`);
  }, [sprints, nav]);

  if (!activeSprint) {
    return (
      <div className="flex items-center justify-center h-screen -m-6 bg-surface-50/50">
        <div className="text-center">
          <Zap size={48} className="text-surface-300 mx-auto mb-4" />
          <p className="text-surface-500">暂无精进突破计划</p>
          <button onClick={onBack} className="mt-4 text-sm text-blue-500 hover:text-blue-600">返回学习路径</button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen -m-6 bg-surface-50/50">
      {/* ══ Left: sprint sidebar ══ */}
      <div className="w-52 lg:w-56 xl:w-60 bg-white border-r border-surface-200 flex flex-col flex-shrink-0 overflow-y-auto">
        <div className="p-4 border-b border-surface-100">
          <button onClick={onBack}
            className="flex items-center gap-1.5 text-xs text-surface-500 hover:text-amber-600 rounded-lg px-2 py-1 -ml-2 mb-3 transition-colors">
            <ArrowLeft size={14} />返回路径
          </button>
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-100 text-amber-700 text-[10px] font-bold">
            🎯 精进式
          </div>
        </div>
        <div className="flex-1 px-3 py-3">
          <SprintSidebar sprints={sprints} activeIdx={activeSprintIdx} onSelect={goToSprint} />
        </div>
      </div>

      {/* ══ Center: content + practice ══ */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 overflow-y-auto">
          <div className="p-6 max-w-3xl mx-auto">
            <SprintHeader sprint={activeSprint} />

            {/* Section nav */}
            {sections.length > 1 && (
              <div className="flex items-center gap-1 mb-4">
                {sections.map((sec, i) => {
                  const isActive = i === activeSectionIdx;
                  const isDone = sec.status === 'mastered';
                  return (
                    <button key={sec.id} onClick={() => goToSection(sec.id)}
                      className={`flex-1 text-center px-2 py-1.5 rounded-lg text-[10px] font-medium transition-all
                        ${isActive ? 'bg-amber-100 text-amber-700' :
                          isDone ? 'bg-emerald-50 text-emerald-600' :
                          'bg-surface-50 text-surface-400 hover:bg-surface-100'}`}>
                      {isDone && <CheckCircle2 size={9} className="inline mr-0.5" />}
                      {sec.title.slice(0, 12)}
                    </button>
                  );
                })}
              </div>
            )}

            {/* Content */}
            {lecture ? (
              sectionContent && <SectionContentRouter content={sectionContent} />
            ) : lectureLoaded ? (
              <div className="bg-white rounded-2xl shadow-soft p-10 text-center">
                <Target size={40} className="text-surface-300 mx-auto mb-3" />
                <p className="text-surface-500 text-sm mb-4">生成针对此薄弱点的练习内容</p>
                <button onClick={handleGenerate} disabled={generating}
                  className="inline-flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-amber-500 to-orange-500 text-white rounded-xl text-sm font-semibold hover:from-amber-600 hover:to-orange-600 disabled:opacity-50 transition-all shadow-md shadow-amber-500/20">
                  <Sparkles size={15} />{generating ? '生成中…' : '生成练习'}
                </button>
              </div>
            ) : (
              <div className="flex items-center justify-center h-64">
                <div className="w-6 h-6 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
              </div>
            )}

            {/* Bottom action */}
            {currentSection && lecture && (
              <div className="mt-6 flex items-center justify-center gap-3">
                {activeSectionIdx > 0 && (
                  <button onClick={() => goToSection(sections[activeSectionIdx - 1].id)}
                    className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium text-surface-500 hover:bg-surface-100 rounded-xl transition-all">
                    <ArrowLeft size={13} />上一项
                  </button>
                )}
                <button onClick={handleMaster}
                  className="flex items-center gap-1.5 px-6 py-2.5 bg-gradient-to-r from-emerald-500 to-emerald-600 text-white rounded-xl text-xs font-semibold hover:from-emerald-600 hover:to-emerald-700 shadow-md shadow-emerald-500/20 active:scale-[0.98] transition-all">
                  <CheckCircle2 size={14} />标记掌握
                </button>
                {activeSectionIdx < sections.length - 1 && (
                  <button onClick={() => goToSection(sections[activeSectionIdx + 1].id)}
                    className="flex items-center gap-1 px-4 py-2 text-xs font-medium text-surface-500 hover:bg-surface-100 rounded-xl transition-all">
                    下一项<ChevronRight size={13} />
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ══ Right: tools panel ══ */}
      {currentSection && (
        <SprintToolsPanel
          sessionId={sessionId}
          sectionId={currentSection.id}
          section={currentSection}
          lecture={lecture}
          sections={sections}
          pathId={path?.id || ''}
          chapterTitle={activeSprint.stage.title}
        />
      )}
      {!currentSection && (
        <div className="w-60 lg:w-64 xl:w-72 bg-white border-l border-surface-200 flex items-center justify-center">
          <p className="text-xs text-surface-400">选择练习项后可用</p>
        </div>
      )}
    </div>
  );
}
