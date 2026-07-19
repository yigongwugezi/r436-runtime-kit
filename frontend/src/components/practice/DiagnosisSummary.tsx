import { Target, TrendingUp, AlertCircle, RefreshCw, ArrowRight } from 'lucide-react';

interface GradedQuestion {
  question_id: string;
  stem: string;
  type: string;
  knowledge_points?: string[];
  difficulty?: string;
}

interface GradeResult {
  total_score: number | null;
  error_type?: string;
  error_label?: string;
  error_explanation?: string;
  suggestions?: string[];
}

interface Props {
  questions: GradedQuestion[];
  grades: Record<string, GradeResult>;
  onRetarget: (knowledgePoints: string[]) => void;
  onRediagnose: () => void;
}

export default function DiagnosisSummary({ questions, grades, onRetarget, onRediagnose }: Props) {
  const gradedCount = Object.keys(grades).length;
  const totalCount = questions.length;
  const allDone = gradedCount >= totalCount;

  // 聚合统计
  const totalCorrect = Object.values(grades).filter(g => g.total_score != null && g.total_score >= 60).length;
  const avgScore = gradedCount > 0
    ? Math.round(Object.values(grades).reduce((sum, g) => sum + (g.total_score ?? 0), 0) / gradedCount)
    : 0;

  // 按知识点分组
  const kpStats: Record<string, { total: number; correct: number; wrongLabels: string[] }> = {};
  questions.forEach(q => {
    const g = grades[q.question_id];
    if (!g) return;
    (q.knowledge_points || ['未分类']).forEach(kp => {
      if (!kpStats[kp]) kpStats[kp] = { total: 0, correct: 0, wrongLabels: [] };
      kpStats[kp].total++;
      if (g.total_score != null && g.total_score >= 60) {
        kpStats[kp].correct++;
      } else if (g.error_label) {
        kpStats[kp].wrongLabels.push(g.error_label);
      }
    });
  });

  // 薄弱知识点（正确率 < 60%）
  const weakKPs = Object.entries(kpStats)
    .filter(([, s]) => s.total > 0 && s.correct / s.total < 0.6)
    .sort((a, b) => (a[1].correct / a[1].total) - (b[1].correct / b[1].total));

  // 错误类型统计
  const errorTypeCount: Record<string, number> = {};
  Object.values(grades).forEach(g => {
    if (g.error_label && g.total_score != null && g.total_score < 60) {
      errorTypeCount[g.error_label] = (errorTypeCount[g.error_label] || 0) + 1;
    }
  });

  if (gradedCount === 0) return null;

  return (
    <div className="rounded-2xl bg-white dark:bg-surface-700 p-6 shadow-soft space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-50 dark:bg-primary-500/20 text-primary-500">
            <Target size={20} />
          </div>
          <div>
            <h3 className="text-base font-semibold text-surface-800 dark:text-gray-100">
              {allDone ? '诊断总结' : `诊断进度 (${gradedCount}/${totalCount})`}
            </h3>
            <p className="text-xs text-surface-400">
              {allDone ? '全部题目已完成批改' : '继续作答以完成诊断'}
            </p>
          </div>
        </div>
        {allDone && (
          <button
            onClick={onRediagnose}
            className="flex items-center gap-1.5 rounded-lg bg-primary-500 px-3.5 py-2 text-xs font-medium text-white shadow-sm hover:bg-primary-600 transition-colors"
          >
            <RefreshCw size={13} />
            再来一组
          </button>
        )}
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl bg-surface-50 dark:bg-surface-800 p-3.5 text-center">
          <p className="text-[10px] uppercase tracking-wider text-surface-400">正确率</p>
          <strong className={`mt-1 block text-2xl font-semibold ${avgScore >= 60 ? 'text-success-600 dark:text-success-400' : 'text-error-600 dark:text-error-400'}`}>
            {gradedCount > 0 ? `${totalCorrect}/${gradedCount}` : '-'}
          </strong>
        </div>
        <div className="rounded-xl bg-surface-50 dark:bg-surface-800 p-3.5 text-center">
          <p className="text-[10px] uppercase tracking-wider text-surface-400">平均分</p>
          <strong className={`mt-1 block text-2xl font-semibold ${avgScore >= 60 ? 'text-success-600 dark:text-success-400' : 'text-error-600 dark:text-error-400'}`}>
            {avgScore}
          </strong>
        </div>
        <div className="rounded-xl bg-surface-50 dark:bg-surface-800 p-3.5 text-center">
          <p className="text-[10px] uppercase tracking-wider text-surface-400">薄弱点</p>
          <strong className="mt-1 block text-2xl font-semibold text-error-600 dark:text-error-400">
            {weakKPs.length}
          </strong>
        </div>
      </div>

      {/* 薄弱知识点 */}
      {weakKPs.length > 0 && (
        <div>
          <div className="mb-3 flex items-center gap-1.5">
            <AlertCircle size={14} className="text-error-500" />
            <span className="text-xs font-semibold text-surface-700 dark:text-gray-200">薄弱知识点</span>
            <span className="text-[10px] text-surface-400">（正确率 &lt; 60%）</span>
          </div>
          <div className="space-y-2">
            {weakKPs.map(([kp, stat]) => {
              const pct = Math.round((stat.correct / stat.total) * 100);
              return (
                <div key={kp} className="flex items-center gap-3 rounded-xl border border-error-100 dark:border-error-500/20 bg-error-50/30 dark:bg-error-500/5 px-4 py-2.5">
                  <span className="h-2 w-2 shrink-0 rounded-full bg-error-400" />
                  <div className="flex-1 min-w-0">
                    <p className="truncate text-sm font-medium text-surface-700 dark:text-gray-200">{kp}</p>
                    <p className="text-xs text-surface-400">
                      {stat.correct}/{stat.total} 正确 · {[...new Set(stat.wrongLabels)].slice(0, 2).join('、') || '错误'}
                    </p>
                  </div>
                  <span className="shrink-0 text-xs font-semibold text-error-600 dark:text-error-400">{pct}%</span>
                  <button
                    onClick={() => onRetarget([kp])}
                    className="flex shrink-0 items-center gap-1 rounded-lg bg-error-100 dark:bg-error-500/20 px-3 py-1.5 text-xs font-medium text-error-600 dark:text-error-300 hover:bg-error-200 dark:hover:bg-error-500/30 transition-colors"
                  >
                    针对练习 <ArrowRight size={11} />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 错误类型分布 */}
      {Object.keys(errorTypeCount).length > 0 && (
        <div>
          <div className="mb-2.5 flex items-center gap-1.5">
            <TrendingUp size={14} className="text-surface-400" />
            <span className="text-xs font-semibold text-surface-700 dark:text-gray-200">错误类型分布</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(errorTypeCount)
              .sort(([, a], [, b]) => b - a)
              .map(([label, count]) => (
                <span key={label} className="rounded-lg bg-surface-100 dark:bg-surface-600 px-2.5 py-1 text-xs text-surface-600 dark:text-gray-300">
                  {label} <strong className="text-error-600 dark:text-error-400">{count}次</strong>
                </span>
              ))}
          </div>
        </div>
      )}

      {/* 未完成提示 */}
      {!allDone && (
        <p className="text-center text-xs text-surface-400">
          还有 {totalCount - gradedCount} 道题待批改，完成后可查看完整诊断报告
        </p>
      )}
    </div>
  );
}
