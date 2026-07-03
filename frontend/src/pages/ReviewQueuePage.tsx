import { useState, useEffect } from 'react';
import { Shield, Check, X, Edit3, AlertTriangle, RefreshCw } from 'lucide-react';
import { PageLoading, PageError } from '../components/common/PageState';

interface ReviewQuestion {
  question_id: string;
  stem: string;
  type: string;
  difficulty: string;
  review_reason: string;
  review_status: string;
  created_at: number;
}

export default function ReviewQueuePage() {
  const [questions, setQuestions] = useState<ReviewQuestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('pending');
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchQueue = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(
        `${import.meta.env.VITE_API_BASE || ''}/api/questions/review-queue?status=${filter}`,
        { headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } }
      );
      const data = await res.json();
      if (data.status === 'success') {
        setQuestions(data.data.questions || []);
      } else {
        setError(data.message || '获取审核队列失败');
      }
    } catch (e: any) {
      setError(e.message || '网络错误');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchQueue(); }, [filter]);

  const handleAction = async (questionId: string, action: string) => {
    setActionLoading(questionId);
    try {
      const res = await fetch(
        `${import.meta.env.VITE_API_BASE || ''}/api/questions/review-action`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${localStorage.getItem('token') || ''}`,
          },
          body: JSON.stringify({ question_id: questionId, action }),
        }
      );
      const data = await res.json();
      if (data.status === 'success') {
        setQuestions(prev => prev.filter(q => q.question_id !== questionId));
      }
    } catch (e: any) {
      console.error(e);
    } finally {
      setActionLoading(null);
    }
  };

  const typeLabel: Record<string, string> = {
    choice: '选择题', fill: '填空题', truefalse: '判断题', shortanswer: '解答题', variant: '变式题',
  };

  if (loading && questions.length === 0) return <PageLoading text="加载审核队列…" />;
  if (error && questions.length === 0) return <PageError title="加载失败" description={error} onRetry={fetchQueue} />;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-2xl font-bold text-surface-800">题目审核队列</h2>
          <p className="text-surface-500 mt-1">审查高风险题目，确保题目质量</p>
        </div>
        <button onClick={fetchQueue} className="flex items-center gap-2 px-4 py-2.5 bg-surface-50 text-surface-600 rounded-xl font-medium hover:bg-surface-100 transition-colors">
          <RefreshCw size={16} />刷新
        </button>
      </div>

      {/* 筛选标签 */}
      <div className="flex gap-2">
        {[
          { key: 'pending', label: '待审核' },
          { key: 'approved', label: '已通过' },
          { key: 'rejected', label: '已拒绝' },
          { key: 'all', label: '全部' },
        ].map(tab => (
          <button
            key={tab.key}
            onClick={() => setFilter(tab.key)}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors ${
              filter === tab.key
                ? 'bg-primary-600 text-white'
                : 'bg-surface-50 text-surface-600 hover:bg-surface-100'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {questions.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Shield className="w-12 h-12 text-surface-300 mb-3" />
          <p className="text-surface-500 font-medium">暂无待审核题目</p>
          <p className="text-xs text-surface-400 mt-1">所有题目质量合格或已通过审核</p>
        </div>
      ) : (
        <div className="space-y-3">
          {questions.map(q => (
            <div key={q.question_id} className="bg-white rounded-2xl p-5 shadow-soft border border-surface-100">
              <div className="flex items-start gap-4">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
                  q.difficulty === 'hard' ? 'bg-error-50 text-error-500' :
                  q.difficulty === 'medium' ? 'bg-warning-50 text-warning-500' :
                  'bg-primary-50 text-primary-500'
                }`}>
                  <AlertTriangle size={18} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-surface-700 line-clamp-2">{q.stem}</p>
                  <div className="flex items-center gap-3 mt-2">
                    <span className="text-[10px] px-2 py-0.5 bg-surface-100 text-surface-500 rounded-full">
                      {typeLabel[q.type] || q.type}
                    </span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full ${
                      q.difficulty === 'hard' ? 'bg-error-50 text-error-600' : 'bg-warning-50 text-warning-600'
                    }`}>
                      {q.difficulty === 'hard' ? '困难' : q.difficulty === 'medium' ? '中等' : '简单'}
                    </span>
                    {q.review_reason && (
                      <span className="text-[10px] text-surface-400">{q.review_reason}</span>
                    )}
                    {q.review_status !== 'pending' && (
                      <span className={`text-[10px] px-2 py-0.5 rounded-full ${
                        q.review_status === 'approved' ? 'bg-success-50 text-success-600' : 'bg-error-50 text-error-600'
                      }`}>
                        {q.review_status === 'approved' ? '已通过' : '已拒绝'}
                      </span>
                    )}
                  </div>
                </div>
                {filter === 'pending' && (
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      onClick={() => handleAction(q.question_id, 'approve')}
                      disabled={actionLoading === q.question_id}
                      className="p-2 bg-success-50 text-success-600 rounded-xl hover:bg-success-100 transition-colors"
                      title="通过"
                    >
                      <Check size={16} />
                    </button>
                    <button
                      onClick={() => handleAction(q.question_id, 'reject')}
                      disabled={actionLoading === q.question_id}
                      className="p-2 bg-error-50 text-error-600 rounded-xl hover:bg-error-100 transition-colors"
                      title="拒绝"
                    >
                      <X size={16} />
                    </button>
                    <button
                      onClick={() => handleAction(q.question_id, 'revise')}
                      disabled={actionLoading === q.question_id}
                      className="p-2 bg-warning-50 text-warning-600 rounded-xl hover:bg-warning-100 transition-colors"
                      title="需修改"
                    >
                      <Edit3 size={16} />
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
