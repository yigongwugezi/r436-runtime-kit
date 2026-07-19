import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { authHeaders } from '../api/client';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useLearningPath } from '../hooks/useLearningPath';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';
import {
  ArrowLeft, BookOpen, CheckCircle, Clock3, FlaskConical, Loader2,
  Target, Sparkles, FileText, Brain, Puzzle, Video, ChevronRight,
  Lightbulb, GraduationCap, Lock, Eye
} from 'lucide-react';
import Markdown from '../utils/markdown';
import TextbookViewer from '../components/learning/TextbookViewer';
import { getTextbookContent } from '../api/textbooks';

/* ── Types ───────────────────────────── */
interface Resource {
  id: string; type: string; title: string; description?: string;
  content?: string; items?: any[]; format?: string; related_stage_id?: string;
}
interface Task {
  task_id?: string; id?: string; title: string; type: string;
  goal?: string; estimated_minutes?: number; status?: string;
}

const TYPE_META: Record<string, { label: string; icon: React.ReactNode; gradient: string }> = {
  read_doc:   { label: '阅读', icon: <BookOpen size={18} />,     gradient: 'from-blue-500 to-indigo-500' },
  do_quiz:    { label: '小测', icon: <FlaskConical size={18} />,  gradient: 'from-amber-500 to-orange-500' },
  practice:   { label: '练习', icon: <Target size={18} />,        gradient: 'from-emerald-500 to-teal-500' },
  write_code: { label: '编程', icon: <Puzzle size={18} />,        gradient: 'from-violet-500 to-purple-500' },
  method:     { label: '方法', icon: <Lightbulb size={18} />,    gradient: 'from-rose-500 to-pink-500' },
  mock:       { label: '模拟', icon: <GraduationCap size={18} />, gradient: 'from-cyan-500 to-blue-500' },
  review:     { label: '复盘', icon: <Sparkles size={18} />,     gradient: 'from-amber-500 to-yellow-500' },
};
const UNSUPPORTED_META = { label: '暂不支持', icon: <FileText size={18} />, gradient: 'from-slate-500 to-slate-600' };

function findTask(stages: any[], taskId: string): { task: any; stage: any } | null {
  // v1.2: 同时搜索 stages→tasks 与 stages→days→tasks（_rewrite_stage_ids 后的格式）
  for (const stage of stages) {
    const candidates = [...(stage.tasks || []), ...(stage.days || []).flatMap((d: any) => d.tasks || [])];
    for (const t of candidates) {
      const tid = typeof t === 'string' ? t : (t.task_id || t.id || t.title || '');
      if (tid === taskId) {
        // 直接返回原始 task 对象的引用（保留所有后端字段：textbookPageStart/End/SectionId 等）
        const task: any = typeof t === 'string'
          ? { title: t, type: 'read_doc', goal: t.slice(0, 100), estimated_minutes: 45 }
          : { ...t, task_id: t.task_id || t.id, id: t.id || t.task_id, title: t.title || '', type: t.type || 'read_doc', goal: t.goal || '', estimated_minutes: t.estimated_minutes || 45, status: t.status };
        return { task, stage };
      }
    }
  }
  return null;
}

export default function TaskPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const [searchParams] = useSearchParams();
  const mode = searchParams.get('mode');
  const nav = useNavigate();
  const { path, updateNodeStatus } = useLearningPath();
  const sessionId = useChatStore((s) => s.dataSessionId);
  const subjectId = useSubjectStore((s) => s.activeSubject?.id ?? s.activeClassSubject?.subject);
  const [resources, setResources] = useState<Resource[]>([]);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(false);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stages = path?.stages || [];
  const found = useMemo(() => taskId ? findTask(stages, taskId) : null, [stages, taskId]);
  const taskAny = found?.task as any;
  const task = found?.task;
  const stage = found?.stage;

  // ── Textbook mode ──
  const isTextbookMode = !!useSubjectStore((s) => s.activeSubject)?.textbookId;
  const activeSubjectId = useSubjectStore((s) => s.activeSubject?.id ?? s.activeClassSubject?.subject);
  // v1.2: 教材判定仅看 source_section_ids（页码由后端 GET /learning-path 富化）
  const hasTextbookPages = isTextbookMode
    && Array.isArray(taskAny?.source_section_ids) && taskAny.source_section_ids.length > 0;
  const [textbookLectureContent, setTextbookLectureContent] = useState('');

  useEffect(() => {
    if (!isTextbookMode || !activeSubjectId || !taskAny?.textbookSectionId) {
      setTextbookLectureContent('');
      return;
    }
    let cancelled = false;
    getTextbookContent(activeSubjectId, {
      sectionId: taskAny.textbookSectionId,
    }).then(c => {
      if (!cancelled) setTextbookLectureContent(c?.content ?? '');
    }).catch(() => {
      if (!cancelled) setTextbookLectureContent('');
    });
    return () => { cancelled = true; };
  }, [isTextbookMode, activeSubjectId, taskAny?.textbookSectionId]);
  const isLocked = mode === 'preview' || (stage && stages.indexOf(stage) > stages.findIndex(s =>
    (s.tasks || []).some((t: any) => t.status !== 'completed' && t.status !== 'mastered')
  ));
  const isDone = task?.status === 'completed' || task?.status === 'mastered';
  const meta = task?.type ? (TYPE_META[task.type] ?? UNSUPPORTED_META) : UNSUPPORTED_META;

  const fetchResources = useCallback(async (): Promise<boolean> => {
    if (!taskId || !sessionId || !subjectId || !path?.id || !stage?.id) return false;
    try {
      const params = new URLSearchParams({
        sessionId,
        subjectId,
        pathId: path.id,
        stageId: stage.id,
        taskId,
      });
      const r = await fetch(`/api/sections/${encodeURIComponent(taskId)}/generated-resources?${params}`, { headers: authHeaders() }).then(r => r.json());
      const list = r.resources || [];
      setResources(list);
      if (list.length > 0) return true;
    } catch {}
    return false;
  }, [taskId, sessionId, subjectId, path?.id, stage?.id]);

  useEffect(() => {
    if (!taskId || !sessionId) return;
    setLoading(true);
    fetchResources().then(ok => {
      if (ok) { setLoading(false); return; }
      if (isLocked) { setLoading(false); return; }
      setPolling(true);
      const poll = () => {
        pollRef.current = setTimeout(async () => {
          const done = await fetchResources();
          if (done) { setPolling(false); setLoading(false); }
          else poll();
        }, 3000);
      };
      poll();
    });
    return () => { if (pollRef.current) clearTimeout(pollRef.current); };
  }, [taskId, sessionId]);

  const byType = useMemo(() => {
    const map: Record<string, Resource[]> = {};
    for (const r of resources) {
      if (!map[r.type]) map[r.type] = [];
      map[r.type].push(r);
    }
    return map;
  }, [resources]);

  if (!taskId) return <div className="flex-1 flex items-center justify-center text-surface-400">缺少任务ID</div>;
  if (!task) return <div className="flex-1 flex items-center justify-center text-surface-400">未找到该任务</div>;

  const lecture = byType['lecture']?.[0];
  const quiz = byType['quiz']?.[0];
  const practice = byType['practice']?.[0];
  const mindmap = byType['mindmap']?.[0];
  const reading = byType['reading']?.[0];

  return (
    <div className="flex-1 overflow-y-auto bg-surface-50">
      {/* ── 顶部导航 ── */}
      <div className="sticky top-0 z-20 bg-white/80 backdrop-blur-xl border-b border-surface-200/60">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center h-16 gap-3">
            <button onClick={() => nav('/path')}
              className="flex items-center gap-1.5 text-sm text-surface-400 hover:text-surface-600 transition-colors shrink-0">
              <ArrowLeft size={18} /> 返回
            </button>
            <div className="w-px h-6 bg-surface-200 shrink-0" />
            <span className="text-sm text-surface-400 truncate">{stage?.title || ''}</span>
            <ChevronRight size={14} className="text-surface-300 shrink-0" />
            <span className="text-sm font-medium text-surface-700 truncate">{task.title}</span>
          </div>
        </div>
      </div>

      {/* ── Hero ── */}
      <div className={`bg-gradient-to-r ${meta.gradient} relative overflow-hidden`}>
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(255,255,255,0.2),transparent_60%)]" />
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10 sm:py-14 relative">
          <div className="flex items-start gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-white/20 backdrop-blur-sm text-white shadow-lg">
              {meta.icon}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-3 mb-2">
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-white/20 text-white backdrop-blur-sm">
                  {meta.icon}{meta.label}
                </span>
                {task.estimated_minutes && (
                  <span className="inline-flex items-center gap-1 text-xs text-white/80"><Clock3 size={14} />{task.estimated_minutes}分钟</span>
                )}
                {isLocked && (
                  <span className="inline-flex items-center gap-1 text-xs text-white/70 bg-white/10 px-2 py-0.5 rounded-full"><Eye size={12} />预览</span>
                )}
              </div>
              <h1 className="text-2xl sm:text-3xl font-bold text-white leading-tight tracking-tight line-clamp-2">{task.title}</h1>
              {task.goal && <p className="mt-2 text-base text-white/80 max-w-2xl leading-relaxed">{task.goal}</p>}
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* ── Textbook PDF viewer / fallback ── */}
        {hasTextbookPages && activeSubjectId ? (
          <section className="bg-white rounded-2xl border border-surface-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-surface-100 flex items-center gap-3">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600"><BookOpen size={18} /></span>
              <h2 className="text-base font-semibold text-surface-800">教材内容</h2>
              <span className="text-xs text-surface-400">
                第{taskAny.textbookPageStart}-{taskAny.textbookPageEnd}页
              </span>
            </div>
            <div className="h-[600px]">
              <TextbookViewer
                subjectId={activeSubjectId}
                pageStart={taskAny.textbookPageStart!}
                pageEnd={taskAny.textbookPageEnd!}
              />
            </div>
          </section>
        ) : isTextbookMode && !hasTextbookPages ? (
          <section className="bg-white rounded-2xl border border-surface-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-surface-100 flex items-center gap-3">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50 text-amber-600"><BookOpen size={18} /></span>
              <h2 className="text-base font-semibold text-surface-800">教材内容</h2>
              <span className="text-xs text-amber-500">尚未关联教材章节</span>
            </div>
            <div className="px-6 py-10 flex flex-col items-center justify-center gap-4 text-center">
              <BookOpen size={40} className="text-surface-200" />
              <div>
                <p className="text-sm text-surface-500 max-w-sm">
                  此任务未关联教材的具体章节。规划时教材信息可能未能被正确识别。
                </p>
                <p className="text-xs text-surface-400 mt-1">
                  点击下方按钮回到智能对话重新规划，或返回学习路径页面。
                </p>
              </div>
              <div className="flex items-center gap-3">
                <button onClick={() => nav('/chat', { state: { chatMode: 'planning' } })}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-brand-500 text-white rounded-lg text-sm font-medium hover:bg-brand-600 transition-colors shadow-sm">
                  <Sparkles size={16} />去对话重新规划
                </button>
                <button onClick={() => nav('/path')}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-surface-100 text-surface-600 rounded-lg text-sm font-medium hover:bg-surface-200 transition-colors">
                  <ArrowLeft size={16} />返回学习路径
                </button>
              </div>
            </div>
          </section>
        ) : null}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="flex flex-col items-center gap-3">
              <Loader2 size={32} className="animate-spin text-primary-500" />
              <p className="text-sm text-surface-400">加载学习资源中...</p>
            </div>
          </div>
        ) : (
          <>
            {/* ── 讲课文稿 ── */}
            {lecture?.content && (
              <section className="bg-white rounded-2xl border border-surface-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-surface-100 flex items-center gap-3">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-50 text-primary-600"><BookOpen size={18} /></span>
                  <h2 className="text-base font-semibold text-surface-800">课程讲义</h2>
                </div>
                <div className="p-6 sm:p-8 prose prose-sm max-w-none prose-headings:text-surface-800 prose-p:text-surface-600 prose-a:text-primary-500 prose-code:text-rose-500 prose-pre:bg-surface-900 prose-pre:text-surface-100 max-h-[600px] overflow-y-auto">
                  <Markdown content={lecture.content} />
                </div>
              </section>
            )}

            {/* ── 思维导图 ── */}
            {mindmap?.content && (
              <section className="bg-white rounded-2xl border border-surface-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-surface-100 flex items-center gap-3">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-50 text-purple-600"><Brain size={18} /></span>
                  <h2 className="text-base font-semibold text-surface-800">知识图谱</h2>
                </div>
                <div className="p-6">
                  <div className="bg-surface-50 rounded-xl p-6 font-mono text-sm text-surface-600 whitespace-pre overflow-x-auto border border-surface-100 min-h-[200px]">
                    {mindmap.content}
                  </div>
                </div>
              </section>
            )}

            {/* ── 随堂测验 ── */}
            {quiz?.items && quiz.items.length > 0 && (
              <section className="bg-white rounded-2xl border border-surface-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-surface-100 flex items-center gap-3">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50 text-amber-600"><FlaskConical size={18} /></span>
                  <h2 className="text-base font-semibold text-surface-800">随堂测验</h2>
                  <span className="text-xs text-surface-400">检验本节掌握程度</span>
                </div>
                <div className="p-6"><QuizCard items={quiz.items} /></div>
              </section>
            )}

            {/* ── 实操练习 ── */}
            {practice?.content && (
              <section className="bg-white rounded-2xl border border-surface-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-surface-100 flex items-center gap-3">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600"><Target size={18} /></span>
                  <h2 className="text-base font-semibold text-surface-800">实操练习</h2>
                </div>
                <div className="p-6 sm:p-8 prose prose-sm max-w-none prose-headings:text-surface-800 prose-p:text-surface-600 prose-code:text-rose-500 prose-pre:bg-surface-900 prose-pre:text-surface-100 max-h-[500px] overflow-y-auto">
                  <Markdown content={practice.content} />
                </div>
              </section>
            )}

            {/* ── 拓展阅读 ── */}
            {reading?.content && (
              <section className="bg-white rounded-2xl border border-surface-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-surface-100 flex items-center gap-3">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600"><FileText size={18} /></span>
                  <h2 className="text-base font-semibold text-surface-800">拓展阅读</h2>
                </div>
                <div className="p-6 sm:p-8 prose prose-sm max-w-none prose-headings:text-surface-800 prose-p:text-surface-600">
                  <Markdown content={reading.content} />
                </div>
              </section>
            )}

            {/* ── 自动轮询中 ── */}
            {polling && (
              <div className="text-center py-20 bg-white rounded-2xl border border-surface-200 shadow-sm">
                <Loader2 size={40} className="mx-auto mb-4 animate-spin text-primary-400" />
                <h3 className="text-lg font-semibold text-surface-700 mb-2">正在准备学习资源</h3>
                <p className="text-sm text-surface-400">系统正在生成讲义、测验等学习材料，请稍候...</p>
              </div>
            )}

            {/* ── 无资源（极少发生） ── */}
            {!loading && !polling && resources.length === 0 && (
              <div className="text-center py-20 bg-white rounded-2xl border border-surface-200 shadow-sm">
                <BookOpen size={48} className="mx-auto mb-4 text-surface-300" />
                <h3 className="text-lg font-semibold text-surface-700 mb-2">暂无学习资源</h3>
                <p className="text-sm text-surface-400">该任务暂无可用资源，请返回路径页面重新生成。</p>
              </div>
            )}

            {/* ── 完成按钮 ── */}
            {!isLocked && resources.length > 0 && (
              <div className="flex items-center gap-4 pt-4 pb-8">
                <button onClick={() => { if (taskId) updateNodeStatus(taskId, isDone ? 'available' as any : 'mastered'); }}
                  className={`flex items-center gap-2.5 px-6 py-3 rounded-xl text-sm font-bold transition-all ${
                    isDone
                      ? 'border-2 border-success-200 bg-success-50 text-success-600'
                      : 'bg-gradient-to-r from-primary-500 to-accent-500 text-white shadow-lg hover:shadow-xl hover:scale-[1.02] active:scale-[0.98]'
                  }`}>
                  <CheckCircle size={20} />
                  {isDone ? '已完成' : '标记完成'}
                </button>
                <button onClick={() => nav('/path')}
                  className="px-5 py-3 rounded-xl border border-surface-200 text-sm font-medium text-surface-600 hover:bg-surface-50 transition-colors">
                  返回路径
                </button>
              </div>
            )}

            {isLocked && (
              <div className="flex items-center gap-3 py-6 text-surface-400"><Lock size={18} /><span className="text-sm">当前阶段已锁定，请先完成前置阶段的学习任务。</span></div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/* ── Quiz ── */
function QuizCard({ items }: { items: any[] }) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState(false);

  const handleSelect = (qId: string, optKey: string) => {
    if (submitted) return;
    setAnswers(p => ({ ...p, [qId]: optKey }));
  };

  const correct = items.filter(q => answers[q.question_id] === q.answer).length;

  return (
    <div className="space-y-6">
      {items.map((q, i) => {
        const sel = answers[q.question_id];
        const isCorrect = submitted && sel === q.answer;
        const isWrong = submitted && sel && sel !== q.answer;
        return (
          <div key={q.question_id} className="space-y-3">
            <p className="text-sm font-medium text-surface-800">{i + 1}. {q.stem}</p>
            {q.options?.length > 0 ? (
              <div className="grid gap-2">
                {q.options.map((opt: string) => {
                  const key = opt.charAt(0);
                  const picked = sel === key;
                  return (
                    <button key={opt} onClick={() => handleSelect(q.question_id, key)}
                      className={`flex items-center gap-3 w-full text-left px-4 py-3 rounded-xl text-sm border transition-all ${
                        submitted && key === q.answer
                          ? 'border-success-300 bg-success-50 text-success-700 ring-1 ring-success-300'
                          : isWrong && picked
                            ? 'border-error-200 bg-error-50 text-error-600'
                            : picked
                              ? 'border-primary-200 bg-primary-50 text-primary-700 ring-1 ring-primary-200'
                              : 'border-surface-200 bg-white text-surface-600 hover:border-surface-300 hover:shadow-sm'
                      }`}>
                      <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                        submitted && key === q.answer ? 'bg-success-500 text-white' :
                        picked ? 'bg-primary-500 text-white' :
                        'bg-surface-100 text-surface-500'
                      }`}>{key}</span>
                      <span>{opt.slice(opt.indexOf(')') + 1).trim() || opt.slice(2).trim()}</span>
                      {submitted && key === q.answer && <CheckCircle size={16} className="ml-auto text-success-500" />}
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="bg-surface-50 rounded-xl p-4 text-sm text-surface-600 border border-surface-100">
                {q.explanation || q.answer}
              </div>
            )}
            {isWrong && q.explanation && <p className="text-xs text-surface-500 italic">💡 {q.explanation}</p>}
          </div>
        );
      })}
      <div className="flex items-center gap-3 pt-2">
        {!submitted ? (
          <button onClick={() => setSubmitted(true)}
            className="px-5 py-2.5 bg-gradient-to-r from-primary-500 to-accent-500 text-white rounded-xl text-sm font-semibold shadow-md hover:shadow-lg transition-all">
            提交答案
          </button>
        ) : (
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold text-success-600">✓ {correct}/{items.length} 正确</span>
            <button onClick={() => { setSubmitted(false); setAnswers({}); }}
              className="text-sm text-primary-500 hover:text-primary-600 transition-colors">重新作答</button>
          </div>
        )}
      </div>
    </div>
  );
}
