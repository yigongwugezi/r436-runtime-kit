import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  TrendingUp, Zap, Target, BookOpen, Clock, Brain,
  AlertCircle, Sparkles, ArrowRight, Star, RefreshCw,
  BarChart3, Activity, Eye, MessageSquare, Cpu, GitFork,
  CheckCircle2, Shield,
} from 'lucide-react';
import {
  PageLoading, PageEmpty, PageError, SourceTag, FallbackBanner, RefreshOverlay,
} from '../components/common/PageState';
import { formatDuration } from '../utils/format';
import { useLearningAnalytics } from '../hooks/useLearningAnalytics';
import type { AnalyticsSummary } from '../types/analytics';
import { useSubjectStore } from '../store/subjectStore';
import DiagnosisPanel from '../components/analytics/DiagnosisPanel';
import { useChatStore } from '../store/chatStore';
import { getLearningPath } from '../api/learningPath';

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
  const navigate = useNavigate();
  const subjectId = useSubjectStore((s) => s.activeSubject?.id);
  const { analytics, loading, error, refetch } = useLearningAnalytics();

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
        onRetry={refetch}
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
    practice_result:   { label: '实操完成', icon: '💻',  color: 'text-cyan-500' },
    quiz_submit:       { label: '提交练习', icon: '📝',  color: 'text-amber-500' },
    quiz_result:       { label: '练习结果', icon: '📝',  color: 'text-amber-500' },
    feedback:          { label: '资源评价', icon: '💬',  color: 'text-purple-500' },
    chat_feedback:     { label: '对话反馈', icon: '💬',  color: 'text-brand-500' },
    node_progress:     { label: '节点进度', icon: '📈',  color: 'text-emerald-500' },
    page_view:         { label: '页面访问', icon: '👁',  color: 'text-gray-400' },
  };

  /** 获取最近事件的友好描述 */
  const eventDescription = (evt: AnalyticsSummary['recentEvents'][0]): string => {
    const meta = evt.metadata || {};
    switch (evt.event) {
      case 'resource_view':     return `查看了资源「${meta.title || meta.type || ''}」`;
      case 'resource_complete': return `完成了资源「${meta.title || meta.type || ''}」`;
      case 'practice_result':   return `完成了实操「${meta.title || ''}」`;
      case 'quiz_result':       return `完成练习：正确 ${meta.correct}/${meta.total}（${meta.accuracy}%）`;
      case 'feedback':          return `评价资源：${meta.rating} 星`;
      case 'node_progress':     return `完成了阶段「${meta.stageTitle || ''}」`;
      case 'page_view':         return `访问了页面「${meta.page || ''}」`;
      case 'chat_feedback':     return '提交了对话反馈';
      default:                  return `${evt.event}: ${JSON.stringify(meta).slice(0, 40)}`;
    }
  };

  const isFallback = !analytics.summary || analytics.recommendations.length === 0;

  // 从 eventBreakdown 推导统计（优先使用后端直接返回的字段）
  const resourceViewCount = analytics.resourceViewCount ?? analytics.eventBreakdown['resource_view'] ?? 0;
  const resourceCompleteCount = analytics.resourceCompleteCount ?? analytics.eventBreakdown['resource_complete'] ?? 0;

  // 最近学习时间（优先使用后端 lastStudyTime，再回退到前端推导）
  const lastEventTime = analytics.lastStudyTime
    ? analytics.lastStudyTime
    : analytics.recentEvents.length > 0
    ? Math.max(
        ...analytics.recentEvents
          .map((e) => (typeof e.timestamp === 'number' ? e.timestamp : e.timestamp ? new Date(e.timestamp).getTime() : 0))
          .filter(Boolean),
      )
    : null;

  /** 格式化时间戳（后端可能返回 epoch ms 或 ISO 字符串） */
  const formatEventTime = (ts: number | string | undefined): string => {
    if (!ts) return '';
    try {
      const d = typeof ts === 'number' ? new Date(ts) : new Date(ts);
      if (isNaN(d.getTime())) return '';
      const now = new Date();
      const diffMs = now.getTime() - d.getTime();
      const diffMin = Math.floor(diffMs / 60000);
      if (diffMin < 1) return '刚刚';
      if (diffMin < 60) return `${diffMin} 分钟前`;
      const diffHour = Math.floor(diffMin / 60);
      if (diffHour < 24) return `${diffHour} 小时前`;
      return d.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch { return ''; }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 md:py-8 relative">
      {/* ========== 刷新遮罩 ========== */}
      {loading && analytics && <RefreshOverlay />}

      {/* ========== 错误横幅（已有数据但刷新失败） ========== */}
      {error && analytics && (
        <div className="mb-6 p-3 bg-red-50 border border-red-100 rounded-xl flex items-center gap-2 text-xs text-red-600">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
          <button onClick={refetch} className="ml-auto flex items-center gap-1 px-2 py-1 bg-red-100 rounded-lg hover:bg-red-200 transition-colors">
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
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-brand-500" />
            <span className="text-xs font-bold text-brand-500 uppercase tracking-wider">Learning Analytics</span>
          </div>
          <button
            onClick={refetch}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-medium text-gray-500 bg-gray-50 hover:bg-gray-100 hover:text-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            title="刷新分析数据"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
        <h1 className="text-2xl md:text-3xl font-extrabold text-gray-900 mb-1">学习分析</h1>
        <div className="flex items-center gap-2 mt-1">
          <p className="text-sm text-gray-500">{analytics.summary || '基于你的学习行为自动生成'}</p>
          <SourceTag source={analytics.eventCount > 0 ? 'agent_generated' : 'system_inferred'} />
        </div>
      </div>

      {/* ========== 关键发现摘要 ========== */}
      <div className="mb-6 p-4 bg-gradient-to-r from-brand-50 to-blue-50 border border-brand-100 rounded-2xl">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-xl bg-brand-100 flex items-center justify-center flex-shrink-0">
            <Brain className="w-4 h-4 text-brand-600" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-gray-800 mb-1">学习洞察摘要</h3>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600">
              {analytics.totalStudyMinutes > 0 && (
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3 text-blue-400" />
                  累计学习 {formatDuration(analytics.totalStudyMinutes)}
                </span>
              )}
              {analytics.activeResourceCount > 0 && (
                <span className="flex items-center gap-1">
                  <BookOpen className="w-3 h-3 text-green-400" />
                  交互过 {analytics.activeResourceCount} 个资源
                </span>
              )}
              {analytics.quizAccuracy != null && (
                <span className="flex items-center gap-1">
                  <Target className="w-3 h-3 text-amber-400" />
                  正确率 {analytics.quizAccuracy}%
                </span>
              )}
              {analytics.weakTopics.length > 0 && (
                <span className="flex items-center gap-1">
                  <AlertCircle className="w-3 h-3 text-red-400" />
                  {analytics.weakTopics.length} 个薄弱知识点待加强
                </span>
              )}
              {analytics.totalStudyMinutes === 0 && analytics.activeResourceCount === 0 && (
                <span>开始学习后，这里将展示你的学习数据洞察</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 核心指标卡片 - 大屏自动分布 */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 xl:grid-cols-6 gap-3 mb-8">
        <StatCard
          icon={<Clock className="w-5 h-5 text-blue-500" />}
          label="学习时长"
          value={formatDuration(analytics.totalStudyMinutes)}
          color="bg-blue-50"
        />
        <StatCard
          icon={<Eye className="w-5 h-5 text-indigo-500" />}
          label="查看资源"
          value={resourceViewCount}
          color="bg-indigo-50"
        />
        <StatCard
          icon={<CheckCircle2 className="w-5 h-5 text-green-500" />}
          label="完成资源"
          value={resourceCompleteCount}
          color="bg-green-50"
        />
        <StatCard
          icon={<Target className="w-5 h-5 text-amber-500" />}
          label="练习正确率"
          value={analytics.quizAccuracy != null ? `${analytics.quizAccuracy}%` : '--'}
          color="bg-amber-50"
        />
        <StatCard
          icon={<Zap className="w-5 h-5 text-purple-500" />}
          label="学习事件"
          value={analytics.eventCount}
          color="bg-purple-50"
        />
        <StatCard
          icon={<Clock className="w-5 h-5 text-rose-500" />}
          label="最近学习"
          value={lastEventTime ? formatEventTime(lastEventTime) : '--'}
          color="bg-rose-50"
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
            <ProgressRing pct={analytics.quizAccuracy ?? 0} size={100} />
            <div className="text-sm text-gray-500 space-y-1">
              <p>
                {analytics.quizAccuracy == null
                  ? '📝 完成练习后开始统计'
                  : analytics.quizAccuracy >= 80
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

        {/* 事件分布 — 已移至图表区 */}
        <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Zap className="w-4 h-4 text-brand-500" />
            学习行为分布
          </h3>
          <EventDistributionChart data={analytics.eventBreakdown} eventLabels={eventLabels} />
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
            <div className="space-y-3">
              {analytics.weakTopics.map((topic, i) => {
                const riskPct = Math.round((topic.risk ?? 0) * 100);
                const riskColor = riskPct >= 70 ? 'bg-red-50 border-red-200' : riskPct >= 40 ? 'bg-amber-50 border-amber-200' : 'bg-yellow-50 border-yellow-200';
                const riskTextColor = riskPct >= 70 ? 'text-red-700' : riskPct >= 40 ? 'text-amber-700' : 'text-yellow-700';
                return (
                  <div key={i} className={`${riskColor} border rounded-xl p-3 space-y-2`}>
                    {/* 第一行：知识点名 + 风险 */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className={`text-xs font-semibold ${riskTextColor} truncate`}>{topic.topic}</span>
                        {/* 优先级徽章 */}
                        {topic.priority === 'high' && (
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-red-200 text-red-700 flex-shrink-0">
                            高优
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                        <span className="text-[10px] text-gray-400">
                          错 {topic.wrongCount}/{topic.totalCount}
                        </span>
                        <div className="w-16 h-1.5 rounded-full bg-gray-200 overflow-hidden">
                          <div
                            className={`h-full rounded-full ${riskPct >= 70 ? 'bg-red-400' : riskPct >= 40 ? 'bg-amber-400' : 'bg-yellow-400'}`}
                            style={{ width: `${riskPct}%` }}
                          />
                        </div>
                        <span className={`text-[10px] font-medium ${riskTextColor}`}>{riskPct}%</span>
                      </div>
                    </div>

                    {/* 第二行：来源标签 */}
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {topic.source?.map((src) => (
                        <span
                          key={src}
                          className={`px-1.5 py-0.5 rounded text-[9px] font-medium border ${
                            src === 'quiz' ? 'bg-blue-50 text-blue-600 border-blue-200' :
                            src === 'practice' ? 'bg-cyan-50 text-cyan-600 border-cyan-200' :
                            src === 'feedback' ? 'bg-purple-50 text-purple-600 border-purple-200' :
                            src === 'diagnosis' ? 'bg-amber-50 text-amber-600 border-amber-200' :
                            'bg-gray-50 text-gray-500 border-gray-200'
                          }`}
                        >
                          {src === 'quiz' ? '📝 练习' : src === 'practice' ? '💻 实操' : src === 'feedback' ? '💬 反馈' : src === 'diagnosis' ? '🔍 诊断' : src}
                        </span>
                      ))}
                      {/* 推荐理由 */}
                      {topic.reason && (
                        <span className="text-[9px] text-gray-400 ml-1 truncate max-w-[200px]" title={topic.reason}>
                          {topic.reason}
                        </span>
                      )}
                    </div>

                    {/* 第三行：操作按钮 */}
                    <div className="flex items-center gap-2 pt-0.5">
                      <button
                        onClick={() => navigate(`/resources?knowledgePoint=${encodeURIComponent(topic.topic)}`)}
                        className="px-2.5 py-1 rounded-lg text-[9px] font-medium bg-white border border-gray-200 text-gray-500 hover:border-brand-300 hover:text-brand-600 transition-all flex items-center gap-1"
                      >
                        <BookOpen className="w-3 h-3" />
                        推荐资源
                      </button>
                      <button
                        onClick={() => navigate(`/chat?prompt=${encodeURIComponent(`帮我讲解一下${topic.topic}，我这个地方掌握得不太好`)}`)}
                        className="px-2.5 py-1 rounded-lg text-[9px] font-medium bg-white border border-gray-200 text-gray-500 hover:border-brand-300 hover:text-brand-600 transition-all flex items-center gap-1"
                      >
                        <MessageSquare className="w-3 h-3" />
                        去提问
                      </button>
                    </div>
                  </div>
                );
              })}
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

      {/* ========== 图表区域 ========== */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* 1. 资源完成趋势 */}
        <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-green-500" />
            资源完成趋势
          </h3>
          <CompletionTrendChart data={analytics.completionTrend} />
        </div>

        {/* 2. Quiz 正确率趋势 */}
        <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-amber-500" />
            Quiz 正确率趋势
          </h3>
          <QuizTrendChart data={analytics.quizTrend} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        {/* 3. 学习事件类型分布 */}
        <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Activity className="w-4 h-4 text-purple-500" />
            事件类型分布
          </h3>
          <EventDistributionChart
            data={analytics.eventBreakdown}
            eventLabels={eventLabels}
          />
        </div>

        {/* 4. 各资源类型使用次数 */}
        <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-cyan-500" />
            资源类型使用
          </h3>
          <ResourceTypeChart data={analytics.resourceTypeBreakdown} />
        </div>

        {/* 5. 阶段完成度（从学习路径获取） */}
        <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Target className="w-4 h-4 text-rose-500" />
            阶段完成度
          </h3>
          <StageProgressCard />
        </div>
      </div>

      {/* ========== 最近学习行为 ========== */}
      <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm mb-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
            <Activity className="w-4 h-4 text-brand-500" />
            最近学习行为
          </h3>
          <button
            onClick={() => navigate('/timeline')}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-[10px] font-medium text-brand-600 bg-brand-50 hover:bg-brand-100 transition-colors"
            title="查看完整时间线"
          >
            <Activity className="w-3 h-3" />
            查看完整时间线
            <ArrowRight className="w-3 h-3" />
          </button>
        </div>
        {analytics.recentEvents && analytics.recentEvents.length > 0 ? (
          <div className="space-y-0 scrollable-list">
            {[...analytics.recentEvents].reverse().slice(-5).reverse().map((evt, i) => {
              const info = eventLabels[evt.event] || { label: evt.event, icon: '📌', color: 'text-gray-400' };
              const desc = eventDescription(evt);
              const timeStr = formatEventTime(evt.timestamp as number | string | undefined);
              return (
                <div key={i} className="flex items-start gap-3 py-2.5 border-b border-gray-50 last:border-0">
                  {/* 时间线圆点 */}
                  <div className="flex flex-col items-center mt-1">
                    <div className={`w-2.5 h-2.5 rounded-full ${info.color.replace('text-', 'bg-')}/60 ring-2 ring-white`} />
                    {i < Math.min(analytics.recentEvents.length - 1, 4) && (
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
                      {timeStr && ` · ${timeStr}`}
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

      {/* ========== 诊断建议入口 ========== */}
      <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm mb-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
            <Shield className="w-4 h-4 text-brand-500" />
            诊断建议
          </h3>
          {analytics.weakTopics.length > 0 && (
            <button
              onClick={() => {
                const el = document.getElementById('diagnosis-panel-analytics');
                el?.scrollIntoView({ behavior: 'smooth' });
              }}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-[10px] font-medium text-brand-600 bg-brand-50 hover:bg-brand-100 transition-colors"
              title="查看诊断详情"
            >
              <Shield className="w-3 h-3" />
              查看详情
              <ArrowRight className="w-3 h-3" />
            </button>
          )}
        </div>

        {analytics.weakTopics.length > 0 ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs text-gray-500 mb-2">
              <AlertCircle className="w-3.5 h-3.5" />
              检测到 <span className="font-semibold text-gray-700">{analytics.weakTopics.length}</span> 个薄弱知识点，
              系统已生成针对性学习建议
            </div>
            <div className="flex flex-wrap gap-2">
              {analytics.weakTopics.slice(0, 5).map((topic, i) => (
                <span
                  key={i}
                  className={`px-2.5 py-1 rounded-lg text-[10px] font-medium border ${
                    topic.priority === 'high'
                      ? 'bg-red-50 text-red-600 border-red-200'
                      : topic.priority === 'medium'
                        ? 'bg-amber-50 text-amber-600 border-amber-200'
                        : 'bg-blue-50 text-blue-600 border-blue-200'
                  }`}
                >
                  {topic.topic}
                  {topic.priority === 'high' && ' 🔥'}
                </span>
              ))}
              {analytics.weakTopics.length > 5 && (
                <span className="px-2.5 py-1 rounded-lg text-[10px] font-medium bg-gray-50 text-gray-400 border border-gray-100">
                  +{analytics.weakTopics.length - 5} 更多
                </span>
              )}
            </div>
            {analytics.recommendations.length > 0 && (
              <div className="mt-2 p-3 bg-brand-50/50 rounded-xl">
                <p className="text-xs text-brand-700 leading-relaxed">
                  💡 {analytics.recommendations[0]}
                </p>
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center py-6 text-center">
            <Shield className="w-8 h-8 text-gray-200 mb-2" />
            <p className="text-xs text-gray-400">暂无诊断建议</p>
            <p className="text-[10px] text-gray-300 mt-1">完成更多学习任务后自动生成诊断分析</p>
          </div>
        )}
      </div>

      {/* ========== 诊断详情面板（折叠区域） ========== */}
      {analytics.weakTopics.length > 0 && (
        <div id="diagnosis-panel-analytics" className="mb-6 bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Shield className="w-4 h-4 text-brand-500" />
            诊断详情
          </h3>
          <DiagnosisPanel
            diagnosis={{
              weakTopics: analytics.weakTopics.map((t) => ({
                topic: t.topic,
                priority: (t.priority as 'high' | 'medium' | 'low') || 'medium',
                reason: t.reason,
                mastery: t.mastery,
                wrongCount: t.wrongCount,
                totalCount: t.totalCount,
                confidence: t.risk != null ? 1 - t.risk : undefined,
              })),
              summary: analytics.summary || undefined,
              confidence: analytics.weakTopics.length > 0 ? 0.7 : undefined,
              source: analytics.eventCount > 0 ? 'agent_generated' : 'system_inferred',
            }}
          />
        </div>
      )}

      {/* ========== 系统调整说明 ========== */}
      <div className="bg-gradient-to-r from-brand-50 to-purple-50 border border-brand-100 rounded-2xl p-6 shadow-sm mb-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
          <Cpu className="w-4 h-4 text-brand-500" />
          系统自适应调整说明
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 xl:grid-cols-3 gap-4">
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

/* ===================================================================
 * 图表子组件
 * =================================================================== */

/** 1. 资源完成趋势 - 迷你柱状图 */
function CompletionTrendChart({ data }: { data: { date: string; count: number }[] }) {
  const hasData = data.some(d => d.count > 0);
  const maxCount = Math.max(...data.map(d => d.count), 1);
  const visibleData = data.slice(-7);

  if (!hasData) {
    return (
      <div className="flex flex-col items-center justify-center py-10 text-center">
        <BarChart3 className="w-8 h-8 text-gray-200 mb-2" />
        <p className="text-xs text-gray-400">暂无资源完成记录</p>
        <p className="text-[10px] text-gray-300 mt-1">完成学习资源后自动生成</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-end gap-1 h-32 mb-2">
        {visibleData.map((item) => {
          const h = Math.max((item.count / maxCount) * 100, item.count > 0 ? 8 : 2);
          return (
            <div key={item.date} className="flex-1 flex flex-col items-center gap-1 group">
              <span className="text-[9px] text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity">{item.count}</span>
              <div className="w-full rounded-t-sm transition-all duration-300 group-hover:opacity-80"
                style={{ height: `${h}%`, backgroundColor: item.count > 0 ? '#22c55e' : '#f1f5f9', minHeight: item.count > 0 ? '4px' : '2px' }} />
              <span className="text-[8px] text-gray-400 whitespace-nowrap">{item.date.slice(5)}</span>
            </div>
          );
        })}
      </div>
      <p className="text-[10px] text-gray-400 text-center">
        累计完成 <span className="font-semibold text-gray-600">{data.reduce((s, d) => s + d.count, 0)}</span> 个资源
      </p>
    </div>
  );
}

/** 2. Quiz 正确率趋势 - SVG折线图 */
function QuizTrendChart({ data }: { data: { date: string; accuracy: number; topic: string }[] }) {
  if (!data || data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-10 text-center">
        <TrendingUp className="w-8 h-8 text-gray-200 mb-2" />
        <p className="text-xs text-gray-400">暂无练习记录</p>
        <p className="text-[10px] text-gray-300 mt-1">完成练习后自动生成</p>
      </div>
    );
  }
  const points = data.slice(-15);
  const svgW = 280, svgH = 100, padL = 5, padR = 5, padT = 8, padB = 5;
  const chartW = svgW - padL - padR, chartH = svgH - padT - padB;
  const xStep = points.length > 1 ? chartW / (points.length - 1) : chartW / 2;
  const linePath = points.map((p, i) => {
    const x = padL + i * xStep;
    const y = padT + chartH - (p.accuracy / 100) * chartH;
    return `${i === 0 ? 'M' : 'L'}${x},${y}`;
  }).join(' ');

  return (
    <div>
      <svg viewBox={`0 0 ${svgW} ${svgH}`} className="w-full h-28">
        <line x1={padL} y1={padT} x2={padL + chartW} y2={padT} stroke="#f1f5f9" strokeWidth={1} />
        <line x1={padL} y1={padT + chartH / 2} x2={padL + chartW} y2={padT + chartH / 2} stroke="#f1f5f9" strokeWidth={1} />
        <line x1={padL} y1={padT + chartH} x2={padL + chartW} y2={padT + chartH} stroke="#f1f5f9" strokeWidth={1} />
        <line x1={padL} y1={padT + chartH / 2} x2={padL + chartW} y2={padT + chartH / 2} stroke="#fde68a" strokeWidth={1} strokeDasharray="4,3" />
        <path d={linePath} fill="none" stroke="#f59e0b" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {points.map((p, i) => {
          const x = padL + i * xStep, y = padT + chartH - (p.accuracy / 100) * chartH;
          const color = p.accuracy >= 80 ? '#22c55e' : p.accuracy >= 60 ? '#f59e0b' : '#ef4444';
          return <circle key={i} cx={x} cy={y} r={3.5} fill={color} stroke="white" strokeWidth={1.5}>
            <title>{`${p.topic || '练习'}: ${p.accuracy}%\n${p.date}`}</title>
          </circle>;
        })}
      </svg>
      <div className="flex items-center justify-between text-[10px] text-gray-400 mt-1">
        <span>最近 {points.length} 次练习</span>
        <span className="flex items-center gap-2">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500" />&ge;80%</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-500" />60-79%</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500" />&lt;60%</span>
        </span>
      </div>
    </div>
  );
}

/** 3. 事件类型分布 - 水平条形图（替换原有简单列表） */
function EventDistributionChart({
  data, eventLabels,
}: {
  data: Record<string, number>;
  eventLabels: Record<string, { label: string; icon: string; color: string }>;
}) {
  const entries = Object.entries(data).sort(([, a], [, b]) => b - a);
  if (entries.length === 0) {
    return <div className="flex flex-col items-center justify-center py-10 text-center">
      <Activity className="w-8 h-8 text-gray-200 mb-2" /><p className="text-xs text-gray-400">暂无事件记录</p>
    </div>;
  }
  const maxCount = Math.max(...Object.values(data));
  const barColor: Record<string, string> = {
    resource_view: '#6366f1', resource_complete: '#22c55e', quiz_result: '#f59e0b',
    feedback: '#a855f7', practice_result: '#06b6d4', node_progress: '#10b981',
  };
  return (
    <div className="space-y-2.5">
      {entries.map(([event, count]) => {
        const info = eventLabels[event] || { label: event, icon: '📌', color: 'text-gray-400' };
        const pct = Math.round((count / maxCount) * 100);
        return (
          <div key={event} className="flex items-center gap-2">
            <span className="w-4 text-xs flex-shrink-0">{info.icon}</span>
            <span className="text-[11px] text-gray-600 w-22 flex-shrink-0 truncate">{info.label}</span>
            <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
              <div className="h-full rounded-full transition-all duration-500"
                style={{ width: `${Math.max(pct, 4)}%`, backgroundColor: barColor[event] || '#94a3b8' }} />
            </div>
            <span className="text-xs font-semibold text-gray-600 w-5 text-right">{count}</span>
          </div>
        );
      })}
    </div>
  );
}

/** 4. 各资源类型使用次数 - 水平条形图 */
function ResourceTypeChart({ data }: { data: Record<string, number> }) {
  const TYPE_LABELS: Record<string, string> = {
    lecture: '课程讲义', mindmap: '思维导图', quiz: '练习题',
    reading: '拓展阅读', case_study: '实操案例', video: '教学视频', ppt: 'PPT大纲', practice: '实操',
  };
  const TYPE_COLORS: Record<string, string> = {
    lecture: '#3b82f6', mindmap: '#8b5cf6', quiz: '#f59e0b',
    reading: '#22c55e', case_study: '#06b6d4', video: '#ef4444', ppt: '#f97316', practice: '#14b8a6',
  };
  const entries = Object.entries(data).sort(([, a], [, b]) => b - a);
  if (entries.length === 0) {
    return <div className="flex flex-col items-center justify-center py-10 text-center">
      <BookOpen className="w-8 h-8 text-gray-200 mb-2" /><p className="text-xs text-gray-400">暂无资源使用数据</p>
    </div>;
  }
  const maxCount = Math.max(...Object.values(data));
  return (
    <div className="space-y-2.5">
      {entries.map(([type, count]) => (
        <div key={type} className="flex items-center gap-2">
          <span className="text-[11px] text-gray-600 w-20 flex-shrink-0 truncate">{TYPE_LABELS[type] || type}</span>
          <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
            <div className="h-full rounded-full transition-all duration-500"
              style={{ width: `${Math.max(Math.round((count / maxCount) * 100), 4)}%`, backgroundColor: TYPE_COLORS[type] || '#94a3b8' }} />
          </div>
          <span className="text-xs font-semibold text-gray-600 w-5 text-right">{count}</span>
        </div>
      ))}
    </div>
  );
}

/** 5. 阶段完成度 - 从学习路径API获取 */
function StageProgressCard() {
  const navigate = useNavigate();
  const [stages, setStages] = useState<{ id: string; title: string; progress: number; total: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const sessionId = useChatStore((s) => s.currentSessionId);

  useEffect(() => {
    if (!sessionId) { setLoading(false); return; }
    getLearningPath({ sessionId })
      .then((res) => {
        const path = res?.path;
        const stagesList = path?.stages || [];
        if (stagesList.length > 0) {
          setStages(stagesList.map((s: { id?: string; title?: string; nodes?: { status?: string }[] }) => ({
            id: s.id || '',
            title: s.title || '',
            progress: (s.nodes || []).filter(
              (n) => n?.status === 'completed' || n?.status === 'mastered'
            ).length,
            total: (s.nodes || []).length,
          })));
        }
      })
      .catch(() => { /* silent */ })
      .finally(() => setLoading(false));
  }, [sessionId]);

  if (loading) return <div className="flex items-center justify-center py-10"><div className="w-5 h-5 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" /></div>;
  if (stages.length === 0) return <div className="flex flex-col items-center justify-center py-10 text-center">
    <Target className="w-8 h-8 text-gray-200 mb-2" /><p className="text-xs text-gray-400">暂无学习阶段</p>
  </div>;

  return (
    <div className="space-y-3">
      {stages.map((stage) => {
        const pct = stage.total > 0 ? Math.round((stage.progress / stage.total) * 100) : 0;
        return (
          <div
            key={stage.id}
            onClick={() => navigate(`/path?stageId=${stage.id}`)}
            className="cursor-pointer hover:bg-gray-50 rounded-xl p-2 -mx-2 transition-colors group"
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-[11px] font-medium text-gray-700 truncate group-hover:text-brand-600 transition-colors">{stage.title}</span>
              <span className="text-[10px] text-gray-400 flex-shrink-0 ml-2">{stage.progress}/{stage.total}</span>
            </div>
            <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
              <div className="h-full rounded-full transition-all duration-500"
                style={{ width: `${pct}%`, backgroundColor: pct >= 100 ? '#22c55e' : pct >= 50 ? '#6366f1' : '#f59e0b' }} />
            </div>
          </div>
        );
      })}
      {/* 查看完整路径 */}
      <button
        onClick={() => navigate('/path')}
        className="w-full mt-2 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-[10px] font-medium text-gray-400 border border-gray-100 hover:border-brand-200 hover:text-brand-600 transition-all"
      >
        <GitFork className="w-3.5 h-3.5" />
        查看完整学习路径
      </button>
    </div>
  );
}
