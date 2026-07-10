import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useLearningPath } from '../hooks/useLearningPath';
import { useChatStore } from '../store/chatStore';
import { ChevronDown, ChevronRight, Sparkles, MessageCircle, Send, Brain, FileText, Check, X, Loader2, HelpCircle } from 'lucide-react';
import Markdown from '../utils/markdown';
import { generateSectionQuiz, submitQuizAttempt } from '../api/assessment';
import type { LinkedQuestion, QuizResult } from '../types/assessment';

export default function LecturePage() {
  const { sectionId } = useParams<{ sectionId: string }>();
  const nav = useNavigate();
  const { path, fetchPath } = useLearningPath();
  const sessionId = useChatStore((s) => s.currentSessionId);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [activeSection, setActiveSection] = useState(sectionId || '');
  const [lecture, setLecture] = useState('');
  const [generating, setGenerating] = useState(false);
  const [chatMsg, setChatMsg] = useState('');

  // ── Quiz state ──
  const [quizState, setQuizState] = useState<'idle' | 'generating' | 'answering' | 'submitted'>('idle');
  const [quizQuestions, setQuizQuestions] = useState<LinkedQuestion[]>([]);
  const [quizId, setQuizId] = useState('');
  const [quizAnswers, setQuizAnswers] = useState<Record<string, string>>({});
  const [quizResults, setQuizResults] = useState<QuizResult[]>([]);
  const [quizTotalScore, setQuizTotalScore] = useState<number | null>(null);
  const [quizSuggestion, setQuizSuggestion] = useState('');

  useEffect(() => { fetchPath(); }, []);
  useEffect(() => { if (sectionId) setActiveSection(sectionId); }, [sectionId]);

  // Reset quiz when section changes
  useEffect(() => {
    setQuizState('idle');
    setQuizQuestions([]);
    setQuizId('');
    setQuizAnswers({});
    setQuizResults([]);
    setQuizTotalScore(null);
    setQuizSuggestion('');
  }, [activeSection]);

  const pathData: any = path || {};
  const chapters = pathData.chapters || pathData.stages || [];

  // ── Extract current section context ──
  const getCurrentSectionContext = () => {
    let sectionTitle = '';
    let chapterTitle = '';
    let chapterId = '';
    const knowledgePoints: string[] = [];

    for (const ch of chapters) {
      const cid = ch.chapter_id || ch.id || '';
      for (const sec of (ch.sections || ch.nodes || [])) {
        const sid = sec.section_id || sec.id || '';
        if (sid === activeSection) {
          sectionTitle = sec.title || sec.topic || '';
          chapterTitle = ch.title || '';
          chapterId = cid;
          if (sec.topic) knowledgePoints.push(sec.topic);
          if (sec.description) knowledgePoints.push(sec.description);
          if (ch.title) knowledgePoints.push(ch.title);
          break;
        }
      }
      if (sectionTitle) break;
    }

    // Fallback to path nodes search
    if (!sectionTitle) {
      for (const stage of chapters) {
        for (const node of (stage.nodes || [])) {
          if (node.id === activeSection) {
            sectionTitle = node.topic || node.title || '';
            chapterTitle = stage.title || '';
            chapterId = stage.id || '';
            if (node.topic) knowledgePoints.push(node.topic);
            if (node.description) knowledgePoints.push(node.description);
            break;
          }
        }
        if (sectionTitle) break;
      }
    }

    return { sectionTitle, chapterTitle, chapterId, knowledgePoints };
  };

  const toggle = (id: string) => {
    const n = new Set(expanded); n.has(id) ? n.delete(id) : n.add(id); setExpanded(n);
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: `生成图文讲义`, sessionId: `lecture_${activeSection}` }),
      });
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '', content = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try { const evt = JSON.parse(line.slice(6)); if (evt.type === 'messages') content += evt.content || ''; } catch {}
          }
        }
      }
      setLecture(content);
    } catch {}
    setGenerating(false);
  };

  // ── Quiz generation ──
  const handleQuizGenerate = async () => {
    const { sectionTitle, chapterTitle, chapterId, knowledgePoints } = getCurrentSectionContext();
    setQuizState('generating');
    try {
      const res = await generateSectionQuiz(activeSection, {
        sessionId: sessionId || `lecture_${activeSection}`,
        title: sectionTitle || '当前小节',
        knowledgePoints: knowledgePoints.length > 0 ? knowledgePoints.slice(0, 5) : [chapterTitle, sectionTitle].filter(Boolean),
        lectureSummary: lecture.slice(0, 1500),
        difficulty: 'medium',
        pathId: pathData.id || '',
        stageId: chapterId || '',
        chapterId: chapterId || '',
        sectionId: activeSection,
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

  // ── Quiz answer handling ──
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
        sessionId: sessionId || `lecture_${activeSection}`,
        answers,
      }) as any;
      const data = res?.data || res;
      if (data?.results) {
        setQuizResults(data.results);
        setQuizTotalScore(data.totalScore ?? null);
        setQuizSuggestion(data.sectionStatusSuggestion || '');
        setQuizState('submitted');
      }
    } catch (e: any) {
      alert('提交失败: ' + (e?.message || '请重试'));
    }
  };

  // ── Quiz type labels ──
  const typeLabel = (t: string) => t === 'choice' ? '选择题' : t === 'truefalse' ? '判断题' : t === 'fill' ? '填空题' : '简答题';

  return (
    <div className="flex h-screen -m-6">
      {/* ── Left sidebar: chapter/section nav ── */}
      <div className="w-52 border-r border-gray-200 bg-gray-50 overflow-y-auto flex-shrink-0">
        <div className="p-3 border-b border-gray-200">
          <span className="text-xs font-medium text-gray-500">{pathData.courseName || '学习路径'}</span>
        </div>
        {chapters.map((ch: any, ci: number) => {
          const cid = ch.chapter_id || `c${ci}`;
          return (
            <div key={cid}>
              <button onClick={() => toggle(cid)} className="w-full flex items-center gap-1.5 px-3 py-2 text-left text-xs hover:bg-gray-100">
                {expanded.has(cid) ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                <FileText size={12} className="text-gray-400" />
                <span className="truncate font-medium text-gray-700">{ch.title}</span>
              </button>
              {expanded.has(cid) && (ch.sections || ch.nodes || []).map((sec: any, si: number) => {
                const sid = sec.section_id || sec.id || `s${ci}_${si}`;
                return (
                  <button key={sid}
                    onClick={() => { setActiveSection(sid); nav(`/lecture/${sid}`); }}
                    className={`w-full text-left pl-8 pr-3 py-1.5 text-xs ${sid === activeSection ? 'bg-blue-50 text-blue-700 border-l-2 border-blue-500' : 'hover:bg-gray-100 text-gray-600'}`}>
                    {sec.title || sec.topic}
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>

      {/* ── Center: lecture + quiz ── */}
      <div className="flex-1 flex flex-col min-w-0 border-r border-gray-200">
        {/* Toolbar */}
        <div className="px-4 py-2.5 border-b border-gray-200 flex items-center gap-2">
          <span className="text-sm font-medium truncate flex-1">讲义</span>
          <button onClick={handleGenerate} disabled={generating}
            className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded text-xs hover:bg-blue-700 disabled:opacity-50">
            <Sparkles size={12} />{generating ? '...' : '生成讲义'}
          </button>
          <button onClick={handleQuizGenerate} disabled={quizState === 'generating'}
            className="flex items-center gap-1 px-3 py-1.5 bg-accent-500 text-white rounded text-xs hover:bg-accent-600 disabled:opacity-50"
            style={{ backgroundColor: '#14b8a6' }}>
            <HelpCircle size={12} />{quizState === 'generating' ? '...' : '生成小测'}
          </button>
        </div>

        {/* Scrollable content area */}
        <div className="flex-1 overflow-y-auto">
          {/* ── Quiz Panel ── */}
          {quizState !== 'idle' && (
            <div className="p-4 border-b border-gray-200 bg-gray-50/50">
              {/* Score summary (after submission) */}
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

              {/* Generating indicator */}
              {quizState === 'generating' && (
                <div className="flex items-center gap-3 p-4 text-surface-500">
                  <Loader2 size={18} className="animate-spin text-accent-500" />
                  <span className="text-sm">正在生成小测题目…</span>
                </div>
              )}

              {/* Questions */}
              {(quizState === 'answering' || quizState === 'submitted') && quizQuestions.map((q, idx) => {
                const result = quizResults.find(r => r.questionId === q.questionId);
                const answer = quizAnswers[q.questionId] || '';
                const isSubmitted = quizState === 'submitted';

                return (
                  <div key={q.questionId} className="bg-white rounded-2xl shadow-soft p-5 mb-4">
                    {/* Header */}
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-sm font-bold text-primary-600">#{idx + 1}</span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary-50 text-primary-600 font-medium">
                        {typeLabel(q.type)}
                      </span>
                      {q.difficulty && (
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${q.difficulty === 'easy' ? 'bg-success-50 text-success-600' : q.difficulty === 'hard' ? 'bg-error-50 text-error-600' : 'bg-warning-50 text-warning-600'}`}>
                          {q.difficulty === 'easy' ? '简单' : q.difficulty === 'hard' ? '困难' : '中等'}
                        </span>
                      )}
                      {result && (
                        <span className={`ml-auto text-sm font-bold ${result.isCorrect ? 'text-success-500' : 'text-error-500'}`}>
                          {result.score}分
                        </span>
                      )}
                    </div>

                    {/* Stem */}
                    <div className="text-sm text-surface-800 mb-4 leading-relaxed">
                      <Markdown content={q.stem} />
                    </div>

                    {/* Answer area */}
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
                            <button key={letter}
                              disabled={isSubmitted}
                              onClick={() => handleQuizAnswer(q.questionId, letter)}
                              className={`w-full text-left px-4 py-3 rounded-xl transition-all flex items-center gap-3 ${cls}`}>
                              <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${isSelected && !isSubmitted ? 'bg-primary-500 text-white' : isSubmitted && isCorrectAnswer ? 'bg-success-500 text-white' : isSubmitted && isSelected ? 'bg-error-500 text-white' : 'bg-surface-100 text-surface-500'}`}>
                                {letter}
                              </span>
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
                            <button key={v}
                              disabled={isSubmitted}
                              onClick={() => handleQuizAnswer(q.questionId, v)}
                              className={cls}>
                              {v === 'true' ? '✓ 正确' : '✗ 错误'}
                            </button>
                          );
                        })}
                      </div>
                    )}

                    {(q.type === 'fill' || q.type === 'shortanswer') && (
                      <textarea
                        value={answer}
                        onChange={e => handleQuizAnswer(q.questionId, e.target.value)}
                        disabled={isSubmitted}
                        rows={q.type === 'shortanswer' ? 4 : 2}
                        placeholder="输入你的答案…"
                        className="w-full px-4 py-3 bg-surface-50 border-2 border-surface-200 rounded-xl resize-none focus:border-primary-400 focus:outline-none disabled:opacity-60 text-sm"
                      />
                    )}

                    {/* Result detail after submission */}
                    {result && (
                      <div className={`mt-4 p-3 rounded-xl ${result.isCorrect ? 'bg-success-50/50 border border-success-200' : 'bg-error-50/50 border border-error-200'}`}>
                        <div className="flex items-center gap-2 mb-1">
                          {result.isCorrect ? <Check className="w-4 h-4 text-success-500" /> : <X className="w-4 h-4 text-error-500" />}
                          <span className={`text-xs font-medium ${result.isCorrect ? 'text-success-600' : 'text-error-600'}`}>
                            {result.isCorrect ? '正确' : '错误'}
                          </span>
                          {result.errorLabel && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-error-100 text-error-600">{result.errorLabel}</span>
                          )}
                        </div>
                        {!result.isCorrect && result.correctAnswer && (
                          <p className="text-xs text-surface-600 mt-1">正确答案：<span className="text-success-600 font-medium">{result.correctAnswer}</span></p>
                        )}
                        {result.explanation && (
                          <p className="text-xs text-surface-500 mt-1 leading-relaxed">{result.explanation}</p>
                        )}
                        {result.feedback && (
                          <p className="text-xs text-primary-600 mt-1">💡 {result.feedback}</p>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Submit button */}
              {quizState === 'answering' && (
                <div className="flex items-center justify-between pt-2">
                  <span className="text-xs text-surface-400">
                    {allAnswered ? '已完成所有题目' : `已答 ${Object.keys(quizAnswers).filter(k => quizAnswers[k]?.trim()).length} / ${quizQuestions.length} 题`}
                  </span>
                  <button
                    onClick={handleQuizSubmit}
                    disabled={!allAnswered}
                    className="px-6 py-2.5 bg-accent-500 text-white rounded-xl text-sm font-medium hover:bg-accent-600 disabled:opacity-40 transition-colors shadow-sm"
                    style={{ backgroundColor: allAnswered ? '#14b8a6' : undefined }}>
                    提交批改
                  </button>
                </div>
              )}

              {/* Re-generate button after submission */}
              {quizState === 'submitted' && (
                <div className="flex justify-end pt-2">
                  <button
                    onClick={() => { setQuizState('idle'); setQuizQuestions([]); setQuizAnswers({}); setQuizResults([]); }}
                    className="px-4 py-2 text-sm text-surface-500 hover:text-surface-700 hover:bg-surface-100 rounded-xl transition-colors">
                    关闭小测
                  </button>
                </div>
              )}
            </div>
          )}

          {/* ── Lecture content ── */}
          <div className="p-4">
            {lecture ? (
              <div className="prose prose-sm max-w-none"><Markdown content={lecture} /></div>
            ) : (
              <div className="flex flex-col items-center justify-center h-64 text-gray-400 gap-2">
                <Brain size={36} /><p className="text-sm">点击「生成讲义」创建内容</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Right panel: AI tutor ── */}
      <div className="w-64 bg-gray-50 flex flex-col flex-shrink-0">
        <div className="px-3 py-2.5 border-b border-gray-200">
          <span className="text-xs font-medium text-gray-500 flex items-center gap-1"><MessageCircle size={12} />智能辅导</span>
        </div>
        <div className="flex-1 p-3 text-xs text-gray-400">针对当前章节提问。</div>
        <div className="p-2 border-t border-gray-200">
          <div className="flex gap-1">
            <input type="text" value={chatMsg} onChange={e => setChatMsg(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && setChatMsg('')}
              placeholder="提问..." className="flex-1 px-2 py-1.5 border border-gray-300 rounded text-xs" />
            <button className="px-2 py-1.5 bg-blue-600 text-white rounded text-xs"><Send size={12} /></button>
          </div>
        </div>
      </div>
    </div>
  );
}
