import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { authHeaders } from '../api/client';
import { useNavigate } from 'react-router-dom';
import { useLearningPath } from '../hooks/useLearningPath';
import { useChatStore } from '../store/chatStore';
import { useLectureStore, type LectureStore } from '../store/lectureStore';
import {
  ArrowLeft, CheckCircle2, Sparkles, Send, ChevronRight,
  Trophy, Zap, Play, Pause, RotateCcw, MessageCircle, Lightbulb, BookOpen
} from 'lucide-react';
import Markdown from '../utils/markdown';
import SectionContentRouter, { type SectionContent } from '../components/learning/SectionContentRouter';
import SectionResourceWorkspace from '../components/learning/SectionResourceWorkspace';
import { DailyTaskHeader, getDefaultContentType, getTaskMeta } from '../components/learning/DailyTaskView';
import { dailyQuickActions, type ActionItem } from '../utils/adaptiveActions';
import { logStudyEvent } from '../api/feedback';
import type { Section } from '../types/learningPath';

// ══════════════════════════════════════════════════════════════════════
// Types
// ══════════════════════════════════════════════════════════════════════

interface Props {
  chapterId?: string;
  sectionId?: string;
  onBack: () => void;
}

// ══════════════════════════════════════════════════════════════════════
// Study timer — tracks focus time per task
// ══════════════════════════════════════════════════════════════════════

function useTimer() {
  const [seconds, setSeconds] = useState(0);
  const [running, setRunning] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const start = useCallback(() => {
    setRunning(true);
    intervalRef.current = setInterval(() => setSeconds(s => s + 1), 1000);
  }, []);

  const pause = useCallback(() => {
    setRunning(false);
    if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
  }, []);

  const reset = useCallback(() => {
    pause();
    setSeconds(0);
  }, [pause]);

  useEffect(() => () => { if (intervalRef.current) clearInterval(intervalRef.current); }, []);

  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;

  return { mins, secs, running, start, pause, reset, totalSeconds: seconds };
}

// ══════════════════════════════════════════════════════════════════════
// Mini chat (simplified tutor for daily mode)
// ══════════════════════════════════════════════════════════════════════

function MiniTutor({ sessionId, sectionId, section, lecture, initialPrompt }: {
  sessionId: string; sectionId: string; section?: Section; lecture: string;
  initialPrompt?: string;
}) {
  const [msg, setMsg] = useState('');
  const [reply, setReply] = useState('');
  const [loading, setLoading] = useState(false);
  const promptedRef = useRef(false);

  const ask = useCallback(async (question: string) => {
    if (!question.trim()) return;
    setMsg(''); setLoading(true); setReply('');
    try {
      const res = await fetch(`/api/sections/${encodeURIComponent(sectionId)}/tutor/ask`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          sessionId, question,
          sectionTitle: section?.title || '',
          sectionGoal: section?.goal || '',
          knowledgePoints: section?.knowledgePoints || [],
          lectureExcerpt: lecture.slice(0, 1000),
        }),
      });
      const data = await res.json();
      setReply(data?.data?.reply || '暂时无法回答，请稍后再试。');
    } catch { setReply('出错了，请稍后重试。');
    } finally { setLoading(false); }
  }, [sessionId, sectionId, section, lecture]);

  // Auto-send initialPrompt when it changes
  useEffect(() => {
    if (initialPrompt && initialPrompt.trim() && !promptedRef.current) {
      promptedRef.current = true;
      ask(initialPrompt);
    }
  }, [initialPrompt, ask]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto min-h-0">
        {reply ? (
          <div className="text-xs text-surface-600 leading-relaxed">
            <Markdown content={reply} />
            <button onClick={() => { setReply(''); promptedRef.current = false; }}
              className="text-[10px] text-surface-400 hover:text-surface-600 mt-1">清除</button>
          </div>
        ) : (
          <p className="text-[11px] text-surface-400">学习中遇到问题？随时问 AI 助教。</p>
        )}
        {loading && (
          <div className="flex items-center gap-2 text-xs text-surface-400 mt-2">
            <div className="w-3 h-3 border-2 border-surface-300 border-t-transparent rounded-full animate-spin" />思考中…
          </div>
        )}
      </div>
      <div className="flex gap-1.5 pt-2 border-t border-surface-100 mt-2">
        <input value={msg} onChange={e => setMsg(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') ask(msg); }}
          placeholder="问 AI…" className="flex-1 px-3 py-2 bg-surface-50 border border-surface-200 rounded-lg text-xs focus:outline-none focus:border-violet-300" />
        <button onClick={() => ask(msg)} disabled={loading}
          className="px-3 py-2 bg-violet-500 text-white rounded-lg hover:bg-violet-600 disabled:opacity-50">
          <Send size={13} />
        </button>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// DayNavigator — horizontal dot timeline for jumping between days
// ══════════════════════════════════════════════════════════════════════

function DayNavigator({ days, activeDayIdx, onSelectDay }: {
  days: { title: string; taskCount: number; completed: number }[];
  activeDayIdx: number;
  onSelectDay: (idx: number) => void;
}) {
  return (
    <div className="bg-white rounded-2xl shadow-soft p-4 mb-5">
      <div className="flex items-center gap-3 overflow-x-auto pb-1">
        {days.map((d, i) => {
          const isActive = i === activeDayIdx;
          const isDone = d.completed === d.taskCount && d.taskCount > 0;
          const isPast = i < activeDayIdx;
          return (
            <button
              key={i}
              onClick={() => onSelectDay(i)}
              className={`flex flex-col items-center gap-1.5 flex-shrink-0 px-3 py-2 rounded-xl transition-all duration-200 min-w-[64px]
                ${isActive ? 'bg-blue-50 ring-2 ring-blue-200 scale-105' :
                  isDone ? 'bg-emerald-50/50' :
                  isPast ? 'bg-surface-50' : 'bg-white hover:bg-surface-50'}`}
            >
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold
                ${isActive ? 'bg-blue-500 text-white shadow-md shadow-blue-500/30' :
                  isDone ? 'bg-emerald-400 text-white' :
                  isPast ? 'bg-surface-200 text-surface-500' :
                  'bg-surface-100 text-surface-400'}`}>
                {isDone ? <CheckCircle2 size={14} /> : i + 1}
              </div>
              <span className={`text-[10px] font-medium truncate max-w-[60px]
                ${isActive ? 'text-blue-600' : isDone ? 'text-emerald-600' : 'text-surface-400'}`}>
                {d.title}
              </span>
              <span className="text-[9px] text-surface-400">{d.completed}/{d.taskCount}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// Task sidebar — list of today's tasks with status
// ══════════════════════════════════════════════════════════════════════

function TaskSidebar({ tasks, activeIdx, onSelect, onComplete }: {
  tasks: Section[];
  activeIdx: number;
  onSelect: (idx: number) => void;
  onComplete?: () => void;
}) {
  const completed = tasks.filter(t => t.status === 'mastered').length;

  return (
    <div className="bg-white rounded-2xl shadow-soft overflow-hidden">
      <div className="bg-gradient-to-r from-violet-500 to-blue-500 px-4 py-3">
        <p className="text-sm font-bold text-white font-display">今日任务</p>
        <p className="text-white/70 text-[10px] mt-0.5">{completed}/{tasks.length} 已完成</p>
        <div className="mt-2 h-1.5 bg-white/20 rounded-full overflow-hidden">
          <div className="h-full bg-white rounded-full transition-all duration-700"
            style={{ width: `${tasks.length > 0 ? (completed / tasks.length) * 100 : 0}%` }} />
        </div>
      </div>
      <div className="divide-y divide-surface-100 max-h-[400px] overflow-y-auto">
        {tasks.map((t, i) => {
          const isActive = i === activeIdx;
          const isDone = t.status === 'mastered';
          return (
            <button
              key={t.id}
              onClick={() => onSelect(i)}
              className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors
                ${isActive ? 'bg-blue-50' : isDone ? 'bg-emerald-50/30' : 'hover:bg-surface-50'}`}
            >
              <div className={`w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0
                ${isDone ? 'bg-emerald-100 text-emerald-500' :
                  isActive ? 'bg-blue-100 text-blue-500' : 'bg-surface-100 text-surface-400'}`}>
                {isDone ? <CheckCircle2 size={13} /> : <span className="text-[10px] font-bold">{i + 1}</span>}
              </div>
              <div className="flex-1 min-w-0">
                <p className={`text-xs font-medium truncate ${isActive ? 'text-blue-700' : isDone ? 'text-surface-500' : 'text-surface-700'}`}>
                  {t.title}
                </p>
                <span className="text-[10px] text-surface-400">
                  {(t as any).task_type || '任务'} · {t.estimatedMinutes || 30}min
                </span>
              </div>
              {isActive && <ChevronRight size={13} className="text-blue-400 flex-shrink-0" />}
            </button>
          );
        })}
      </div>
      {completed === tasks.length && tasks.length > 0 && (
        <div className="p-4 bg-emerald-50 border-t border-emerald-100 text-center">
          <Trophy size={20} className="text-emerald-500 mx-auto mb-1" />
          <p className="text-sm font-bold text-emerald-700 font-display">全部完成！</p>
          <p className="text-[10px] text-emerald-600">坚持学习，明天继续加油 🔥</p>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// Right panel with tabs: tutor / resources / generate
// ══════════════════════════════════════════════════════════════════════

function DailyToolsPanel({ sessionId, activeSectionId, section, lecture, sections, pathId, chapterTitle, store }: {
  sessionId: string; activeSectionId: string; section?: Section;
  lecture: string; sections: Section[]; pathId: string; chapterTitle: string;
  store: LectureStore;
}) {
  const taskType = (section as any)?.task_type || '';
  const taskMeta = getTaskMeta(taskType);
  const [tab, setTab] = useState<'tool' | 'tutor' | 'resources'>('tool');
  const [tutorPrompt, setTutorPrompt] = useState('');

  const tabs = useMemo(() => [
    { key: 'tool' as const, label: taskMeta?.label || '工具', icon: taskMeta ? <taskMeta.icon size={12} /> : <Sparkles size={12} /> },
    { key: 'tutor' as const, label: '辅导', icon: <MessageCircle size={12} /> },
    { key: 'resources' as const, label: '资源', icon: <Lightbulb size={12} /> },
  ], [taskMeta]);

  const handleTutorPrompt = useCallback((prompt: string) => {
    setTutorPrompt(prompt);
  }, []);

  const handleRegen = useCallback((content: string) => {
    if (content && activeSectionId) {
      store.setLecture(`${sessionId}:${activeSectionId}`, content);
      store.markGenerated(activeSectionId);
    }
  }, [sessionId, activeSectionId, store]);

  return (
    <div className="w-64 lg:w-72 xl:w-80 bg-white border-l border-surface-200 flex flex-col flex-shrink-0 overflow-hidden">
      <div className="flex border-b border-surface-200 flex-shrink-0">
        {tabs.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`flex-1 flex items-center justify-center gap-1 py-2.5 text-[10px] font-medium transition-all border-b-2
              ${tab === t.key ? 'border-violet-500 text-violet-700 bg-violet-50' : 'border-transparent text-surface-400 hover:text-surface-600'}`}>
            {t.icon}{t.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto min-h-0">
        {tab === 'tool' && section && (
          <div className="p-3">
            <AdaptiveToolTab
              sessionId={sessionId}
              sectionId={activeSectionId}
              section={section}
              lecture={lecture}
              onGenerated={handleRegen}
              onTutorPrompt={handleTutorPrompt}
            />
          </div>
        )}
        {tab === 'tutor' && section && (
          <div className="flex flex-col h-full p-3">
            <MiniTutor sessionId={sessionId} sectionId={activeSectionId} section={section} lecture={lecture} initialPrompt={tutorPrompt} />
          </div>
        )}
        {tab === 'resources' && (
          <SectionResourceWorkspace
            sessionId={sessionId}
            pathId={pathId}
            stageId=""
            chapterId=""
            chapterTitle={chapterTitle}
            section={section}
            taskId={activeSectionId}
            lectureContent={lecture}
            sections={sections}
          />
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// Adaptive tool tab — quick actions + generate, all context-aware
// ══════════════════════════════════════════════════════════════════════

function AdaptiveToolTab({ sessionId, sectionId, section, lecture, onGenerated, onTutorPrompt }: {
  sessionId: string; sectionId: string; section: Section; lecture: string;
  onGenerated: (content: string) => void;
  onTutorPrompt: (prompt: string) => void;
}) {
  const [generating, setGenerating] = useState<string | null>(null);
  const taskType = (section as any).task_type || '';
  const course = section.knowledgePoints?.[0]?.name || section.title || '';

  const actions = useMemo(() => {
    return dailyQuickActions(taskType, course, section.title);
  }, [taskType, course, section.title]);

  const handleGen = async (action: ActionItem) => {
    if (action.tutorPrompt) {
      onTutorPrompt(action.tutorPrompt);
      return;
    }
    if (!action.genType) return;
    if (generating) return;
    setGenerating(action.key);
    try {
      const body: Record<string, any> = {
        sessionId, sectionTitle: section.title, sectionGoal: section.goal || '',
        knowledgePoints: section.knowledgePoints || [],
        lectureContent: lecture.slice(0, 3000),
        task_type: taskType,
        type: action.genType,
      };
      const res = await fetch(`/api/sections/${encodeURIComponent(sectionId)}/lecture/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data?.data?.lecture?.content) {
        onGenerated(data.data.lecture.content);
      }
    } catch { /* ok */ }
    finally { setGenerating(null); }
  };

  return (
    <div className="space-y-1.5">
      <p className="text-[10px] font-semibold text-surface-400 uppercase tracking-wider px-1">快捷操作</p>
      {actions.map(a => (
        <button key={a.key} onClick={() => handleGen(a)} disabled={!!generating}
          className="w-full flex items-start gap-2.5 p-2.5 rounded-xl bg-surface-50 hover:bg-white hover:border-surface-200 border border-transparent active:scale-[0.98] transition-all disabled:opacity-50">
          <span className="text-sm flex-shrink-0">{a.icon}</span>
          <div className="text-left min-w-0">
            <p className="text-[11px] font-medium text-surface-700">{a.label}</p>
            <p className="text-[10px] text-surface-400">{a.desc}</p>
          </div>
          {generating === a.key && (
            <div className="w-3.5 h-3.5 border-2 border-violet-400 border-t-transparent rounded-full animate-spin flex-shrink-0 ml-auto" />
          )}
        </button>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// DailyTaskPage — main page component
// ══════════════════════════════════════════════════════════════════════

export default function DailyTaskPage({ chapterId, sectionId, onBack }: Props) {
  const nav = useNavigate();
  const { path, updateKnowledgePoint } = useLearningPath();
  const sessionId = useChatStore(s => s.dataSessionId) || '';
  const store = useLectureStore();
  const timer = useTimer();

  // ── Gather all daily-mode stages → chapters(days) → sections(tasks) ──
  const allDays = useMemo(() => {
    if (!path?.stages) return [] as { weekIdx: number; dayIdx: number; weekTitle: string; dayTitle: string; sections: Section[]; completed: number }[];
    const result: { weekIdx: number; dayIdx: number; weekTitle: string; dayTitle: string; sections: Section[]; completed: number }[] = [];
    let dayCounter = 0;
    for (const stage of path.stages) {
      for (const ch of (stage.chapters || [])) {
        const sections = (ch.sections || []) as Section[];
        result.push({
          weekIdx: result.length,
          dayIdx: dayCounter++,
          weekTitle: stage.title,
          dayTitle: ch.title,
          sections,
          completed: sections.filter((s: Section) => s.status === 'mastered').length,
        });
      }
    }
    return result;
  }, [path]);

  // ── Find which day the current section belongs to ──
  const activeDayIdx = useMemo(() => {
    const idx = allDays.findIndex((d: { sections: Section[] }) => d.sections.some((s: Section) => s.id === sectionId));
    return idx >= 0 ? idx : 0;
  }, [allDays, sectionId]);

  const activeDay = allDays[activeDayIdx];
  const tasks = activeDay?.sections || [];

  // ── Active task ──
  const activeTaskIdx = useMemo(() => {
    if (!sectionId) return 0;
    const idx = tasks.findIndex((t: Section) => t.id === sectionId);
    return idx >= 0 ? idx : 0;
  }, [tasks, sectionId]);

  const currentTask = tasks[activeTaskIdx];
  const cacheKey = `${sessionId}:${currentTask?.id || sectionId}`;

  // ── Content loading + auto-generate if missing ──
  const lecture = store.lectureCache[cacheKey] || '';
  const [lectureLoaded, setLectureLoaded] = useState(false);
  const autoGenRef = useRef(false);

  useEffect(() => {
    if (!currentTask?.id || !sessionId) return;
    const key = `${sessionId}:${currentTask.id}`;
    if (store.lectureCache[key]) { setLectureLoaded(true); return; }
    setLectureLoaded(false);
    autoGenRef.current = false;
    fetch(`/api/sections/${encodeURIComponent(currentTask.id)}/lecture?sessionId=${encodeURIComponent(sessionId)}`, { headers: authHeaders() })
      .then(r => r.json())
      .then(d => {
        store.markLoaded(currentTask.id);
        if (d?.data?.lecture?.content) {
          store.setLecture(key, d.data.lecture.content);
          store.markGenerated(currentTask.id);
        }
      })
      .catch(() => store.markLoaded(currentTask.id))
      .finally(() => setLectureLoaded(true));
  }, [currentTask?.id, sessionId]);

  // ── Auto-generate if no content exists for this task ──
  useEffect(() => {
    if (!lectureLoaded || !currentTask || !sessionId) return;
    const key = `${sessionId}:${currentTask.id}`;
    if (store.lectureCache[key] || autoGenRef.current) return;
    autoGenRef.current = true;
    // Auto-generate after a short delay so the UI renders first
    const timer = setTimeout(() => handleGenerate(), 400);
    return () => clearTimeout(timer);
  }, [lectureLoaded, currentTask?.id, sessionId]);

  // ── Auto-select best content type for task ──
  useEffect(() => {
    if (currentTask) {
      const best = getDefaultContentType((currentTask as any).task_type);
      store.setContentType(best);
    }
  }, [currentTask?.id]);

  // ── Content for the router ──
  const sectionContent: SectionContent | null = useMemo(() => {
    if (!lecture || !currentTask) return null;
    return {
      contentType: store.contentType || 'lecture',
      title: currentTask.title,
      goal: currentTask.goal || '',
      content: lecture,
      knowledgePoints: (currentTask.knowledgePoints || []).map((kp: any) =>
        typeof kp === 'string' ? { name: kp } : { name: kp.name, type: kp.type }
      ),
    };
  }, [lecture, currentTask, store.contentType]);

  // ── Generate content ──
  const [generating, setGenerating] = useState(false);
  const handleGenerate = useCallback(async () => {
    if (!currentTask || !sessionId) return;
    setGenerating(true);
    try {
      const res = await fetch(`/api/sections/${encodeURIComponent(currentTask.id)}/lecture/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          sessionId,
          sectionTitle: currentTask.title,
          sectionGoal: currentTask.goal || '',
          courseId: path?.courseName || '',
          knowledgePoints: currentTask.knowledgePoints || [],
          task_type: (currentTask as any).task_type || '',
          requirements: `这是一道${(currentTask as any).task_type || '学习'}类型的每日任务，请按照该类型的教学特点生成内容。`,
        }),
      });
      const data = await res.json();
      if (data?.data?.lecture?.content) {
        store.setLecture(`${sessionId}:${currentTask.id}`, data.data.lecture.content);
        store.markGenerated(currentTask.id);
      }
    } catch { /* fail silently */ }
    finally { setGenerating(false); }
  }, [currentTask, sessionId, path?.courseName]);

  // ── Task completion ──
  const handleComplete = useCallback(async () => {
    if (!currentTask) return;
    timer.reset();
    // Mark mastered
    (currentTask.knowledgePoints || []).forEach((kp: any) => {
      updateKnowledgePoint(kp.id || kp.name, { status: 'mastered' });
    });
    // Log event
    logStudyEvent({
      sessionId, event: 'daily_task_complete',
      resourceId: currentTask.id,
      metadata: {
        title: currentTask.title,
        task_type: (currentTask as any).task_type || '',
        study_seconds: timer.totalSeconds,
      },
    }).catch(() => {});
    // Jump to next incomplete task
    const next = tasks.findIndex((t: Section, i: number) => i > activeTaskIdx && t.status !== 'mastered');
    if (next >= 0) {
      nav(`/lecture/section/${encodeURIComponent(tasks[next].id)}`);
    }
  }, [currentTask, tasks, activeTaskIdx, timer, sessionId, updateKnowledgePoint, nav]);

  // ── Navigate between tasks ──
  const goToTask = useCallback((idx: number) => {
    const task = tasks[idx];
    if (task) nav(`/lecture/section/${encodeURIComponent(task.id)}`);
  }, [tasks, nav]);

  // ── Navigate between days ──
  const goToDay = useCallback((dayIdx: number) => {
    const day = allDays[dayIdx];
    if (day?.sections[0]) {
      nav(`/lecture/section/${encodeURIComponent(day.sections[0].id)}`);
    }
  }, [allDays, nav]);

  const prevTask = activeTaskIdx > 0 ? tasks[activeTaskIdx - 1] : null;
  const nextTask = activeTaskIdx < tasks.length - 1 ? tasks[activeTaskIdx + 1] : null;
  const allDone = tasks.length > 0 && tasks.every((t: Section) => t.status === 'mastered');

  // ════════════════════════════════════════════════════════════════════
  // Render
  // ════════════════════════════════════════════════════════════════════
  return (
    <div className="flex h-screen -m-6 bg-surface-50/50">
      {/* ══ Left sidebar: day nav + task list ══ */}
      <div className="w-52 lg:w-56 xl:w-60 bg-white border-r border-surface-200 flex flex-col flex-shrink-0 overflow-y-auto">
        {/* Back button + mode badge */}
        <div className="p-4 border-b border-surface-100">
          <button onClick={onBack}
            className="flex items-center gap-1.5 text-xs text-surface-500 hover:text-blue-600 rounded-lg px-2 py-1 -ml-2 mb-3 transition-colors">
            <ArrowLeft size={14} />返回路径
          </button>
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-violet-100 text-violet-700 text-[10px] font-bold mb-3">
            📅 日课式
          </div>
          {/* Day selector */}
          <DayNavigator
            days={allDays.map((d: typeof allDays[number]) => ({
              title: d.dayTitle,
              taskCount: d.sections.length,
              completed: d.completed,
            }))}
            activeDayIdx={activeDayIdx}
            onSelectDay={goToDay}
          />
        </div>

        {/* Today's task list */}
        <div className="flex-1 px-3 pb-3">
          <TaskSidebar
            tasks={tasks}
            activeIdx={activeTaskIdx}
            onSelect={goToTask}
          />
        </div>

        {/* Timer */}
        <div className="border-t border-surface-100 p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-semibold text-surface-400 uppercase tracking-wider">学习计时</span>
            <button onClick={timer.reset} className="text-surface-300 hover:text-surface-500">
              <RotateCcw size={12} />
            </button>
          </div>
          <div className="text-2xl font-bold text-surface-800 font-display text-center tabular-nums">
            {String(timer.mins).padStart(2, '0')}:{String(timer.secs).padStart(2, '0')}
          </div>
          <button
            onClick={timer.running ? timer.pause : timer.start}
            className={`mt-2 w-full flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-semibold transition-all active:scale-[0.98]
              ${timer.running
                ? 'bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100'
                : 'bg-blue-500 text-white hover:bg-blue-600 shadow-sm'}`}
          >
            {timer.running ? <><Pause size={12} />暂停</> : <><Play size={12} />开始计时</>}
          </button>
        </div>
      </div>

      {/* ══ Center: task content ══ */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 overflow-y-auto">
          {currentTask ? (
            <div className="p-6 max-w-3xl mx-auto">
              {/* Task header */}
              <DailyTaskHeader
                taskType={(currentTask as any).task_type}
                sectionTitle={currentTask.title}
                estimatedMinutes={currentTask.estimatedMinutes}
                dayIndex={activeDayIdx + 1}
                totalDays={allDays.length}
                completedTasks={activeDay?.completed || 0}
                totalTasks={tasks.length}
              />

              {/* Content: auto-show flashcard for vocab, step-through for grammar, etc. */}
              {lecture ? (
                sectionContent && <SectionContentRouter content={sectionContent} />
              ) : lectureLoaded ? (
                <div className="bg-white rounded-2xl shadow-soft p-10 text-center">
                  <Sparkles size={40} className="text-surface-300 mx-auto mb-3" />
                  <p className="text-surface-500 text-sm mb-4">还没有内容，让 AI 帮你生成今日任务吧</p>
                  <button onClick={handleGenerate} disabled={generating}
                    className="inline-flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-violet-500 to-blue-500 text-white rounded-xl text-sm font-semibold hover:from-violet-600 hover:to-blue-600 disabled:opacity-50 transition-all shadow-md shadow-violet-500/20">
                    <Sparkles size={15} />{generating ? '生成中…' : '生成今日任务'}
                  </button>
                </div>
              ) : (
                <div className="flex items-center justify-center h-64">
                  <div className="w-6 h-6 border-2 border-violet-400 border-t-transparent rounded-full animate-spin" />
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-center h-full">
              <p className="text-surface-400 text-sm">选择左侧任务开始今日学习</p>
            </div>
          )}
        </div>

        {/* ══ Bottom bar: task navigation + complete button ══ */}
        {currentTask && (
          <div className="bg-white border-t border-surface-200 px-6 py-3 flex items-center justify-between flex-shrink-0">
            <button
              onClick={() => prevTask && goToTask(activeTaskIdx - 1)}
              disabled={!prevTask}
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-xl transition-all
                disabled:opacity-30 text-surface-500 hover:bg-surface-100">
              <ArrowLeft size={13} />上一任务
            </button>

            <div className="flex items-center gap-2 text-xs text-surface-400">
              <span>{activeTaskIdx + 1} / {tasks.length}</span>
              <div className="w-24 h-1.5 bg-surface-100 rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-violet-400 to-blue-500 rounded-full transition-all"
                  style={{ width: `${tasks.length > 0 ? ((activeTaskIdx + 1) / tasks.length) * 100 : 0}%` }} />
              </div>
            </div>

            {allDone ? (
              <button className="flex items-center gap-1.5 px-5 py-2 bg-emerald-500 text-white rounded-xl text-xs font-semibold shadow-md shadow-emerald-500/20 hover:bg-emerald-600 transition-all">
                <Trophy size={14} />今日全部完成！
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <button onClick={handleComplete}
                  className="flex items-center gap-1.5 px-5 py-2 bg-gradient-to-r from-violet-500 to-blue-500 text-white rounded-xl text-xs font-semibold shadow-md shadow-violet-500/20 hover:from-violet-600 hover:to-blue-600 active:scale-[0.98] transition-all">
                  <CheckCircle2 size={14} />标记完成
                </button>
                {nextTask && (
                  <button onClick={() => goToTask(activeTaskIdx + 1)}
                    className="flex items-center gap-1 px-4 py-2 text-xs font-medium text-surface-500 hover:text-surface-700 hover:bg-surface-100 rounded-xl transition-all">
                    跳过<ChevronRight size={13} />
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ══ Right: tools panel (tutor / resources / generate) ══ */}
      {currentTask && (
        <DailyToolsPanel
          sessionId={sessionId}
          activeSectionId={currentTask.id}
          section={currentTask}
          lecture={lecture}
          sections={tasks}
          pathId={path?.id || ''}
          chapterTitle={activeDay?.weekTitle || ''}
          store={store}
        />
      )}
      {!currentTask && (
        <div className="w-56 lg:w-60 xl:w-64 bg-white border-l border-surface-200 flex items-center justify-center">
          <p className="text-xs text-surface-400">选择任务后可用</p>
        </div>
      )}
    </div>
  );
}
