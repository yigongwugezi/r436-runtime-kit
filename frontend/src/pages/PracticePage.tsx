import { useState, useEffect, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useChatStore } from '../store/chatStore';
import { Check, X, ChevronLeft, ChevronRight, Loader2, Brain, History, AlertCircle, Edit3 } from 'lucide-react';
import { listQuestions, gradeAnswer, getWeakQuestions, getAnswerHistory } from '../api/chat';

interface Question {
  question_id: string;
  type: 'choice' | 'fill' | 'truefalse' | 'shortanswer';
  stem: string;
  options?: string[];
  difficulty?: string;
  knowledge_points?: string[];
}

interface GradingResult {
  total_score: number | null;
  dimension_scores: Record<string, number | null>;
  dimension_feedback: Record<string, string>;
  error_type: string;
  error_label: string;
  error_explanation: string;
  error_action: string;
  suggestions: string[];
  strengths: string[];
}

export default function PracticePage() {
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const sessionId = useChatStore((s) => s.currentSessionId);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [grades, setGrades] = useState<Record<string, GradingResult>>({});
  const [loading, setLoading] = useState(true);
  const [grading, setGrading] = useState(false);
  const [activeTab, setActiveTab] = useState<'practice' | 'history' | 'weak'>('practice');
  const [historyData, setHistoryData] = useState<any>(null);
  const [weakData, setWeakData] = useState<any>(null);

  useEffect(() => {
    const qsid = sp.get('questionSetId') || '';
    const sid = sp.get('sessionId') || sessionId;
    listQuestions(sid).then((res: any) => {
      if (res?.questions?.length) {
        setQuestions(res.questions);
      }
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const current = questions[currentIdx];
  const answer = answers[current?.question_id || ''] || '';
  const grade = grades[current?.question_id || ''];

  const handleAnswer = useCallback((val: string) => {
    if (!current) return;
    setAnswers((prev) => ({ ...prev, [current.question_id]: val }));
  }, [current]);

  const handleSubmit = useCallback(async () => {
    if (!current || !answer || grading) return;
    setGrading(true);
    try {
      const res: any = await gradeAnswer(current.question_id, answer, sessionId);
      if (res?.gradingResult) {
        setGrades((prev) => ({ ...prev, [current.question_id]: res.gradingResult }));
      }
    } catch { /* ignore */ }
    setGrading(false);
  }, [current, answer, grading, sessionId]);

  const handleNext = () => { if (currentIdx < questions.length - 1) setCurrentIdx((i) => i + 1); };
  const handlePrev = () => { if (currentIdx > 0) setCurrentIdx((i) => i - 1); };

  // 加载历史/错题数据
  useEffect(() => {
    if (activeTab === 'history' && !historyData) {
      getAnswerHistory(sessionId).then(setHistoryData).catch(() => {});
    }
    if (activeTab === 'weak' && !weakData) {
      getWeakQuestions(sessionId).then(setWeakData).catch(() => {});
    }
  }, [activeTab]);

  const TABS = [
    { id: 'practice' as const, label: '练习', icon: Edit3 },
    { id: 'history' as const, label: '答题历史', icon: History },
    { id: 'weak' as const, label: '错题本', icon: AlertCircle },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-primary-500" />
        <span className="ml-2 text-surface-500">加载题目中…</span>
      </div>
    );
  }

  if (!questions.length) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-surface-400">
        <Brain className="w-10 h-10 mb-3" />
        <p>暂无题目。请在聊天中说"给我出几道题"开始练习。</p>
        <button onClick={() => nav('/chat')} className="mt-4 px-4 py-2 bg-primary-500 text-white rounded-lg text-sm">
          回到聊天
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-6 animate-fade-in">
      {/* 进度 */}
      <div className="flex items-center justify-between mb-6">
        <button onClick={() => nav('/chat')} className="text-sm text-surface-500 hover:text-surface-700">
          ← 回到聊天
        </button>
        <span className="text-sm text-surface-500">
          第 {currentIdx + 1} / {questions.length} 题
        </span>
        <div className="w-20" />
      </div>

      {/* 进度条 */}
      <div className="h-1 bg-surface-100 rounded-full mb-8 overflow-hidden">
        <div
          className="h-full bg-primary-500 rounded-full transition-all duration-300"
          style={{ width: `${((currentIdx + 1) / questions.length) * 100}%` }}
        />
      </div>

      {/* 题目卡片 */}
      {current && (
        <div className="bg-white rounded-2xl shadow-soft p-6 mb-6">
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xs px-2 py-0.5 rounded-full bg-primary-50 text-primary-600 font-medium">
              {current.type === 'choice' ? '选择题' : current.type === 'fill' ? '填空题' : current.type === 'truefalse' ? '判断题' : '解答题'}
            </span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-surface-100 text-surface-500">
              {current.difficulty === 'easy' ? '简单' : current.difficulty === 'hard' ? '困难' : '中等'}
            </span>
          </div>

          <h3 className="text-lg font-medium text-surface-800 mb-6">{current.stem}</h3>

          {/* 选择题 */}
          {current.type === 'choice' && current.options && (
            <div className="space-y-3">
              {current.options.map((opt, i) => {
                const letter = String.fromCharCode(65 + i);
                const selected = answer === letter;
                const disabled = !!grade;
                let cls = 'border-surface-200 hover:border-primary-300';
                if (disabled && grade) {
                  if (letter === answer) {
                    cls = grade.total_score === 100 ? 'border-success-400 bg-success-50' : 'border-error-400 bg-error-50';
                  }
                } else if (selected) {
                  cls = 'border-primary-400 bg-primary-50';
                }
                return (
                  <button
                    key={letter}
                    disabled={disabled}
                    onClick={() => handleAnswer(letter)}
                    className={`w-full text-left px-4 py-3 rounded-xl border-2 transition-all ${cls}`}
                  >
                    <span className="font-semibold mr-2">{letter}.</span>
                    {opt}
                  </button>
                );
              })}
            </div>
          )}

          {/* 判断题 */}
          {current.type === 'truefalse' && (
            <div className="flex gap-4">
              {['true', 'false'].map((val) => {
                const label = val === 'true' ? '✓ 正确' : '✗ 错误';
                const selected = answer === val;
                const disabled = !!grade;
                let cls = 'border-surface-200 hover:border-primary-300';
                if (disabled && grade) {
                  if (val === answer && grade.total_score === 100) cls = 'border-success-400 bg-success-50';
                  else if (val === answer) cls = 'border-error-400 bg-error-50';
                } else if (selected) {
                  cls = 'border-primary-400 bg-primary-50';
                }
                return (
                  <button
                    key={val}
                    disabled={disabled}
                    onClick={() => handleAnswer(val)}
                    className={`flex-1 px-6 py-4 rounded-xl border-2 text-lg font-medium transition-all ${cls}`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          )}

          {/* 填空/解答 */}
          {(current.type === 'fill' || current.type === 'shortanswer') && (
            <textarea
              value={answer}
              onChange={(e) => handleAnswer(e.target.value)}
              disabled={!!grade}
              placeholder={current.type === 'fill' ? '输入答案…' : '输入你的解答过程…'}
              rows={current.type === 'shortanswer' ? 6 : 2}
              className="w-full px-4 py-3 bg-surface-50 border border-surface-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary-200 resize-none disabled:opacity-60"
            />
          )}
        </div>
      )}

      {/* 判卷结果 */}
      {grade && (
        <div className="bg-white rounded-2xl shadow-soft p-6 mb-6 animate-fade-in-up">
          <div className="flex items-center gap-3 mb-4">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center ${grade.total_score !== null && grade.total_score >= 60 ? 'bg-success-100' : 'bg-error-100'}`}>
              {grade.total_score !== null && grade.total_score >= 60 ? <Check className="w-5 h-5 text-success-600" /> : <X className="w-5 h-5 text-error-500" />}
            </div>
            <div>
              <p className="font-semibold text-surface-800">
                {grade.total_score !== null ? `得分：${grade.total_score} 分` : '无法评分'}
              </p>
              {grade.error_type !== 'null' && (
                <p className="text-sm text-error-500">错误类型：{grade.error_label}</p>
              )}
            </div>
          </div>

          {/* 维度评分 */}
          {grade.dimension_scores.reasoning !== null && (
            <div className="grid grid-cols-2 gap-3 mb-4">
              {[
                { key: 'reasoning', label: '思路正确性', w: '40%' },
                { key: 'completeness', label: '步骤完整性', w: '30%' },
                { key: 'calculation', label: '计算准确性', w: '20%' },
                { key: 'expression', label: '表达规范性', w: '10%' },
              ].map((dim) => {
                const score = grade.dimension_scores[dim.key];
                return (
                  <div key={dim.key} className="bg-surface-50 rounded-xl p-3">
                    <div className="flex justify-between text-xs text-surface-500 mb-1">
                      <span>{dim.label}（{dim.w}）</span>
                      <span className="font-semibold">{score ?? '-'}</span>
                    </div>
                    <div className="h-1.5 bg-surface-200 rounded-full overflow-hidden">
                      <div className="h-full bg-primary-500 rounded-full" style={{ width: `${score ?? 0}%` }} />
                    </div>
                    {grade.dimension_feedback[dim.key] && (
                      <p className="text-xs text-surface-500 mt-1">{grade.dimension_feedback[dim.key]}</p>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {grade.error_explanation && (
            <p className="text-sm text-surface-600 mb-3">{grade.error_explanation}</p>
          )}
          {grade.suggestions?.length > 0 && (
            <div className="text-sm">
              <p className="font-medium text-surface-700 mb-1">改进建议：</p>
              <ul className="list-disc pl-5 space-y-0.5 text-surface-600">
                {grade.suggestions.map((s: string, i: number) => <li key={i}>{s}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* 操作按钮 */}
      <div className="flex items-center justify-between">
        <button onClick={handlePrev} disabled={currentIdx === 0}
          className="flex items-center gap-1 px-4 py-2 text-sm text-surface-500 hover:text-surface-700 disabled:opacity-30">
          <ChevronLeft className="w-4 h-4" />上一题
        </button>

        <div className="flex items-center gap-2">
          {!grade && answer && (
            <button onClick={handleSubmit} disabled={grading}
              className="px-6 py-2 bg-primary-500 text-white rounded-xl text-sm font-medium hover:bg-primary-600 disabled:opacity-50 flex items-center gap-2">
              {grading && <Loader2 className="w-4 h-4 animate-spin" />}
              提交批改
            </button>
          )}
          {grade && answer && (
            <span className="text-sm text-surface-400">已批改</span>
          )}
        </div>

        <button onClick={handleNext} disabled={currentIdx >= questions.length - 1}
          className="flex items-center gap-1 px-4 py-2 text-sm text-surface-500 hover:text-surface-700 disabled:opacity-30">
          下一题<ChevronRight className="w-4 h-4" />
        </button>
      </div>
      {/* Tab 导航 */}
      <div className="flex items-center gap-1 bg-surface-50 rounded-xl p-1 mt-8">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setActiveTab(t.id)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium transition-all flex-1 justify-center ${activeTab === t.id ? 'bg-white text-primary-600 shadow-sm' : 'text-surface-500 hover:text-surface-700'}`}>
            <t.icon className="w-3.5 h-3.5" />{t.label}
          </button>
        ))}
      </div>

      {/* 答题历史 */}
      {activeTab === 'history' && (
        <div className="bg-white rounded-2xl shadow-soft p-6 mt-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-surface-800">答题历史</h3>
            {historyData && (
              <span className="text-xs text-surface-500">共 {historyData.totalAttempted} 题，答对 {historyData.totalCorrect} 题</span>
            )}
          </div>
          {!historyData ? <Loader2 className="w-5 h-5 animate-spin text-primary-500" /> : historyData.records?.length === 0 ? (
            <p className="text-sm text-surface-400">暂无答题记录</p>
          ) : (
            <div className="space-y-2">
              {historyData.records?.map((r: any, i: number) => (
                <div key={i} className={`p-3 rounded-xl flex items-center justify-between ${r.grading_result?.total_score >= 60 ? 'bg-success-50/50' : 'bg-error-50/50'}`}>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-surface-700 truncate">{r.question?.stem?.slice(0, 60) || '题目'}</p>
                    <p className="text-[10px] text-surface-400">{new Date(r.created_at).toLocaleString()}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {r.grading_result?.error_type && r.grading_result.error_type !== 'null' && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-error-100 text-error-600">{r.grading_result.error_label}</span>
                    )}
                    <span className={`text-sm font-bold ${r.grading_result?.total_score >= 60 ? 'text-success-600' : 'text-error-600'}`}>{r.grading_result?.total_score ?? '-'}分</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 错题本 */}
      {activeTab === 'weak' && (
        <div className="bg-white rounded-2xl shadow-soft p-6 mt-4">
          <h3 className="font-semibold text-surface-800 mb-4">错题本</h3>
          {!weakData ? <Loader2 className="w-5 h-5 animate-spin text-primary-500" /> : weakData.records?.length === 0 ? (
            <p className="text-sm text-surface-400">暂无错题 👍</p>
          ) : (
            <div className="space-y-3">
              {weakData.records?.map((r: any, i: number) => (
                <div key={i} className="p-4 border border-error-100 rounded-xl bg-error-50/30">
                  <p className="text-sm text-surface-700 mb-2">{r.question?.stem || '题目'}</p>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs text-surface-500">你的答案：<span className="text-error-500 font-medium">{r.last_answer}</span></span>
                    {r.question?.correct && <span className="text-xs text-surface-500">正确答案：<span className="text-success-500 font-medium">{r.question.correct}</span></span>}
                    {r.grading_result?.error_label && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-error-100 text-error-600">{r.grading_result.error_label}</span>
                    )}
                  </div>
                  {r.grading_result?.error_explanation && (
                    <p className="text-xs text-surface-500 mt-2">{r.grading_result.error_explanation}</p>
                  )}
                  {r.grading_result?.suggestions?.length > 0 && (
                    <p className="text-xs text-primary-600 mt-1">💡 {r.grading_result.suggestions[0]}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
