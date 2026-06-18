import { useState, useEffect, useCallback, useRef } from 'react';
import client from '../api/client';
import { useSubjectStore } from '../store/subjectStore';
import {
  TrendingUp, Zap, Target, BookOpen, Clock, Brain,
  AlertCircle, Sparkles, ArrowRight, Star,
} from 'lucide-react';
import Loading from '../components/common/Loading';
import EmptyState from '../components/common/EmptyState';
import { formatDuration } from '../utils/format';

/* ===================================================================
 * 类型
 * =================================================================== */
interface AnalyticsData {
  eventCount: number;
  totalStudyMinutes: number;
  activeResourceCount: number;
  eventBreakdown: Record<string, number>;
  topResources: { resourceId: string; count: number }[];
  quizAccuracy: number;
  weakTopics: string[];
  recommendations: string[];
  recentEvents: { event: string; timestamp: number }[];
  summary: string;
}

/* ===================================================================
 * 子组件
 * =================================================================== */
function StatCard({ icon, label, value, color }: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  color: string;
}) {
  return (
    <div className={`bg-white border border-gray-100 rounded-2xl p-5 shadow-sm hover:shadow-md transition-shadow`}>
      <div className="flex items-start gap-3">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${color}`}>
          {icon}
        </div>
        <div>
          <p className="text-2xl font-extrabold text-gray-900">{value}</p>
          <p className="text-xs text-gray-400 mt-0.5">{label}</p>
        </div>
      </div>
    </div>
  );
}

function ProgressRing({ pct, size = 80, strokeWidth = 6 }: { pct: number; size?: number; strokeWidth?: number }) {
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (pct / 100) * circumference;
  const color = pct >= 80 ? '#22c55e' : pct >= 50 ? '#f59e0b' : '#ef4444';

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#e2e8f0" strokeWidth={strokeWidth} />
        <circle
          cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={color}
          strokeWidth={strokeWidth} strokeLinecap="round"
          strokeDasharray={circumference} strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          className="transition-all duration-1000"
        />
      </svg>
      <span className="absolute text-sm font-bold" style={{ color }}>{pct}%</span>
    </div>
  );
}

/* ===================================================================
 * 主页面
 * =================================================================== */
export default function LearningAnalyticsPage() {
  const subjectId = useSubjectStore((s) => s.activeSubject?.id);
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lastSubjectRef = useRef<string | undefined>(undefined);

  const fetchAnalytics = useCallback(async () => {
    if (!subjectId) return;
    setLoading(true);
    setError(null);
    try {
      const { data } = await client.get('/learning-analytics', {
        params: { subjectId },
      });
      setAnalytics(data);
    } catch {
      setError('加载分析数据失败');
    } finally {
      setLoading(false);
    }
  }, [subjectId]);

  useEffect(() => {
    if (subjectId && lastSubjectRef.current !== subjectId) {
      lastSubjectRef.current = subjectId;
      fetchAnalytics();
    }
    // 无科目时立即结束加载
    if (!subjectId) {
      setLoading(false);
      setError(null);
      setAnalytics(null);
    }
  }, [subjectId, fetchAnalytics]);

  // 无科目
  if (!subjectId) {
    return (
      <EmptyState
        icon={<TrendingUp className="w-8 h-8" />}
        title="请先选择科目"
        description="在左侧边栏或个人中心选择一个科目后查看学习分析"
      />
    );
  }

  // 空状态
  if (!loading && !error && analytics && analytics.eventCount === 0) {
    return (
      <EmptyState
        icon={<TrendingUp className="w-8 h-8" />}
        title="暂无学习分析数据"
        description="完成学习任务、提交反馈或做题后，系统将自动生成你的学习分析报告"
      />
    );
  }

  if (loading) return <Loading fullScreen text="正在分析你的学习数据…" />;

  if (error || !analytics) {
    return (
      <EmptyState
        icon={<AlertCircle className="w-8 h-8" />}
        title="加载失败"
        description={error || '请稍后重试'}
      />
    );
  }

  // 事件标签映射
  const eventLabels: Record<string, { label: string; icon: string }> = {
    resource_view: { label: '查看资源', icon: '👁' },
    resource_complete: { label: '完成学习', icon: '✅' },
    quiz_submit: { label: '提交练习', icon: '📝' },
    chat_feedback: { label: '对话反馈', icon: '💬' },
    node_progress: { label: '节点进度', icon: '📈' },
  };

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 md:py-8">
      {/* 头部 */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-2">
          <TrendingUp className="w-5 h-5 text-brand-500" />
          <span className="text-xs font-bold text-brand-500 uppercase tracking-wider">Learning Analytics</span>
        </div>
        <h1 className="text-2xl md:text-3xl font-extrabold text-gray-900 mb-1">学习分析</h1>
        <p className="text-sm text-gray-500">{analytics.summary || '基于你的学习行为自动生成'}</p>
      </div>

      {/* 核心指标卡片 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
        <StatCard
          icon={<Clock className="w-5 h-5 text-blue-500" />}
          label="学习时长"
          value={formatDuration(analytics.totalStudyMinutes)}
          color="bg-blue-50"
        />
        <StatCard
          icon={<BookOpen className="w-5 h-5 text-green-500" />}
          label="学习资源"
          value={analytics.activeResourceCount}
          color="bg-green-50"
        />
        <StatCard
          icon={<Target className="w-5 h-5 text-amber-500" />}
          label="练习正确率"
          value={`${analytics.quizAccuracy}%`}
          color="bg-amber-50"
        />
        <StatCard
          icon={<Zap className="w-5 h-5 text-purple-500" />}
          label="学习事件"
          value={analytics.eventCount}
          color="bg-purple-50"
        />
      </div>

      {/* 两栏布局 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* 正确率仪表盘 */}
        <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Star className="w-4 h-4 text-amber-400" />
            练习正确率
          </h3>
          <div className="flex items-center gap-6">
            <ProgressRing pct={analytics.quizAccuracy} size={100} />
            <div className="text-sm text-gray-500 space-y-1">
              <p>
                {analytics.quizAccuracy >= 80
                  ? '🎉 优秀！继续保持'
                  : analytics.quizAccuracy >= 60
                    ? '👍 不错，还有进步空间'
                    : '💪 需要更多练习'}
              </p>
              <p className="text-xs text-gray-400">
                基于 {analytics.eventBreakdown['quiz_submit'] || 0} 次练习统计
              </p>
            </div>
          </div>
        </div>

        {/* 事件分布 */}
        <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Zap className="w-4 h-4 text-brand-500" />
            学习行为分布
          </h3>
          {Object.keys(analytics.eventBreakdown).length === 0 ? (
            <p className="text-xs text-gray-400">暂无事件记录</p>
          ) : (
            <div className="space-y-2">
              {Object.entries(analytics.eventBreakdown)
                .sort(([, a], [, b]) => b - a)
                .map(([event, count]) => {
                  const info = eventLabels[event] || { label: event, icon: '📌' };
                  const maxCount = Math.max(...Object.values(analytics.eventBreakdown));
                  const pct = Math.round((count / maxCount) * 100);
                  return (
                    <div key={event} className="flex items-center gap-2">
                      <span className="w-5 text-xs">{info.icon}</span>
                      <span className="text-xs text-gray-600 w-20 flex-shrink-0">{info.label}</span>
                      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-brand-400 to-brand-600 rounded-full transition-all duration-500"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-xs font-semibold text-gray-700 w-6 text-right">{count}</span>
                    </div>
                  );
                })}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* 薄弱知识点 */}
        <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-400" />
            薄弱知识点
          </h3>
          {analytics.weakTopics.length === 0 ? (
            <p className="text-xs text-gray-400">暂无数据，完成练习后可自动分析</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {analytics.weakTopics.map((topic, i) => (
                <span
                  key={i}
                  className="px-3 py-1.5 bg-red-50 text-red-600 border border-red-100 rounded-xl text-xs font-medium"
                >
                  {topic}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* 推荐建议 */}
        <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-brand-500" />
            学习建议
          </h3>
          {analytics.recommendations.length === 0 ? (
            <p className="text-xs text-gray-400">暂无建议，持续学习后系统将自动生成</p>
          ) : (
            <div className="space-y-2">
              {analytics.recommendations.map((rec, i) => (
                <div key={i} className="flex items-start gap-2 p-2.5 bg-brand-50/50 rounded-xl">
                  <ArrowRight className="w-4 h-4 text-brand-500 flex-shrink-0 mt-0.5" />
                  <p className="text-xs text-brand-700 leading-relaxed">{rec}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 热门资源 */}
      {analytics.topResources.length > 0 && (
        <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm mb-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-brand-500" />
            常用学习资源
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
            {analytics.topResources.map((r) => (
              <div key={r.resourceId} className="flex items-center justify-between p-2.5 bg-gray-50 rounded-xl">
                <span className="text-xs text-gray-600 truncate flex-1">{r.resourceId}</span>
                <span className="text-xs font-semibold text-gray-400 ml-2">×{r.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
