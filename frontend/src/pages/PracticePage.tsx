import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  AlertCircle, ArrowLeft, ArrowRight, BarChart3, BookOpen,
  Check, ChevronRight, ClipboardList, GraduationCap, Play,
  Settings, Target, X, Loader2, RefreshCw
} from 'lucide-react';
import Markdown from '../utils/markdown';
import { listQuestions, gradeAnswer, getWeakQuestions, getAnswerHistory, getQuestionSets } from '../api/chat';
import { generateQuestions } from '../api/questions';
import { getAnalytics } from '../api/analytics';
import { listExamSets, getExamSetResults, startExamSetAttempt, submitExamSet, listExamSetAttempts, updateAttempt } from '../api/assessment';
import type { ExamSet, Attempt, QuizResult } from '../types/assessment';
import { getPushedQuestions } from '../api/classSubjects';
import { getCurrentLearner } from '../store/authStore';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';

interface Question { question_id: string; type: string; stem: string; options?: string[]; difficulty?: string; knowledge_points?: string[]; correct?: string; explanation?: string; }
type ViewKey = 'home' | 'quiz' | 'exam' | 'history';

export default function PracticePage() {
  const nav = useNavigate(); const isParent = getCurrentLearner()?.role === 'parent';
  if (isParent) return (
    <div className="flex min-h-full items-center justify-center animate-fade-in">
      <div className="max-w-md p-6 text-center"><div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-surface-100 dark:bg-surface-700"><Settings className="h-8 w-8 text-surface-400" /></div><h3 className="mb-2 text-lg font-semibold text-surface-800 dark:text-gray-100">只读模式</h3><p className="text-sm text-surface-500 dark:text-gray-400">家长账户无法使用练习功能。<br/>请前往学习分析查看孩子的答题情况。</p></div></div>
  );

  const sessionId = useChatStore((s) => s.currentSessionId);
  const [searchParams] = useSearchParams();
  const [activeView, setActiveView] = useState<ViewKey>('home');
  const [loading, setLoading] = useState(true);
  const [analytics, setAnalytics] = useState<any>(null);    // 完整学习分析
  const [stats, setStats] = useState<any>(null);
  const [weakData, setWeakData] = useState<any>(null);
  const [historyData, setHistoryData] = useState<any>(null);
  const [sets, setSets] = useState<any[]>([]);
  const [examSets, setExamSets] = useState<ExamSet[]>([]);
  const [pushedGroups, setPushedGroups] = useState<any[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [grades, setGrades] = useState<Record<string, any>>({});
  const [currentIdx, setCurrentIdx] = useState(0);
  const [grading, setGrading] = useState(false);
  const submitIdempotencyKeyRef = useRef('');
  const [activeExamSet, setActiveExamSet] = useState<ExamSet | null>(null);
  const [examSetAttempts, setExamSetAttempts] = useState<Attempt[]>([]);
  const [examSetQuestions, setExamSetQuestions] = useState<any[]>([]);
  const [examSetResults, setExamSetResults] = useState<QuizResult[]>([]);
  const [examSetAttemptId, setExamSetAttemptId] = useState('');
  const [examSetSubmitted, setExamSetSubmitted] = useState(false);
  const [examSetTotalScore, setExamSetTotalScore] = useState<number | null>(null);
  const [examSetWeakPoints, setExamSetWeakPoints] = useState<any[]>([]);

  useEffect(() => {
    const csid = searchParams.get('classSubjectId') || useSubjectStore.getState().activeClassSubject?.id || '';
    Promise.all([
      getAnalytics({ sessionId }).then(setAnalytics).catch(() => {}),
      getQuestionSets(sessionId).then((d: any) => d?.sets || []).catch(() => []).then(setSets),
      getAnswerHistory(sessionId).then((d: any) => { if (d) { setStats(d); setHistoryData(d); } }).catch(() => {}),
      getWeakQuestions(sessionId).then((d: any) => { if (d) setWeakData(d); }).catch(() => {}),
      csid ? getPushedQuestions(csid).then(setPushedGroups).catch(() => {}) : Promise.resolve(),
      listExamSets({ sessionId }).then((d: any) => { if (d?.examSets) setExamSets(d.examSets); }).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const eid = searchParams.get('examSetId');
    if (eid && examSets.length > 0) { const es = examSets.find(e => e.id === eid); if (es) { setActiveExamSet(es); setActiveView('exam'); } }
  }, [searchParams, examSets]);

  const openExamSet = async (es: ExamSet) => { setActiveExamSet(es); setActiveView('exam'); setExamSetSubmitted(false); setExamSetResults([]); setExamSetTotalScore(null); try { const r: any = await listExamSetAttempts(es.id); setExamSetAttempts(r?.data?.attempts || r?.attempts || []); } catch { setExamSetAttempts([]); } };
  const startExamSet = async () => {
    if (!activeExamSet) return; try {
      const res: any = await startExamSetAttempt(activeExamSet.id, { sessionId });
      setExamSetAttemptId((res?.data || res)?.attempt?.attemptId || ''); submitIdempotencyKeyRef.current = '';
      const qRes: any = await getExamSetResults(activeExamSet.id); const linked = ((qRes?.data || qRes)?.examSet?.linkedQuestions) || [];
      const m = linked.map((q: any) => ({ question_id: q.questionId, type: q.type, stem: q.stem, options: q.options, difficulty: q.difficulty, knowledge_points: q.knowledgePoints || [] }));
      setExamSetQuestions(m); setQuestions(m); setCurrentIdx(0); setAnswers({}); setGrades({}); setExamSetSubmitted(false); setActiveView('quiz');
    } catch (e: any) { alert('开始作答失败: ' + (e?.message || '请重试')); }
  };
  const continueExamSet = async () => {
    if (!activeExamSet) return; const ip = examSetAttempts.find(a => a.status === 'in_progress'); if (!ip) { startExamSet(); return; }
    setExamSetAttemptId(ip.attemptId); try {
      const qRes: any = await getExamSetResults(activeExamSet.id); const linked = ((qRes?.data || qRes)?.examSet?.linkedQuestions) || [];
      const m = linked.map((q: any) => ({ question_id: q.questionId, type: q.type, stem: q.stem, options: q.options, difficulty: q.difficulty, knowledge_points: q.knowledgePoints || [] }));
      setExamSetQuestions(m); setQuestions(m); setCurrentIdx(0);
      if (ip.answers) { const sv: Record<string, string> = {}; (ip.answers as any[]).forEach((a: any) => { sv[a.questionId] = a.answer || a.studentAnswer || ''; }); setAnswers(sv); } else setAnswers({});
      setGrades({}); setExamSetSubmitted(false); setActiveView('quiz');
    } catch { alert('继续作答失败'); }
  };
  const submitExamSetAnswers = async () => {
    if (!activeExamSet || !examSetAttemptId) return; setGrading(true);
    if (!submitIdempotencyKeyRef.current) submitIdempotencyKeyRef.current = crypto.randomUUID();
    try {
      const al = examSetQuestions.map(q => ({ questionId: q.question_id, answer: answers[q.question_id] || '' }));
      const res: any = await submitExamSet(activeExamSet.id, { sessionId, answers: al, idempotencyKey: submitIdempotencyKeyRef.current });
      const d = res?.data || res; setExamSetResults(d?.results || []); setExamSetTotalScore(d?.totalScore ?? null);
      setExamSetWeakPoints(d?.weakPoints || []); setExamSetSubmitted(true); setActiveView('exam');
      const esRes: any = await getExamSetResults(activeExamSet.id);
      if (esRes?.data?.examSet || esRes?.examSet) setActiveExamSet(esRes?.data?.examSet || esRes?.examSet);
      const attRes: any = await listExamSetAttempts(activeExamSet.id);
      setExamSetAttempts(attRes?.data?.attempts || attRes?.attempts || []);
    } catch (e: any) { alert('提交失败: ' + (e?.message || '请重试')); } setGrading(false);
  };
  const handleAnswer = (val: string) => { const q = questions[currentIdx]; if (!q || grades[q.question_id]) return; setAnswers(a => ({ ...a, [q.question_id]: val })); };
  const handleSubmit = async () => { const q = questions[currentIdx]; if (!q || grades[q.question_id]) return; setGrading(true); try { const r: any = await gradeAnswer(q.question_id, answers[q.question_id] || '', sessionId); setGrades(g => ({ ...g, [q.question_id]: r })); } catch { alert('批改失败'); } setGrading(false); };

  // ── Derived stats ──
  const a = analytics || {};
  const trend: number[] = (a.completionTrend || []).slice(-12).map((p: any) => p.count);
  const trendMax = Math.max(...trend, 4);
  const totalAttempted = stats?.totalAttempted || a.practiceCount || 0;
  const totalCorrect = stats?.totalCorrect || 0;
  const weakCount = weakData?.records?.length || a.weakTopics?.length || 0;
  const accuracy = totalAttempted > 0 ? Math.round((totalCorrect / totalAttempted) * 100) : (a.quizAccuracy != null ? Math.round(a.quizAccuracy) : null);
  const studyMinutes = a.totalStudyMinutes || 0;
  const todayMinutes = a.todayStudyMinutes || 0;
  const streak = a.streak || 0;

  /* ══════════════════════════════════════════════════════════════ RENDER ══════════════════════════════════════════════════════════════ */
  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div><h2 className="font-display text-2xl font-bold text-surface-800 dark:text-gray-100">练习中心</h2><p className="text-surface-500 dark:text-gray-400 mt-1">巩固知识 · 查漏补缺 · 稳步提升</p></div>
        <nav className="flex rounded-xl bg-surface-100 dark:bg-surface-700 p-1 gap-0.5">
          {(['home', 'quiz', 'exam', 'history'] as const).map(key => (
            <button key={key} onClick={() => setActiveView(key)} className={`rounded-lg px-3.5 py-1.5 text-xs font-medium transition-all ${activeView === key ? 'bg-white dark:bg-surface-600 text-primary-600 dark:text-primary-400 shadow-soft' : 'text-surface-500 dark:text-gray-400 hover:text-surface-700 dark:hover:text-gray-200'}`}>
              {key === 'home' ? '首页' : key === 'quiz' ? '题目练习' : key === 'exam' ? '题集详情' : '错题与历史'}
            </button>
          ))}
        </nav>
      </div>

      {/* ═══════════ HOME ═══════════ */}
      {activeView === 'home' && (
        <div className="space-y-8">
          {loading ? (
            <div className="flex items-center justify-center py-24"><Loader2 className="h-6 w-6 animate-spin text-primary-500" /><span className="ml-3 text-sm text-surface-400">加载中...</span></div>
          ) : (
            <>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                <div><p className="mb-2 text-xs font-medium uppercase tracking-[0.22em] text-primary-500 dark:text-primary-400">PRACTICE CENTER / 练习中心</p><h1 className="text-3xl font-bold tracking-tight text-surface-800 dark:text-gray-100 md:text-4xl">把每一次练习，<span className="text-primary-500 dark:text-primary-400">变成进步。</span></h1></div>
                <p className="max-w-xs text-sm leading-6 text-surface-500 dark:text-gray-400">你的专属练习空间<br />今天也保持专注。</p>
              </div>

              {/* ── Stats strip ── */}
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-[repeat(3,1fr)_1.4fr]">
                {[
                  { l: '正确率', v: accuracy != null ? `${accuracy}%` : '-', c: accuracy != null && accuracy >= 60 ? 'text-success-600 dark:text-success-400' : 'text-error-600 dark:text-error-400' },
                  { l: '答题总量', v: `${totalAttempted}`, c: 'text-primary-600 dark:text-primary-400' },
                  { l: '薄弱点', v: `${weakCount}个`, c: 'text-error-600 dark:text-error-400' },
                ].map(item => (
                  <div key={item.l} className="bg-white dark:bg-surface-700 rounded-2xl p-5 shadow-soft"><p className="text-xs tracking-wide text-surface-400">{item.l}</p><strong className={`mt-1 block text-3xl font-semibold ${item.c}`}>{item.v}</strong></div>
                ))}
                {/* Sparkline — real data from analytics */}
                <div className="bg-white dark:bg-surface-700 rounded-2xl p-5 shadow-soft">
                  <div className="mb-2 flex justify-between text-xs text-surface-400"><span>近期活跃度</span><span className="text-surface-500">近 7 天</span></div>
                  <svg viewBox={`0 0 ${trend.length * 20} 58`} className="h-14 w-full" preserveAspectRatio="none">
                    <defs><linearGradient id="b" x1="0" x2="1"><stop stopColor="#3b82f6" /><stop offset="1" stopColor="#8b5cf6" /></linearGradient></defs>
                    {trend.map((h: number, i: number) => (
                      <rect key={i} x={i * 20 + 3} y={58 - Math.min(h, trendMax) * (55 / trendMax)} width="10" height={Math.max(Math.min(h, trendMax) * (55 / trendMax), 2)} rx="3" fill="url(#b)" opacity={0.45 + i / (trend.length * 2)} />
                    ))}
                  </svg>
                </div>
              </div>

              {/* ── Quick entries + Analytics sidebar ── */}
              <div className="grid gap-6 xl:grid-cols-[1.65fr_0.9fr]">
                <div className="grid gap-4 sm:grid-cols-2">
                  <HomeCard icon={Target} title="快速诊断" desc="自适应出题，找到薄弱点" action="开始诊断 →" color="primary" onClick={async () => {
                    if (!sessionId) { alert('请先开始一个学习会话（在聊天页面发送消息）后再使用此功能。'); return; }
                    try {
                      const res: any = await generateQuestions({ sessionId, message: '帮我诊断薄弱点' });
                      console.log('[诊断] 后端返回:', res);
                      const qs = res?.questions || (Array.isArray(res) ? res : []);
                      if (qs.length > 0) { setQuestions(qs); setCurrentIdx(0); setAnswers({}); setGrades({}); setActiveView('quiz'); }
                      else alert('AI 出题未返回题目，可能原因：1) AI 服务未就绪 2) 当前会话无法生成题目。请先确保在聊天页面已有对话记录。');
                    } catch (e: any) { alert('出题失败: ' + (e?.response?.data?.detail || e?.message || '请检查后端 AI 服务是否运行')); }
                  }} />
                  <HomeCard icon={BookOpen} title="自定义练习" desc="自选知识点、数量、题型" action="创建练习 →" color="accent" onClick={async () => {
                    if (!sessionId) { alert('请先开始一个学习会话后再使用此功能。'); return; }
                    try {
                      const res: any = await generateQuestions({ sessionId, message: '给我出几道题' });
                      console.log('[自定义] 后端返回:', res);
                      const qs = res?.questions || (Array.isArray(res) ? res : []);
                      if (qs.length > 0) { setQuestions(qs); setCurrentIdx(0); setAnswers({}); setGrades({}); setActiveView('quiz'); }
                      else alert('AI 出题未返回题目，请确保已在聊天页面有过对话，AI 会根据上下文出题。');
                    } catch (e: any) { alert('出题失败: ' + (e?.response?.data?.detail || e?.message || '')); }
                  }} />
                  <HomeCard icon={AlertCircle} title="错题重练" desc={weakCount > 0 ? `${weakCount}道错题待完成` : '暂无错题'} action={weakCount > 0 ? '开始重练 →' : '去诊断 →'} color="error" badge={weakCount > 0 ? weakCount : undefined} onClick={() => { if (weakCount > 0) { const wqs = (weakData?.records || []).map((r: any) => r.question).filter(Boolean); if (wqs.length > 0) { setQuestions(wqs); setCurrentIdx(0); setAnswers({}); setGrades({}); setActiveView('quiz'); } } }} />
                  <HomeCard icon={BarChart3} title="答题历史" desc={totalAttempted > 0 ? `${totalAttempted}题 · ${accuracy ?? '-'}%正确率` : '暂无记录'} action="查看记录 →" color="success" onClick={() => setActiveView('history')} />
                </div>
                {/* Analytics sidebar */}
                <div className="bg-white dark:bg-surface-700 rounded-2xl p-6 shadow-soft">
                  <p className="mb-4 text-[11px] font-semibold uppercase tracking-[0.24em] text-surface-400">学习概览</p>
                  <div className="flex items-center gap-5">
                    <div className="relative flex h-24 w-24 shrink-0 items-center justify-center">
                      <svg viewBox="0 0 100 100" className="h-24 w-24 -rotate-90">
                        <circle cx="50" cy="50" r="39" fill="none" stroke="rgba(59,130,246,.12)" strokeWidth="8" />
                        <circle cx="50" cy="50" r="39" fill="none" stroke="#3b82f6" strokeWidth="8" strokeLinecap="round" strokeDasharray="245" strokeDashoffset={accuracy != null ? String(245 - (accuracy / 100) * 245) : '245'} />
                      </svg>
                      <strong className="absolute text-lg text-surface-800 dark:text-gray-100">{accuracy != null ? `${accuracy}%` : '-'}</strong>
                    </div>
                    <div><p className="text-sm font-medium text-surface-800 dark:text-gray-100">{accuracy != null && accuracy >= 60 ? '表现不错' : '继续加油'}</p><p className="mt-1 text-xs leading-5 text-surface-500">保持这个节奏，你正在稳步提升。</p></div>
                  </div>
                  <div className="mt-6 space-y-3 border-t border-surface-100 dark:border-surface-600 pt-4">
                    {(historyData?.records || []).slice(0, 3).map((r: any, i: number) => {
                      const ok = r.grading_result?.total_score != null && r.grading_result.total_score >= 60;
                      return (<div key={i} className="flex items-center gap-3 text-xs"><span className={`h-2 w-2 shrink-0 rounded-full ${ok ? 'bg-success-400' : 'bg-error-400'}`} /><span className="min-w-0 flex-1 truncate text-surface-500">{r.question?.stem?.slice(0, 30) || '题目'}</span><strong className={`shrink-0 ${ok ? 'text-success-600 dark:text-success-400' : 'text-error-600 dark:text-error-400'}`}>{r.grading_result?.total_score != null ? `${r.grading_result.total_score}分` : '-'}</strong></div>);
                    })}
                    {(historyData?.records || []).length === 0 && <p className="text-xs text-surface-400 text-center py-2">暂无答题记录</p>}
                  </div>
                </div>
              </div>

              {/* ── Class practice ── */}
              {/* ── 班级练习 ── */}
              <div className="bg-white dark:bg-surface-700 rounded-2xl p-6 shadow-soft border-l-[3px] border-warning-400">
                <div className="mb-4 flex items-center gap-2"><GraduationCap size={18} className="text-warning-500" /><h3 className="font-semibold text-surface-800 dark:text-gray-100">班级练习</h3><span className="rounded-full bg-warning-50 dark:bg-warning-500/20 px-2.5 py-0.5 text-[11px] font-medium text-warning-600 dark:text-warning-300">教师推送</span></div>
                {pushedGroups.length > 0 ? (
                <div className="grid gap-3 md:grid-cols-2">
                  {pushedGroups.map((pg: any) => (
                    <div key={pg.pushId} onClick={() => { setQuestions(pg.questions || []); setCurrentIdx(0); setAnswers({}); setGrades({}); setActiveView('quiz'); }}
                      className="flex cursor-pointer items-center gap-4 rounded-xl border border-surface-200 dark:border-surface-600 bg-surface-50 dark:bg-surface-800 p-4 transition hover:border-warning-300 dark:hover:border-warning-500/50">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-warning-50 dark:bg-warning-500/20 text-warning-500"><ClipboardList size={18} /></div>
                      <div className="min-w-0 flex-1"><h4 className="truncate text-sm font-medium text-surface-800 dark:text-gray-100">{pg.title}</h4><p className="mt-0.5 text-xs text-surface-400">{pg.questions?.length || 0}道题</p></div>
                      <span className="shrink-0 text-xs text-surface-500">完成 <strong className="text-surface-700 dark:text-gray-200">{(pg.questions || []).filter((q: any) => q.answered).length}/{pg.questions?.length || 0}</strong></span>
                    </div>
                  ))}
                </div>
                ) : (
                  <p className="text-sm text-surface-400 text-center py-4">暂无班级练习</p>
                )}
              </div>

              {/* ── Exam Sets ── */}
              <div>
                <p className="mb-4 text-[11px] font-semibold uppercase tracking-[0.24em] text-surface-400">Exam Sets</p>
                {examSets.length > 0 ? (
                <div className="grid gap-4 lg:grid-cols-3">
                  {examSets.map(exam => {
                    let st = '未开始', sc = 'bg-surface-100 dark:bg-surface-600 text-surface-500 dark:text-gray-400', pct = 0, ft = '准备开始', btn = '开始作答', fill = 'bg-primary-400';
                    if (exam.status === 'in_progress') { st = '进行中'; sc = 'bg-primary-50 dark:bg-primary-500/20 text-primary-600 dark:text-primary-300'; pct = 47; ft = '进行中'; btn = '继续作答'; fill = 'bg-gradient-to-r from-primary-400 to-accent-400'; }
                    if (exam.status === 'completed') { st = '已完成'; sc = 'bg-success-50 dark:bg-success-500/20 text-success-600 dark:text-success-300'; pct = 100; ft = '已完成'; btn = '查看结果'; fill = 'bg-success-400'; }
                    return (<div key={exam.id} className="bg-white dark:bg-surface-700 rounded-2xl p-5 shadow-soft transition hover:shadow-elevated hover:-translate-y-0.5"><div className="flex items-center justify-between"><span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${sc}`}>{st}</span><span className="text-xs text-surface-400">{pct}%</span></div><h4 className="mt-4 text-[15px] font-semibold text-surface-800 dark:text-gray-100 line-clamp-2">{exam.title}</h4><p className="mt-1.5 text-xs text-surface-500">{exam.questionCount || '-'}题 · {exam.estimatedMinutes || '-'}分钟 · 100分</p><div className="mt-4 h-1.5 rounded-full bg-surface-100 dark:bg-surface-600 overflow-hidden"><div className={`h-full rounded-full transition-all duration-700 ${fill}`} style={{ width: `${pct}%` }} /></div><div className="mt-4 flex items-center justify-between"><span className="text-xs text-surface-400">{ft}</span><button onClick={(e) => { e.stopPropagation(); openExamSet(exam); }} className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${pct === 0 ? 'bg-gradient-to-r from-primary-500 to-accent-500 text-white shadow-sm hover:from-primary-600 hover:to-accent-600' : 'bg-surface-100 dark:bg-surface-600 text-surface-600 dark:text-gray-300 hover:bg-primary-50 dark:hover:bg-primary-500/20 hover:text-primary-600 dark:hover:text-primary-300'}`}>{btn}</button></div></div>);
                  })}
                </div>
                ) : (
                  <p className="text-sm text-surface-400 text-center py-8">暂无题集</p>
                )}
              </div>

              {/* ── 题目集 (display only) ── */}
              <div>
                <div className="mb-4 flex items-center gap-2"><span className="text-[11px] font-semibold uppercase tracking-[0.24em] text-surface-400">题目集</span><span className="rounded-full bg-primary-50 dark:bg-primary-500/20 px-2 py-0.5 text-[11px] text-primary-600 dark:text-primary-300">{sets.length}</span></div>
                {sets.length > 0 ? (
                <div className="space-y-2">
                  {sets.slice(0, 6).map((topic: any) => {
                    const pct = topic.count > 0 ? Math.round((topic.completed / topic.count) * 100) : 0;
                    return (<div key={topic.questionSetId} className="flex items-center gap-4 rounded-2xl bg-white dark:bg-surface-700 p-4 shadow-soft"><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-50 dark:bg-primary-500/20 text-primary-500"><Play size={17} fill="currentColor" /></div><div className="min-w-[160px] flex-1"><h4 className="text-sm font-medium text-surface-800 dark:text-gray-100 truncate">{topic.title}</h4><div className="mt-1.5 flex gap-1.5">{(topic.knowledgePoints || []).slice(0, 3).map((chip: string) => (<span key={chip} className="rounded-md bg-surface-100 dark:bg-surface-600 px-2 py-0.5 text-[10px] text-surface-500">{chip}</span>))}</div></div><div className="flex shrink-0 items-center gap-3"><div className="h-1.5 w-20 rounded-full bg-surface-100 dark:bg-surface-600 overflow-hidden"><div className="h-full rounded-full bg-gradient-to-r from-primary-400 to-accent-400" style={{ width: `${pct}%` }} /></div><span className="text-xs tabular-nums text-surface-600 dark:text-gray-300 w-8 text-right">{pct}%</span><ChevronRight size={16} className="text-surface-400" /></div></div>);
                  })}
                </div>
                ) : (
                  <p className="text-sm text-surface-400 text-center py-4">暂无题目集</p>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* ═══════════ QUIZ ═══════════ */}
      {activeView === 'quiz' && questions.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-center"><BookOpen size={48} className="text-surface-300 dark:text-surface-600 mb-4" /><h3 className="text-lg font-semibold text-surface-800 dark:text-gray-100 mb-1">暂无题目</h3><p className="text-sm text-surface-500 max-w-xs">请先在首页选择诊断出题或点击题集，题目将在这里展示。</p><button onClick={() => setActiveView('home')} className="mt-4 rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-primary-600 transition-colors">返回首页</button></div>
      )}
      {activeView === 'quiz' && questions.length > 0 && (() => {
        const i = currentIdx; const q = questions[i]; const a = q ? answers[q.question_id] || '' : ''; const g = q ? grades[q.question_id] : undefined;
        return (<div className="space-y-5">
          <div className="flex items-center justify-between"><div><p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-surface-400">{(activeExamSet ? 'Exam Set' : 'Quiz') + ' View'}</p><h2 className="text-xl font-semibold text-surface-800 dark:text-gray-100">题目练习 <span className="text-sm font-normal text-surface-500">/ {activeExamSet ? '题集训练' : '自适应训练'}</span></h2></div>{q && !g && a && <button onClick={handleSubmit} disabled={grading} className="rounded-lg bg-primary-500 px-3.5 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-primary-600 transition-colors">{grading ? '批改中...' : '提交批改'}</button>}</div>
          <div className="grid gap-5 lg:grid-cols-[160px_1fr]">
            <aside className="bg-white dark:bg-surface-700 rounded-2xl p-4 shadow-soft"><p className="mb-3 text-[10px] uppercase tracking-widest text-surface-400 font-semibold">题目列表</p><div className="space-y-0.5">{questions.map((qq, j) => { const gg = grades[qq.question_id]; const cur = j === i; let s = 'todo'; if (gg) s = gg.total_score != null && gg.total_score >= 60 ? 'correct' : 'wrong'; else if (cur) s = 'current'; return (<button key={qq.question_id} onClick={() => setCurrentIdx(j)} className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition ${s === 'current' ? 'bg-primary-50 dark:bg-primary-500/20 font-semibold text-primary-600 dark:text-primary-300' : 'text-surface-500 dark:text-gray-400 hover:bg-surface-50 dark:hover:bg-surface-600'}`}><span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${s === 'correct' ? 'bg-success-500 text-white' : s === 'wrong' ? 'bg-error-500 text-white' : s === 'current' ? 'bg-primary-500 text-white' : 'bg-surface-200 dark:bg-surface-600 text-surface-500'}`}>{s === 'correct' ? <Check size={10} /> : s === 'wrong' ? <X size={10} /> : j + 1}</span>第 {j + 1} 题</button>); })}</div></aside>
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-sm font-medium text-surface-700 dark:text-gray-200">#{i + 1} / {questions.length} 题</span>
                {q && (
                  <>
                    <span className="rounded-full bg-surface-100 dark:bg-surface-600 px-2.5 py-0.5 text-xs text-surface-600 dark:text-gray-300">{q.type === 'choice' ? '选择题' : q.type === 'truefalse' ? '判断题' : q.type === 'fill' ? '填空题' : '解答题'}</span>
                    {q.difficulty && (
                      <span className={`rounded-full px-2.5 py-0.5 text-xs ${q.difficulty === 'easy' ? 'bg-success-50 dark:bg-success-500/20 text-success-600 dark:text-success-300' : q.difficulty === 'hard' ? 'bg-error-50 dark:bg-error-500/20 text-error-600 dark:text-error-300' : 'bg-warning-50 dark:bg-warning-500/20 text-warning-600 dark:text-warning-300'}`}>{q.difficulty === 'easy' ? '简单' : q.difficulty === 'hard' ? '困难' : '中等'}</span>
                    )}
                  </>
                )}
                <div className="ml-auto h-1.5 w-28 rounded-full bg-surface-100 dark:bg-surface-600 overflow-hidden">
                  <div className="h-full rounded-full bg-gradient-to-r from-primary-400 to-accent-400 transition-all" style={{ width: `${questions.length > 0 ? ((i + 1) / questions.length) * 100 : 0}%` }} />
                </div>
              </div>
              <div className="bg-white dark:bg-surface-700 rounded-2xl p-6 shadow-soft md:p-8"><div className="max-w-4xl text-base leading-8 text-surface-800 dark:text-gray-100"><Markdown content={q?.stem || ''} /></div>{(q?.knowledge_points?.length ?? 0) > 0 && <div className="mt-4 flex flex-wrap gap-2">{q!.knowledge_points!.slice(0, 5).map((chip: string) => (<span key={chip} className="rounded-md bg-primary-50 dark:bg-primary-500/20 px-2.5 py-1 text-xs text-primary-600 dark:text-primary-300">{chip}</span>))}</div>}
                {q?.type === 'choice' && (<div className="mt-6 space-y-2.5">{(q.options || []).map((opt, oi) => { const letter = String.fromCharCode(65 + oi); const sel = a === letter; const done = !!g; let cls = 'border-surface-200 dark:border-surface-600 hover:border-primary-300 dark:hover:border-primary-500/50 bg-white dark:bg-surface-800'; if (done) { const ok = g.total_score != null && g.total_score >= 60; if (sel && ok) cls = 'border-success-400 bg-success-50/70 dark:bg-success-500/10'; else if (sel) cls = 'border-error-400 bg-error-50/70 dark:bg-error-500/10'; else if (letter === q.correct) cls = 'border-success-300 bg-success-50/30 dark:bg-success-500/5'; } else if (sel) cls = 'border-primary-400 bg-primary-50/70 dark:bg-primary-500/10'; return (<button key={letter} disabled={done} onClick={() => handleAnswer(letter)} className={`flex w-full items-center gap-3 rounded-xl border-2 px-5 py-3.5 text-sm transition-all ${cls} group`}><span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold ${done && sel && g.total_score != null && g.total_score >= 60 ? 'bg-success-500 text-white' : done && sel ? 'bg-error-500 text-white' : sel ? 'bg-primary-500 text-white' : 'bg-surface-100 dark:bg-surface-600 text-surface-500 group-hover:bg-primary-100 dark:group-hover:bg-primary-500/20 group-hover:text-primary-600 dark:group-hover:text-primary-300'}`}>{letter}</span><span className="flex-1 text-surface-700 dark:text-gray-200"><Markdown content={opt} /></span>{done && letter === q.correct && <Check size={16} className="shrink-0 text-success-500" />}{done && sel && letter !== q.correct && <X size={16} className="shrink-0 text-error-500" />}</button>); })}</div>)}
                {q?.type === 'truefalse' && (<div className="mt-6 flex gap-3">{['true', 'false'].map(v => { const sel = a === v; const done = !!g; const ok = done && v === q.correct; let cls = 'border-surface-200 dark:border-surface-600 hover:border-primary-300 dark:hover:border-primary-500/50 bg-white dark:bg-surface-800'; if (done && sel && ok) cls = 'border-success-400 bg-success-50/70 dark:bg-success-500/10'; else if (done && sel) cls = 'border-error-400 bg-error-50/70 dark:bg-error-500/10'; else if (sel) cls = 'border-primary-400 bg-primary-50/70 dark:bg-primary-500/10'; return <button key={v} disabled={done} onClick={() => handleAnswer(v)} className={`flex-1 rounded-xl border-2 px-6 py-5 text-center text-base font-medium transition-all ${cls} text-surface-700 dark:text-gray-200`}>{v === 'true' ? '✓ 正确' : '✗ 错误'}</button>; })}</div>)}
                {(q?.type === 'fill' || q?.type === 'shortanswer') && (<div className="mt-6"><label className="block text-xs font-medium text-surface-400 mb-1.5" htmlFor="ans">解题过程</label><textarea id="ans" value={a} onChange={e => handleAnswer(e.target.value)} disabled={!!g} rows={q?.type === 'shortanswer' ? 8 : 3} placeholder="输入你的解题过程…" className="w-full resize-none rounded-xl border-2 border-surface-200 dark:border-surface-600 bg-surface-50 dark:bg-surface-800 p-4 text-sm leading-6 text-surface-700 dark:text-gray-200 outline-none placeholder:text-surface-400 focus:border-primary-400 dark:focus:border-primary-500/50 disabled:opacity-60 transition-colors" /></div>)}
              </div>
              {g && (<div className={`rounded-2xl border-2 p-5 ${g.total_score != null && g.total_score >= 60 ? 'border-success-200 dark:border-success-500/30 bg-success-50/50 dark:bg-success-500/10' : 'border-error-200 dark:border-error-500/30 bg-error-50/50 dark:bg-error-500/10'}`}><div className="flex items-center gap-3"><strong className={`text-3xl ${g.total_score != null && g.total_score >= 60 ? 'text-success-600' : 'text-error-600'}`}>{g.total_score != null ? `${g.total_score} 分` : '已批改'}</strong><span className={`text-sm ${g.total_score != null && g.total_score >= 60 ? 'text-success-500' : 'text-error-500'}`}>{g.total_score != null && g.total_score >= 60 ? '正确' : '有误'}</span></div>{g.error_type !== 'null' && <p className="mt-2 text-xs text-surface-500">错误类型：<span className="font-medium text-error-600">{g.error_label}</span></p>}{g.error_explanation && <p className="mt-2 text-sm text-surface-600 dark:text-gray-300">{g.error_explanation}</p>}{g.suggestions?.[0] && <p className="mt-2 text-sm text-primary-600">💡 {g.suggestions[0]}</p>}</div>)}
              <div className="flex items-center justify-between rounded-2xl bg-white dark:bg-surface-700 px-4 py-3 shadow-soft"><button onClick={() => i > 0 && setCurrentIdx(j => j - 1)} disabled={i === 0} className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm text-surface-500 hover:text-surface-700 dark:hover:text-gray-200 disabled:opacity-30 transition-colors"><ArrowLeft size={16} /> 上一题</button><div className="flex items-center gap-2">{activeExamSet && <button onClick={async () => { if (!examSetAttemptId) return; try { await updateAttempt(examSetAttemptId, { answers: examSetQuestions.map(qq => ({ questionId: qq.question_id, answer: answers[qq.question_id] || '' })), status: 'in_progress' }); } catch {} } } className="rounded-lg bg-surface-100 dark:bg-surface-600 px-3 py-1.5 text-xs text-surface-600 dark:text-gray-300 hover:bg-surface-200 dark:hover:bg-surface-500 transition-colors">保存进度</button>}{!activeExamSet && !g && a && <button onClick={handleSubmit} disabled={grading} className="rounded-lg bg-primary-500 px-4 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-primary-600 transition-colors">{grading ? '批改中…' : '提交批改'}</button>}{!activeExamSet && g && <button onClick={() => { if (q) { setGrades(gg => { const n = { ...gg }; delete n[q.question_id]; return n; }); setAnswers(aa => { const n = { ...aa }; delete n[q.question_id]; return n; }); } } } className="flex items-center gap-1 rounded-lg bg-surface-100 dark:bg-surface-600 px-3 py-1.5 text-xs text-surface-600 dark:text-gray-300 hover:bg-surface-200 dark:hover:bg-surface-500 transition-colors"><RefreshCw size={14} /> 重做</button>}{activeExamSet && <button onClick={submitExamSetAnswers} disabled={grading} className="rounded-lg bg-gradient-to-r from-primary-500 to-accent-500 px-4 py-1.5 text-sm font-medium text-white shadow-sm hover:from-primary-600 hover:to-accent-600 transition-all">{grading ? '批改中…' : '提交全部'}</button>}</div><button onClick={() => i < questions.length - 1 && setCurrentIdx(j => j + 1)} disabled={i >= questions.length - 1} className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm text-surface-500 hover:text-surface-700 dark:hover:text-gray-200 disabled:opacity-30 transition-colors">下一题 <ArrowRight size={16} /></button></div>
            </div>
          </div>
        </div>);
      })()}

      {/* ═══════════ EXAM ═══════════ */}
      {activeView === 'exam' && !activeExamSet && (
        <div className="flex flex-col items-center justify-center py-20 text-center"><ClipboardList size={48} className="text-surface-300 dark:text-surface-600 mb-4" /><h3 className="text-lg font-semibold text-surface-800 dark:text-gray-100 mb-1">未选择题集</h3><p className="text-sm text-surface-500 max-w-xs">请先在首页点击一个题集，详情将在这里展示。</p><button onClick={() => setActiveView('home')} className="mt-4 rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-primary-600 transition-colors">返回首页</button></div>
      )}
      {activeView === 'exam' && activeExamSet && (
        <div className="space-y-6">
          <button onClick={() => setActiveView('home')} className="flex items-center gap-1.5 text-sm text-surface-500 hover:text-surface-700 dark:hover:text-gray-200 transition-colors"><ArrowLeft size={16} /> 返回首页</button>
          <div className="bg-white dark:bg-surface-700 rounded-2xl p-6 shadow-soft md:p-8"><div className="flex flex-wrap items-start gap-4"><div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-primary-50 dark:bg-primary-500/20 text-primary-500"><ClipboardList size={24} /></div><div className="flex-1"><div className="flex flex-wrap items-center gap-2"><h3 className="text-xl font-semibold text-surface-800 dark:text-gray-100">{activeExamSet.title}</h3><span className={`rounded-full px-2.5 py-0.5 text-xs ${activeExamSet.status === 'completed' ? 'bg-success-50 dark:bg-success-500/20 text-success-600 dark:text-success-300' : activeExamSet.status === 'in_progress' ? 'bg-primary-50 dark:bg-primary-500/20 text-primary-600 dark:text-primary-300' : 'bg-surface-100 dark:bg-surface-600 text-surface-500'}`}>{activeExamSet.status === 'completed' ? '已完成' : activeExamSet.status === 'in_progress' ? '进行中' : '未开始'}</span></div><p className="mt-1.5 text-sm text-surface-500">{activeExamSet.questionCount || '-'}题 · {activeExamSet.estimatedMinutes || '-'}分钟 · 100分</p></div></div>
            <div className="my-6 flex flex-wrap items-center justify-between gap-4 border-t border-surface-100 dark:border-surface-600 pt-5"><div><p className="text-xs text-surface-500">上次成绩</p><strong className={`mt-0.5 block text-2xl ${examSetTotalScore != null ? (examSetTotalScore >= 60 ? 'text-success-600' : 'text-error-600') : 'text-surface-400'}`}>{examSetTotalScore != null ? `${examSetTotalScore}分` : '-'}</strong></div><div className="flex gap-3">{examSetAttempts.some(a => a.status === 'in_progress') ? <button onClick={continueExamSet} className="rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-primary-600 transition-colors">继续作答</button> : <button onClick={startExamSet} className="rounded-lg bg-primary-500 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-primary-600 transition-colors">开始作答</button>}{examSetSubmitted && <button onClick={startExamSet} className="rounded-lg bg-surface-100 dark:bg-surface-600 px-4 py-2 text-sm text-surface-600 dark:text-gray-300 hover:bg-surface-200 dark:hover:bg-surface-500 transition-colors">再次作答</button>}</div></div></div>
          <div className="grid gap-6 lg:grid-cols-[0.75fr_1.25fr]">
            <div className="bg-white dark:bg-surface-700 rounded-2xl p-6 shadow-soft"><p className="mb-4 text-[11px] font-semibold uppercase tracking-[0.24em] text-surface-400">答题结果</p><div className="flex items-center gap-6"><div className={`flex h-24 w-24 shrink-0 items-center justify-center rounded-full border-8 text-3xl font-bold ${examSetTotalScore != null && examSetTotalScore >= 60 ? 'border-success-200 dark:border-success-500/30 text-success-600' : examSetTotalScore != null ? 'border-error-200 dark:border-error-500/30 text-error-600' : 'border-surface-200 dark:border-surface-600 text-surface-400'}`}>{examSetTotalScore ?? '-'}</div><div><p className="text-sm font-medium text-surface-800 dark:text-gray-100">{examSetTotalScore != null && examSetTotalScore >= 60 ? '本次表现良好' : examSetTotalScore != null ? '需要加强' : '暂无成绩'}</p><p className="mt-1 text-xs text-surface-500">{examSetWeakPoints.length > 0 ? '还有一些关键概念需要巩固' : examSetTotalScore != null ? '继续保持！' : '完成作答后可查看成绩'}</p></div></div>{examSetWeakPoints.length > 0 && (<div className="mt-5 space-y-2.5 border-t border-surface-100 dark:border-surface-600 pt-4"><p className="text-xs font-medium text-surface-500">薄弱知识点</p>{examSetWeakPoints.map((wp: any, i: number) => (<div key={i} className="flex items-center gap-3 text-sm"><span className="h-2 w-2 shrink-0 rounded-full bg-error-400" /><span className="flex-1 text-surface-600 dark:text-gray-300">{typeof wp === 'string' ? wp : wp.name || wp.point || ''}</span><span className="rounded-full bg-error-50 dark:bg-error-500/20 px-2 py-0.5 text-xs text-error-600 dark:text-error-300">错{i + 1}次</span></div>))}</div>)}</div>
            <div className="bg-white dark:bg-surface-700 rounded-2xl p-6 shadow-soft"><p className="mb-4 text-[11px] font-semibold uppercase tracking-[0.24em] text-surface-400">作答记录</p>{examSetAttempts.length === 0 ? <p className="py-6 text-center text-sm text-surface-400">暂无作答记录</p> : examSetAttempts.map((a, i) => (<div key={a.attemptId} className={`flex items-center gap-4 rounded-xl p-3.5 ${i % 2 ? 'bg-surface-50 dark:bg-surface-800' : ''}`}><span className="text-sm font-semibold text-surface-700 dark:text-gray-200">#{a.attemptNumber || i + 1}</span><span className="flex-1 text-xs text-surface-500">{a.submittedAt ? new Date(a.submittedAt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit' }) : a.startedAt ? new Date(a.startedAt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit' }) : '-'}</span><span className={`rounded-full px-2 py-0.5 text-xs ${a.status === 'completed' ? 'bg-success-50 dark:bg-success-500/20 text-success-600 dark:text-success-300' : a.status === 'in_progress' ? 'bg-primary-50 dark:bg-primary-500/20 text-primary-600 dark:text-primary-300' : 'bg-surface-100 dark:bg-surface-600 text-surface-500'}`}>{a.status === 'completed' ? '已完成' : a.status === 'in_progress' ? '进行中' : '未完成'}</span><strong className="text-sm text-surface-700 dark:text-gray-200">{a.totalScore != null ? `${a.totalScore}分` : '-'}</strong></div>))}</div>
          </div>
        </div>
      )}

      {/* ═══════════ HISTORY ═══════════ */}
      {activeView === 'history' && (
        <div className="space-y-5">
          <div><p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-surface-400">Weak Points & History View</p><h2 className="text-xl font-semibold text-surface-800 dark:text-gray-100">错题与历史</h2></div>
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="bg-white dark:bg-surface-700 rounded-2xl p-6 shadow-soft border-l-[3px] border-error-300 dark:border-error-500/50"><div className="mb-4 flex items-center justify-between"><h3 className="text-lg font-semibold text-surface-800 dark:text-gray-100">错题本</h3><span className="rounded-full bg-error-50 dark:bg-error-500/20 px-2.5 py-0.5 text-xs text-error-600 dark:text-error-300">{weakCount}</span></div>{!weakData?.records?.length ? <p className="py-6 text-center text-sm text-surface-400">暂无错题 👍</p> : (<div className="space-y-3">{(weakData.records as any[]).slice(0, 8).map((r: any, i: number) => (<div key={i} className="rounded-xl border border-error-100 dark:border-error-500/20 bg-error-50/30 dark:bg-error-500/5 p-4"><p className="truncate text-sm text-surface-700 dark:text-gray-200"><Markdown content={r.question?.stem || '题目'} /></p><div className="mt-2.5 flex flex-wrap items-center gap-3 text-xs"><span className="text-error-600 dark:text-error-400">你的答案: {r.last_answer || '-'}</span>{r.question?.correct && <span className="text-success-600 dark:text-success-400">正确答案: {r.question.correct}</span>}{r.grading_result?.error_label && <span className="rounded-md bg-error-50 dark:bg-error-500/20 px-2 py-0.5 text-error-600">{r.grading_result.error_label}</span>}</div>{r.grading_result?.error_explanation && <p className="mt-2 text-xs leading-5 text-surface-500">{r.grading_result.error_explanation}</p>}</div>))}</div>)}</div>
            <div className="bg-white dark:bg-surface-700 rounded-2xl p-6 shadow-soft"><div className="mb-4"><h3 className="text-lg font-semibold text-surface-800 dark:text-gray-100">答题历史</h3><p className="mt-1.5 text-sm text-surface-500">{totalAttempted}题 · 正确{totalCorrect}题 · 错误{totalAttempted - totalCorrect}题</p></div>{!historyData?.records?.length ? <p className="py-6 text-center text-sm text-surface-400">暂无记录</p> : (<div className="max-h-[360px] overflow-auto space-y-0.5">{(historyData.records as any[]).map((r: any, i: number) => { const ok = r.grading_result?.total_score != null && r.grading_result.total_score >= 60; return (<div key={i} className={`flex items-center gap-3 rounded-lg p-3 ${i % 2 ? 'bg-surface-50 dark:bg-surface-800' : ''}`}><span className={`h-2 w-2 shrink-0 rounded-full ${ok ? 'bg-success-400' : 'bg-error-400'}`} /><p className="min-w-0 flex-1 truncate text-sm text-surface-600 dark:text-gray-300">{r.question?.stem?.slice(0, 60) || '题目'}</p><span className={`shrink-0 rounded-md px-2 py-0.5 text-xs font-medium ${ok ? 'bg-success-50 dark:bg-success-500/20 text-success-600' : 'bg-error-50 dark:bg-error-500/20 text-error-600'}`}>{r.grading_result?.total_score != null ? `${r.grading_result.total_score}分` : '-'}</span><time className="hidden shrink-0 text-xs text-surface-400 sm:block">{r.created_at ? new Date(r.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit' }) : ''}</time></div>); })}</div>)}</div>
          </div>
        </div>
      )}
    </div>
  );
}

function HomeCard({ icon: Icon, title, desc, action, color, badge, onClick }: {
  icon: typeof Target; title: string; desc: string; action: string; color: 'primary' | 'accent' | 'error' | 'success'; badge?: number; onClick: () => void;
}) {
  const c = { primary: 'bg-primary-50 dark:bg-primary-500/20 text-primary-600 dark:text-primary-300', accent: 'bg-accent-50 dark:bg-accent-500/20 text-accent-600 dark:text-accent-300', error: 'bg-error-50 dark:bg-error-500/20 text-error-600 dark:text-error-300', success: 'bg-success-50 dark:bg-success-500/20 text-success-600 dark:text-success-300' }[color];
  return (<button onClick={onClick} className="group relative overflow-hidden rounded-2xl border border-surface-200 dark:border-surface-600 bg-white dark:bg-surface-700 p-5 text-left shadow-soft transition-all duration-300 hover:shadow-elevated hover:-translate-y-0.5"><div className={`mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl ${c}`}><Icon size={20} /></div><h3 className="font-semibold text-surface-800 dark:text-gray-100">{title}</h3><p className="mt-1 text-xs text-surface-500">{desc}</p><div className={`mt-3 flex items-center gap-1 text-xs font-medium ${c} opacity-0 group-hover:opacity-100 transition-opacity`}>{action}</div>{badge != null && badge > 0 && <span className="absolute right-3 top-3 flex h-5 w-5 items-center justify-center rounded-full bg-error-500 text-[10px] font-bold text-white">{badge}</span>}</button>);
}
