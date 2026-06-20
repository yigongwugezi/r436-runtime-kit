import { useState, useEffect, useCallback, useRef } from 'react';
import client from '../api/client';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';
import {
  TrendingUp, Zap, Target, BookOpen, Clock, Brain,
  AlertCircle, Sparkles, ArrowRight, Star, RefreshCw,
  BarChart3, Activity, ListChecks, Eye, MessageSquare, HelpCircle, Cpu,
  CheckCircle2, User,
} from 'lucide-react';
import {
  PageLoading, PageEmpty, PageError, SourceTag, FallbackBanner, RefreshOverlay,
} from '../components/common/PageState';
import { formatDuration } from '../utils/format';

/* ===================================================================
 * 类型
 * =================================================================== */
interface AnalyticsData {
  eventCount: number;
  totalStudyMinutes: number;
  activeResourceCount: number;
  eventBreakdown: Record<string, number>;
  topResources: { resourceId: string; count: number; title?: string }[];
  quizAccuracy: number;
  weakTopics: string[];
  recommendations: string[];
  recentEvents: { event: string; timestamp?: number; metadata?: Record<string, unknown> }[];
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
  const dataVersion = useChatStore((state) => state.dataVersion);
  const lastVersionRef = useRef<number>(0);

  const fetchAnalytics = useCallback(async () => {
    const sid = useChatStore.getState().currentSessionId;
    if (!subjectId && !sid) return;
    setLoading(true);
    setError(null);
    try {
      const { data } = await client.get('/learning-analytics', {
        params: { sessionId: sid, subjectId },
      });
      setAnalytics(data);
    } catch {
      setError('加载分析数据失败');
    } finally {
      setLoading(false);
    }
  }, [subjectId]);

  // 科目切换时重新获取
  useEffect(() => {
    if (subjectId && lastSubjectRef.current !== subjectId) {
      lastSubjectRef.current = subjectId;
      fetchAnalytics();
    }
    if (!subjectId) {
      setLoading(false);
      setError(null);
      setAnalytics(null);
    }
  }, [subjectId, fetchAnalytics]);

  // 对话完成后自动刷新（dataVersion 递增时）
  useEffect(() => {
    if (dataVersion > 0 && dataVersion !== lastVersionRef.current) {
      lastVersionRef.current = dataVersion;
      fetchAnalytics();
    }
  }, [dataVersion, fetchAnalytics]);

  // —— 无科目 ——
  if (!subjectId) {
    return (
      <PageEmpty
        icon={<TrendingUp className="w-8 h-8" />}
        title="请先选择科目"
        description="在左侧边栏或个人中心选择一个科目后查看学习分析"
      />
    );
  }

  // —— Loading（首次） ——
  if (loading && !analytics) {
    return <PageLoading text="正在分析你的学习数据…" />;
  }

  // —— Error（首次） ——
  if (error && !analytics) {
    return (
      <PageError
        title="加载分析数据失败"
        description={error}
        onRetry={fetchAnalytics}
      />
    );
  }

  // —— 空数据 ——
  if (!loading && !error && analytics && analytics.eventCount === 0) {
    return (
      <PageEmpty
        icon={<TrendingUp className="w-8 h-8" />}
        title="暂无学习分析数据"
        description="完成学习任务、提交反馈或做题后，系统将自动生成你的学习分析报告"
      />
    );
  }

  if (!analytics) return null;

  // 事件标签映射
  const eventLabels: Record<string, { label: string; icon: string; color: string }> = {
    resource_view:     { label: '查看资源', icon: '👁',  color: 'text-blue-500' },
    resource_complete: { label: '完成学习', icon: '✅',  color: 'text-green-500' },
    quiz_submit:       { label: '提交练习', icon: '📝',  color: 'text-amber-500' },
    quiz_result:       { label: '练习结果', icon: '📝',  color: 'text-amber-500' },
    feedback:          { label: '资源评价', icon: '💬',  color: 'text-purple-500' },
    chat_feedback:     { label: '对话反馈', icon: '💬',  color: 'text-brand-500' },
    node_progress:     { label: '节点进度', icon: '📈',  color: 'text-emerald-500' },
    page_view:         { label: '页面访问', icon: '👁',  color: 'text-gray-400' },
  };

  /** 获取最近事件的友好描述 */
  const eventDescription = (evt: AnalyticsData['recentEvents'][0]): string => {
    const meta = evt.metadata || {};
    switch (evt.event) {
      case 'resource_view':     return `查看了资源「${meta.title || meta.type || ''}」`;
      case 'resource_complete': return `完成了资源「${meta.title || meta.type || ''}」`;
      case 'quiz_result':       return `完成练习：正确 ${meta.correct}/${meta.total}（${meta.accuracy}%）`;
      case 'feedback':          return `评价资源：${meta.rating} 星`;
      case 'node_progress':     return `完成了阶段「${meta.stageTitle || ''}」`;
      case 'page_view':         return `访问了页面「${meta.page || ''}」`;
      case 'chat_feedback':     return '提交了对话反馈';
      default:                  return `${evt.event}: ${JSON.stringify(meta).slice(0, 40)}`;
    }
  };

  const isFallback = !analytics.summary || analytics.recommendations.length === 0;

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 md:py-8 relative">
      {/* ========== 刷新遮罩 ========== */}
      {loading && analytics && <RefreshOverlay />}

      {/* ========== 错误横幅（已有数据但刷新失败） ========== */}
      {error && analytics && (
        <div className="mb-6 p-3 bg-red-50 border border-red-100 rounded-xl flex items-center gap-2 text-xs text-red-600">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
          <button onClick={fetchAnalytics} className="ml-auto flex items-center gap-1 px-2 py-1 bg-red-100 rounded-lg hover:bg-red-200 transition-colors">
            <RefreshCw className="w-3 h-3" /> 重试
          </button>
        </div>
      )}

      {/* ========== Fallback 提示 ========== */}
      {isFallback && !loading && (
        <FallbackBanner message="当前分析数据基于有限的学习事件生成，完成更多学习任务后可获得更精准的分析报告。" />
      )}

      {/* 头部 */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-2">
          <TrendingUp className="w-5 h-5 text-brand-500" />
          <span className="text-xs font-bold text-brand-500 uppercase tracking-wider">Learning Analytics</span>
        </div>
        <h1 className="text-2xl md:text-3xl font-extrabold text-gray-900 mb-1">学习分析</h1>
        <div className="flex items-center gap-2 mt-1">
          <p className="text-sm text-gray-500">{analytics.summary || '基于你的学习行为自动生成'}</p>
          <SourceTag source={analytics.eventCount > 0 ? 'agent_generated' : 'system_inferred'} />
        </div>
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
                基于 {analytics.eventBreakdown['quiz_result'] || analytics.eventBreakdown['quiz_submit'] || 0} 次练习统计
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

      {/* ========== 最近学习行为 ========== */}
      <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm mb-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <Activity className="w-4 h-4 text-brand-500" />
          最近学习行为
        </h3>
        {analytics.recentEvents && analytics.recentEvents.length > 0 ? (
          <div className="space-y-0">
            {[...analytics.recentEvents].reverse().slice(-10).reverse().map((evt, i) => {
              const info = eventLabels[evt.event] || { label: evt.event, icon: '📌', color: 'text-gray-400' };
              const desc = eventDescription(evt);
              return (
                <div key={i} className="flex items-start gap-3 py-2.5 border-b border-gray-50 last:border-0">
                  {/* 时间线圆点 */}
                  <div className="flex flex-col items-center mt-1">
                    <div className={`w-2.5 h-2.5 rounded-full ${info.color.replace('text-', 'bg-')}/60 ring-2 ring-white`} />
                    {i < Math.min(analytics.recentEvents.length - 1, 9) && (
                      <div className="w-px h-full min-h-[24px] bg-gray-100 mt-1" />
                    )}
                  </div>
                  {/* 事件图标 */}
                  <span className="text-xs flex-shrink-0 mt-0.5">{info.icon}</span>
                  {/* 事件描述 */}
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-gray-700 leading-relaxed">{desc}</p>
                    <p className="text-[10px] text-gray-400 mt-0.5">
                      {info.label}
                      {evt.timestamp && ` · ${new Date(evt.timestamp).toLocaleString('zh-CN', {
                        month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
                      })}`}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="flex flex-col items-center py-8 text-center">
            <Activity className="w-8 h-8 text-gray-200 mb-2" />
            <p className="text-xs text-gray-400">暂无学习行为记录</p>
            <p className="text-[10px] text-gray-300 mt-1">完成学习任务后，这里会展示详细的行为时间线</p>
          </div>
        )}
      </div>

      {/* ========== 高频使用资源 ========== */}
      {analytics.topResources.length > 0 && (
        <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm mb-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-brand-500" />
            高频使用资源
          </h3>
          <div className="space-y-2">
            {analytics.topResources.map((r, i) => {
              const maxCount = Math.max(...analytics.topResources.map(x => x.count));
              const pct = Math.round((r.count / maxCount) * 100);
              return (
                <div key={r.resourceId} className="flex items-center gap-3">
                  <span className="text-[10px] font-bold text-gray-400 w-4 text-right">{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="text-xs text-gray-700 truncate">{r.title || r.resourceId}</span>
                      <span className="text-[10px] font-semibold text-gray-400 ml-2">×{r.count}</span>
                    </div>
                    <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-brand-400 to-brand-600 rounded-full transition-all duration-500"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ========== 系统调整说明 ========== */}
      <div className="bg-gradient-to-r from-brand-50 to-purple-50 border border-brand-100 rounded-2xl p-6 shadow-sm mb-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
          <Cpu className="w-4 h-4 text-brand-500" />
          系统自适应调整说明
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="p-3 bg-white/70 rounded-xl">
            <div className="flex items-center gap-2 mb-1.5">
              <Target className="w-4 h-4 text-amber-500" />
              <span className="text-[10px] font-semibold text-amber-700">画像动态更新</span>
            </div>
            <p className="text-[10px] text-gray-500 leading-relaxed">
              系统根据 {analytics.eventCount} 条学习事件持续修正你的 {analytics.activeResourceCount} 个已交互资源画像维度，
              让学习推荐越来越精准。
            </p>
          </div>
          <div className="p-3 bg-white/70 rounded-xl">
            <div className="flex items-center gap-2 mb-1.5">
              <ArrowRight className="w-4 h-4 text-green-500" />
              <span className="text-[10px] font-semibold text-green-700">路径动态规划</span>
            </div>
            <p className="text-[10px] text-gray-500 leading-relaxed">
              学习路径根据节点掌握度和 {analytics.recommendations.length} 条系统建议自动调整，
              薄弱知识点将获得更多资源覆盖。
            </p>
          </div>
          <div className="p-3 bg-white/70 rounded-xl">
            <div className="flex items-center gap-2 mb-1.5">
              <Sparkles className="w-4 h-4 text-purple-500" />
              <span className="text-[10px] font-semibold text-purple-700">资源个性化</span>
            </div>
            <p className="text-[10px] text-gray-500 leading-relaxed">
              基于{analytics.weakTopics.length > 0 ? ` ${analytics.weakTopics.length} 个薄弱知识点` : '学习偏好'}，
              后续资源将针对性强化薄弱环节。
            </p>
          </div>
        </div>
      </div>

      {/* 底部说明 */}
      <div className="text-center py-6 border-t border-gray-50">
        <div className="flex items-center justify-center gap-2 mb-2">
          <SourceTag source={analytics.eventCount > 0 ? 'agent_generated' : 'system_inferred'} />
        </div>
        <p className="text-xs text-gray-400">
          累计追踪 {analytics.eventCount} 条学习事件 · 数据驱动个性化学习体验持续优化
        </p>
      </div>
    </div>
  );
}
