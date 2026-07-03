import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useChatStore } from '../store/chatStore';
import { Target, BookOpen, AlertCircle, BarChart3, Play, Loader2, ChevronLeft, ChevronRight, Check, X, RefreshCw, Edit3, Users, GraduationCap } from 'lucide-react';
import Markdown from '../utils/markdown';
import { listQuestions, gradeAnswer, getWeakQuestions, getAnswerHistory, getQuestionSets } from '../api/chat';
import { getPushedQuestions } from '../api/classSubjects';
import type { PushedQuestionGroup } from '../types/classSubject';
import { getCurrentLearner } from '../store/authStore';
import { useSubjectStore } from '../store/subjectStore';

interface Question {
  question_id: string; type: string; stem: string; options?: string[];
  difficulty?: string; knowledge_points?: string[];
  correct?: string; explanation?: string;
}
interface GradingResult { total_score: number | null; dimension_scores: Record<string, number | null>; dimension_feedback: Record<string, string>; error_type: string; error_label: string; error_explanation: string; suggestions: string[]; }
interface QuestionSet { questionSetId: string; title: string; knowledgePoints: string[]; count: number; completed: number; createdAt: number; }

export default function PracticePage() {
  const nav = useNavigate();
  const isParent = getCurrentLearner()?.role === 'parent';

  if (isParent) {
    return (
      <div className="p-6 h-full flex items-center justify-center animate-fade-in">
        <div className="text-center max-w-md">
          <div className="w-16 h-16 rounded-2xl bg-surface-100 dark:bg-surface-700 flex items-center justify-center mx-auto mb-4">
            <Edit3 className="w-8 h-8 text-surface-400" />
          </div>
          <h3 className="font-display text-lg font-semibold text-surface-800 dark:text-gray-100 mb-2">只读模式</h3>
          <p className="text-surface-500 dark:text-gray-400 text-sm">家长账户无法使用练习功能。<br/>请前往学习分析查看孩子的答题情况。</p>
        </div>
      </div>
    );
  }
  const sessionId = useChatStore((s) => s.currentSessionId);
  const [view, setView] = useState<'home' | 'quiz' | 'weak' | 'history'>('home');
  const [sets, setSets] = useState<QuestionSet[]>([]);
  const [activeSetId, setActiveSetId] = useState<string>('');
  const [questions, setQuestions] = useState<Question[]>([]);
  const [allQuestions, setAllQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [grades, setGrades] = useState<Record<string, GradingResult>>({});
  const [currentIdx, setCurrentIdx] = useState(0);
  const [grading, setGrading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<any>(null);
  const [weakData, setWeakData] = useState<any>(null);
  const [historyData, setHistoryData] = useState<any>(null);
  const [pushedGroups, setPushedGroups] = useState<PushedQuestionGroup[]>([]);
  const [classSubjectId, setClassSubjectId] = useState<string>('');
  const [searchParams] = useSearchParams();

  useEffect(() => {
    // Read from URL first, fall back to store (persists across navigations)
    const csid = searchParams.get('classSubjectId') || useSubjectStore.getState().activeClassSubject?.id || '';
    setClassSubjectId(csid);
    Promise.all([
      getQuestionSets(sessionId).then((d: any) => d?.sets || []).catch(() => []),
      getAnswerHistory(sessionId).then((d: any) => { setStats(d); setHistoryData(d); }).catch(() => {}),
      getWeakQuestions(sessionId).then(setWeakData).catch(() => {}),
      csid ? getPushedQuestions(csid).then(setPushedGroups).catch(() => {}) : Promise.resolve(),
    ]).then(([s]) => setSets(s)).finally(() => setLoading(false));
  }, []);

  const loadSet = async (qsid: string) => {
    setActiveSetId(qsid);
    const res: any = await listQuestions(sessionId);
    const qs = (res?.questions || []).filter((q: any) => q.question_set_id === qsid);
    setAllQuestions(qs);
    setQuestions(qs);
    setCurrentIdx(0);
    // 从 localStorage 恢复答题状态
    const saved = localStorage.getItem(`practice_answers_${sessionId}`);
    const savedAnswers = saved ? JSON.parse(saved) : {};
    setAnswers(savedAnswers);
    // 从历史记录恢复已判卷结果
    getAnswerHistory(sessionId).then((d: any) => {
      if (d?.records) {
        const prevGrades: Record<string, GradingResult> = {};
        d.records.forEach((r: any) => {
          if (r.question_id && r.grading_result) prevGrades[r.question_id] = r.grading_result;
        });
        setGrades(prevGrades);
      }
    }).catch(() => {});
    setView('quiz');
  };

  const startDiagnostic = () => nav(`/chat?prompt=帮我诊断薄弱点`);
  const startCustom = () => nav('/chat?prompt=给我出几道题');
  const totalAttempted = stats?.totalAttempted || 0;
  const totalCorrect = stats?.totalCorrect || 0;
  const weakCount = weakData?.records?.length || 0;
  const accuracy = totalAttempted > 0 ? Math.round((totalCorrect / totalAttempted) * 100) : null;

  // ── Home ──
  if (view === 'home') {
    return (
      <div className="p-6 animate-fade-in h-full flex flex-col">
        <h2 className="font-display text-xl font-bold text-surface-800 mb-6">练习中心</h2>
        <div className="flex gap-6 flex-1 min-h-0">
          {/* 左：题目集 + 快捷卡片 */}
          <div className="flex-1 flex flex-col min-w-0 gap-4">
            {/* 快捷入口 */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <QuickCard icon={Target} title="快速诊断" desc="自适应出题找薄弱点" color="bg-primary-50 text-primary-600" onClick={startDiagnostic} />
              <QuickCard icon={BookOpen} title="自定义练习" desc="自选知识点数量题型" color="bg-accent-50 text-accent-600" onClick={startCustom} />
              <QuickCard icon={AlertCircle} title="错题重练" desc={weakCount > 0 ? `共${weakCount}道错题` : '暂无错题'} color="bg-error-50 text-error-600" onClick={() => weakCount > 0 ? setView('weak') : startDiagnostic()} badge={weakCount} />
              <QuickCard icon={BarChart3} title="答题历史" desc={`${totalAttempted}题·${accuracy ?? '-'}%`} color="bg-success-50 text-success-600" onClick={() => setView('history')} />
            </div>

            {/* 班级练习（教师推送） */}
            {pushedGroups.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-surface-600 mb-3 flex items-center gap-1.5">
                  <GraduationCap size={14} className="text-amber-500" /> 班级练习
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium">教师推送</span>
                </h3>
                <div className="space-y-2">
                  {pushedGroups.map((pg) => (
                    <button key={pg.pushId} onClick={() => { setAllQuestions(pg.questions as any); setQuestions(pg.questions as any); setCurrentIdx(0); setAnswers({}); setGrades({}); setView('quiz'); }}
                      className="w-full flex items-center gap-4 p-4 bg-white rounded-xl border border-amber-200 hover:border-amber-400 hover:shadow-soft transition-all text-left border-l-4 border-l-amber-400">
                      <Users className="w-5 h-5 text-amber-500 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-surface-700 truncate">{pg.title}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-xs text-surface-400">{pg.questions.length} 题</span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-600">教师推送</span>
                        </div>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <span className="text-xs text-surface-400">
                          {pg.questions.filter(q => q.answered).length}/{pg.questions.length} 完成
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* 题目集列表 */}
            <div className="flex-1 min-h-0">
              <h3 className="text-sm font-semibold text-surface-600 mb-3">题目集</h3>
              {loading ? <Loader2 className="w-5 h-5 animate-spin text-surface-400" /> : sets.length === 0 ? (
                <p className="text-sm text-surface-400">暂无题目集。在对话中说"给我出几道题"开始吧</p>
              ) : (
                <div className="space-y-2 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 360px)' }}>
                  {sets.map(s => (
                    <button key={s.questionSetId} onClick={() => loadSet(s.questionSetId)}
                      className="w-full flex items-center gap-4 p-4 bg-white rounded-xl border border-surface-200 hover:border-primary-300 hover:shadow-soft transition-all text-left">
                      <Play className="w-5 h-5 text-primary-500 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-surface-700 truncate">{s.title}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-xs text-surface-400">{s.count} 题</span>
                          {s.completed > 0 && <span className="text-xs text-success-500">{s.completed} 已完成</span>}
                          {s.knowledgePoints?.slice(0, 2).map((kp: string, i: number) => (
                            <span key={i} className="text-[10px] px-1.5 py-0.5 rounded-full bg-surface-100 text-surface-500">{kp}</span>
                          ))}
                        </div>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <div className="h-1.5 w-24 bg-surface-100 rounded-full overflow-hidden">
                          <div className="h-full bg-primary-500 rounded-full" style={{ width: `${s.count > 0 ? (s.completed / s.count) * 100 : 0}%` }} />
                        </div>
                        <span className="text-[10px] text-surface-400">{s.count > 0 ? Math.round((s.completed / s.count) * 100) : 0}%</span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* 右：统计 */}
          <div className="w-48 flex-shrink-0 space-y-3">
            <StatBlock title="正确率" value={accuracy !== null ? `${accuracy}%` : '-'} color="text-success-500" />
            <StatBlock title="薄弱点" value={`${weakCount}`} color="text-error-500" />
            <StatBlock title="总答题" value={`${totalAttempted}`} color="text-primary-500" />
            {historyData?.records?.slice(0, 5).map((r: any, i: number) => (
              <div key={i} className="text-xs truncate">
                <span className={r.grading_result?.total_score >= 60 ? 'text-success-500' : 'text-error-500'}>
                  {r.grading_result?.total_score >= 60 ? '✓' : '✗'}
                </span>
                <span className="text-surface-400 ml-1">{r.question?.stem?.slice(0, 15) || '题目'} {r.grading_result?.total_score ?? '-'}分</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ── Quiz ──
  const currentQ = questions[currentIdx];
  const answer = answers[currentQ?.question_id || ''] || '';
  const grade = grades[currentQ?.question_id || ''];
  const handleAnswer = (val: string) => {
    if (!currentQ) return;
    setAnswers(a => {
      const updated = { ...a, [currentQ.question_id]: val };
      localStorage.setItem(`practice_answers_${sessionId}`, JSON.stringify(updated));
      return updated;
    });
  };
  const handleSubmit = async () => {
    if (!currentQ || !answer || grading) return;
    setGrading(true);
    try {
      const res: any = await gradeAnswer(currentQ.question_id, answer, sessionId);
      if (res?.gradingResult) setGrades(g => ({ ...g, [currentQ.question_id]: res.gradingResult }));
    } catch {}
    setGrading(false);
  };

  if (view === 'quiz') {
    return (
      <div className="p-6 h-full flex flex-col animate-fade-in max-h-screen">
        <button onClick={() => setView('home')} className="text-sm text-surface-500 hover:text-surface-700 mb-4 flex-shrink-0"><ChevronLeft className="w-4 h-4 inline" /> 返回</button>
        <div className="flex gap-4 flex-1 min-h-0 overflow-hidden">
          {/* 左侧题号列表 */}
          <div className="w-52 flex-shrink-0 bg-white rounded-2xl shadow-soft p-3 overflow-y-auto">
            <p className="text-[10px] text-surface-400 uppercase tracking-wider mb-2 font-semibold">题目列表</p>
            {questions.map((q, i) => {
              const g = grades[q.question_id];
              const isCurrent = i === currentIdx;
              let dot = '○';
              let cls = 'text-surface-400';
              if (g) { dot = g.total_score !== null && g.total_score >= 60 ? '✓' : '✗'; cls = g.total_score !== null && g.total_score >= 60 ? 'text-success-500' : 'text-error-500'; }
              if (isCurrent) cls = 'text-primary-600 font-bold';
              return (
                <button key={q.question_id} onClick={() => setCurrentIdx(i)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm hover:bg-surface-50 transition-colors ${isCurrent ? 'bg-primary-50 font-medium' : ''}`}>
                  <span className={cls}>{dot}</span>
                  <span className="truncate text-surface-500">第{i + 1}题</span>
                </button>
              );
            })}
          </div>

          {/* 右侧题目区 */}
          <div className="flex-1 flex flex-col min-w-0 min-h-0">
            <div className="flex items-center justify-between mb-3 flex-shrink-0">
              <div className="flex items-center gap-3">
                <span className="text-lg font-bold text-primary-600">#{currentIdx + 1}</span>
                <span className="text-sm text-surface-400">/ {questions.length} 题</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary-50 text-primary-600 font-medium">
                  {currentQ?.type === 'choice' ? '选择题' : currentQ?.type === 'truefalse' ? '判断题' : currentQ?.type === 'fill' ? '填空题' : '解答题'}
                </span>
                {currentQ?.difficulty && (
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${currentQ?.difficulty === 'easy' ? 'bg-success-50 text-success-600' : currentQ?.difficulty === 'hard' ? 'bg-error-50 text-error-600' : 'bg-warning-50 text-warning-600'}`}>
                    {currentQ?.difficulty === 'easy' ? '简单' : currentQ?.difficulty === 'hard' ? '困难' : '中等'}
                  </span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2 mb-6 flex-shrink-0">
              <div className="flex-1 h-2 bg-surface-100 rounded-full overflow-hidden"><div className="h-full bg-gradient-to-r from-primary-500 to-accent-500 rounded-full transition-all duration-500" style={{ width: `${questions.length>0?((currentIdx+1)/questions.length)*100:0}%` }} /></div>
              <span className="text-xs text-surface-400 tabular-nums w-10 text-right">{questions.length>0?Math.round(((currentIdx+1)/questions.length)*100):0}%</span>
            </div>

            <div className="flex-1 overflow-y-auto min-h-0 pb-2">
              <div className="bg-white rounded-2xl shadow-soft p-8 mb-6">
                <div className="text-xl font-semibold text-surface-800 mb-2 leading-relaxed"><Markdown content={currentQ?.stem || ''} /></div>
                {currentQ?.knowledge_points && currentQ.knowledge_points.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-6">
                    {currentQ.knowledge_points.slice(0,4).map((kp: string, i: number) => (
                      <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-surface-100 text-surface-500">{kp}</span>
                    ))}
                  </div>
                )}
                <div className="space-y-3">
                {currentQ?.type === 'choice' && currentQ.options?.map((opt: string, i: number) => {
                  const letter = String.fromCharCode(65 + i); const sel = answer === letter; const done = !!grade;
                  let cls = 'border-2 hover:shadow-sm';
                  if (done && grade?.total_score === 100 && sel) cls += ' border-success-400 bg-success-50/70';
                  else if (done && sel && grade?.total_score !== 100) cls += ' border-error-400 bg-error-50/70';
                  else if (sel) cls += ' border-primary-400 bg-primary-50/70';
                  else cls += ' border-surface-200 hover:border-primary-300 bg-white';
                  return <button key={letter} disabled={done} onClick={() => handleAnswer(letter)} className={`w-full text-left px-5 py-4 rounded-xl transition-all flex items-center gap-3 group ${cls}`}><span className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0 transition-colors ${sel && !done ? 'bg-primary-500 text-white' : done && grade?.total_score === 100 && sel ? 'bg-success-500 text-white' : done && sel ? 'bg-error-500 text-white' : 'bg-surface-100 text-surface-500 group-hover:bg-primary-100 group-hover:text-primary-600'}`}>{letter}</span><span className="text-sm"><Markdown content={opt} /></span>{done && letter === (currentQ?.correct || '') && <Check className="w-4 h-4 text-success-500 ml-auto" />}{done && sel && letter !== (currentQ?.correct || '') && <X className="w-4 h-4 text-error-500 ml-auto" />}</button>;
                })}
                {currentQ?.type === 'truefalse' && <div className="flex gap-4">{['true','false'].map(v => { const sel = answer === v; const done = !!grade; let cls = 'border-2'; if (done && grade?.total_score === 100 && sel) cls += ' border-success-400 bg-success-50/70'; else if (done && sel) cls += ' border-error-400 bg-error-50/70'; else if (sel) cls += ' border-primary-400 bg-primary-50/70'; else cls += ' border-surface-200 hover:border-primary-300'; const label = v === 'true' ? '✓ 正确' : '✗ 错误'; return <button key={v} disabled={done} onClick={() => handleAnswer(v)} className={`flex-1 px-6 py-5 rounded-xl text-lg font-medium transition-all ${cls}`}>{label}</button>; })}</div>}
                {(currentQ?.type === 'fill' || currentQ?.type === 'shortanswer') && <textarea value={answer} onChange={e => handleAnswer(e.target.value)} disabled={!!grade} rows={currentQ?.type === 'shortanswer' ? 8 : 2} placeholder="输入你的答案…" className="w-full px-5 py-4 bg-surface-50 border-2 border-surface-200 rounded-xl resize-none focus:border-primary-400 focus:outline-none disabled:opacity-60 text-sm" />}
                </div>
              </div>

              {grade && (
                <div className={`p-5 rounded-2xl mb-6 border-2 animate-fade-in-up ${grade.total_score !== null && grade.total_score >= 60 ? 'bg-success-50/50 border-success-200' : 'bg-error-50/50 border-error-200'}`}>
                  <div className="flex items-center gap-3 mb-3">
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center ${grade.total_score !== null && grade.total_score >= 60 ? 'bg-success-100' : 'bg-error-100'}`}>
                      {grade.total_score !== null && grade.total_score >= 60 ? <Check className="w-5 h-5 text-success-600" /> : <X className="w-5 h-5 text-error-500" />}
                    </div>
                    <div>
                      <span className="text-lg font-bold">{grade.total_score !== null ? `${grade.total_score} 分` : '已批改'}</span>
                      {grade.error_type !== 'null' && <span className="ml-2 text-xs px-1.5 py-0.5 rounded-full bg-error-100 text-error-600">{grade.error_label}</span>}
                    </div>
                  </div>
                  {grade.error_explanation && <p className="text-sm text-surface-600 leading-relaxed">{grade.error_explanation}</p>}
                  {grade.suggestions?.[0] && <p className="text-xs text-primary-600 mt-2">💡 {grade.suggestions[0]}</p>}
                </div>
              )}
            </div>

            <div className="sticky bottom-0 flex items-center justify-between flex-shrink-0 pt-3 pb-1 px-1 border-t border-surface-200 bg-white/95 backdrop-blur-sm rounded-b-2xl z-10">
              <button onClick={() => currentIdx > 0 && setCurrentIdx(i => i - 1)} disabled={currentIdx === 0} className="flex items-center gap-1 px-4 py-2.5 text-sm text-surface-500 disabled:opacity-30 hover:bg-surface-50 rounded-xl transition-colors"><ChevronLeft className="w-4 h-4" />上一题</button>
              {!grade && answer && <button onClick={handleSubmit} disabled={grading} className="px-8 py-2.5 bg-primary-500 text-white rounded-xl text-sm font-medium hover:bg-primary-600 transition-colors shadow-sm">{grading ? '批改中…' : '提交批改'}</button>}
              {!grade && !answer && <span className="px-8 py-2.5 text-xs text-surface-400">输入答案后提交</span>}
              {grade && <button onClick={() => { setGrades(g => { const n = { ...g }; delete n[currentQ.question_id]; return n; }); setAnswers(a => { const n = { ...a }; delete n[currentQ.question_id]; return n; }); }} className="px-4 py-2.5 text-sm bg-surface-100 rounded-xl text-surface-500 hover:bg-surface-200 transition-colors"><RefreshCw className="w-3 h-3 inline mr-1" />重做</button>}
              <button onClick={() => currentIdx < questions.length - 1 && setCurrentIdx(i => i + 1)} disabled={currentIdx >= questions.length - 1} className="flex items-center gap-1 px-4 py-2.5 text-sm text-surface-500 disabled:opacity-30 hover:bg-surface-50 rounded-xl transition-colors">下一题<ChevronRight className="w-4 h-4" /></button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Weak ──
  if (view === 'weak') {
    return (
      <div className="p-6 animate-fade-in">
        <button onClick={() => setView('home')} className="text-sm text-surface-500 hover:text-surface-700 mb-4"><ChevronLeft className="w-4 h-4 inline" /> 返回</button>
        <h3 className="font-display text-lg font-semibold text-surface-800 mb-4">❌ 错题本（{weakData?.records?.length || 0} 题）</h3>
        {!weakData?.records?.length ? <p className="text-surface-400 text-sm">暂无错题 👍</p> : (
          <div className="space-y-3">
            {weakData.records.map((r: any, i: number) => (
              <div key={i} className="p-4 border border-error-100 rounded-xl bg-error-50/30">
                <p className="text-sm text-surface-700 mb-2">{r.question?.stem || '题目'}</p>
                <div className="flex items-center gap-2 flex-wrap text-xs text-surface-500">
                  <span>你的答案：<span className="text-error-500 font-medium">{r.last_answer}</span></span>
                  {r.question?.correct && <span>正确答案：<span className="text-success-500 font-medium">{r.question.correct}</span></span>}
                  {r.grading_result?.error_label && <span className="px-1.5 py-0.5 rounded-full bg-error-100 text-error-600 text-[10px]">{r.grading_result.error_label}</span>}
                </div>
                {r.grading_result?.error_explanation && <p className="text-xs text-surface-500 mt-2">{r.grading_result.error_explanation}</p>}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ── History ──
  return (
    <div className="p-6 animate-fade-in">
      <button onClick={() => setView('home')} className="text-sm text-surface-500 hover:text-surface-700 mb-4"><ChevronLeft className="w-4 h-4 inline" /> 返回</button>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-display text-lg font-semibold text-surface-800">📊 答题历史</h3>
        {stats && <span className="text-xs text-surface-500">共 {stats.totalAttempted} 题，正确 {stats.totalCorrect} 题</span>}
      </div>
      {!historyData?.records?.length ? <p className="text-surface-400 text-sm">暂无记录</p> : (
        <div className="space-y-2">
          {historyData.records.map((r: any, i: number) => (
            <div key={i} className={`p-3 rounded-xl flex items-center justify-between ${r.grading_result?.total_score >= 60 ? 'bg-success-50/50' : 'bg-error-50/50'}`}>
              <div className="flex-1 min-w-0">
                <p className="text-xs text-surface-700 truncate">{r.question?.stem?.slice(0, 60) || '题目'}</p>
                <p className="text-[10px] text-surface-400">{new Date(r.created_at).toLocaleString()}</p>
              </div>
              <div className="flex items-center gap-2">
                {r.grading_result?.error_type && r.grading_result.error_type !== 'null' && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-error-100 text-error-600">{r.grading_result.error_label}</span>}
                <span className={`text-sm font-bold ${r.grading_result?.total_score >= 60 ? 'text-success-600' : 'text-error-600'}`}>{r.grading_result?.total_score ?? '-'}分</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function QuickCard({ icon: Icon, title, desc, color, onClick, badge }: { icon: any; title: string; desc: string; color: string; onClick: () => void; badge?: number; }) {
  return (
    <button onClick={onClick} className="p-5 bg-white rounded-2xl shadow-soft hover:shadow-elevated transition-all text-left relative">
      <div className={`w-10 h-10 rounded-xl ${color} bg-opacity-15 flex items-center justify-center mb-3`}>
        <Icon className="w-5 h-5" />
      </div>
      <p className="font-semibold text-surface-800 text-sm">{title}</p>
      <p className="text-xs text-surface-500 mt-1">{desc}</p>
      {badge != null && badge > 0 && <span className="absolute top-3 right-3 w-5 h-5 rounded-full bg-error-500 text-white text-[10px] flex items-center justify-center font-bold">{badge}</span>}
    </button>
  );
}

function StatBlock({ title, value, color }: { title: string; value: string; color: string; }) {
  return (
    <div className="bg-white rounded-xl p-4 shadow-soft text-center">
      <p className={`text-xl font-bold ${color}`}>{value}</p>
      <p className="text-[10px] text-surface-400 mt-0.5">{title}</p>
    </div>
  );
}
