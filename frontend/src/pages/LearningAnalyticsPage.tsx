// @ts-nocheck
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { TrendingUp, TrendingDown, Zap, Target, BookOpen, Clock, Brain, AlertCircle, Star, RefreshCw, BarChart3, Activity, CheckCircle2 } from 'lucide-react';
import { PageLoading, PageEmpty, PageError, RefreshOverlay } from '../components/common/PageState';
import { formatDuration } from '../utils/format';
import { useLearningAnalytics } from '../hooks/useLearningAnalytics';
import { useNotificationPoller } from '../hooks/useNotificationPoller';
import { useChatStore } from '../store/chatStore';
import type { RecommendationItem } from '../types/analytics';
import { useSubjectStore } from '../store/subjectStore';
import { learningTaskRoute } from '../utils/learningTaskRoute';

function Ring({ pct }: { pct: number }) {
  const size = 72; const sw = 5; const r = (size - sw) / 2; const c = r * 2 * Math.PI; const o = c - (pct / 100) * c;
  const color = pct >= 80 ? '#16A34A' : pct >= 50 ? '#D97706' : '#DC2626';
  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width={size} height={size}><circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#E4E4E7" strokeWidth={sw} /><circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={sw} strokeLinecap="round" strokeDasharray={c} strokeDashoffset={o} transform={`rotate(-90 ${size / 2} ${size / 2})`} className="transition-all duration-700" /></svg>
      <span className="absolute text-sm font-bold" style={{ color }}>{pct}%</span>
    </div>
  );
}

export default function LearningAnalyticsPage() {
  const nav = useNavigate();
  const subjectId = useSubjectStore(s => s.activeSubject?.id ?? s.activeClassSubject?.subject);
  const sessionId = useChatStore(s => s.dataSessionId);
  const { analytics, loading, error, refetch } = useLearningAnalytics();
  const [aiAssessment, setAiAssessment] = useState<any>(null);
  // Poll for closed-loop assessment notifications
  useNotificationPoller(sessionId || '');
  if (!subjectId) return <PageEmpty icon={<TrendingUp className="w-8 h-8" />} title="请先选择科目" description="在左侧边栏选择一个科目后查看学习分析" />;
  if (loading && !analytics) return <PageLoading text="正在分析学习数据…" />;
  if (error && !analytics) return <PageError title="加载分析数据失败" description={error} onRetry={refetch} />;
  if (!analytics) return <PageEmpty icon={<TrendingUp className="w-8 h-8" />} title="暂无学习数据" description="开始学习后这里会显示学习分析报告" />;

  const eb = analytics.eventBreakdown ?? {};
  const rv = analytics.resourceViewCount ?? eb['resource_view'] ?? 0;
  const rc = analytics.resourceCompleteCount ?? eb['resource_complete'] ?? 0;
  const pathProgress = analytics.pathProgress;
  const continuePath = () => {
    const task = pathProgress?.nextTask;
    if (!task?.accessible) return;
    const supported = ['reading', 'document', 'lecture', 'read_doc', 'quiz', 'practice', 'exam', 'do_quiz', 'mindmap', 'resource'];
    if (!supported.includes(task.taskType)) return window.alert('当前任务类型暂不支持直接进入，请从学习路径查看。');
    nav(learningTaskRoute(task.taskType, { ...task.routeContext, returnTo: '/analytics' }));
  };

  return (
    <div className="space-y-6 animate-fade-in relative">
      {loading && analytics && <RefreshOverlay />}
      {error && <div className="px-4 py-3 bg-error-50 border border-error-200 rounded-xl text-sm text-error-600 flex items-center gap-2"><AlertCircle className="w-4 h-4" />{error}<button onClick={refetch} className="ml-auto px-3 py-1.5 bg-white rounded-lg text-xs font-medium">重试</button></div>}

      <div className="flex items-center justify-between">
        <div><h2 className="font-display text-2xl font-bold text-surface-800">学习分析</h2><p className="text-surface-500 mt-1">{analytics.summary || '基于你的学习行为自动生成'}</p></div>
        <button onClick={refetch} disabled={loading} className="flex items-center gap-2 px-4 py-2.5 bg-surface-50 text-surface-600 rounded-xl font-medium hover:bg-surface-100 transition-colors"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} />刷新</button>
      </div>

      <div className="grid grid-cols-4 gap-5">
        {[{ icon: <Clock className="w-5 h-5 text-primary-600" />, label: '学习时长', value: formatDuration(analytics.totalStudyMinutes), color: 'primary' },
          { icon: <BookOpen className="w-5 h-5 text-accent-600" />, label: '查看资源', value: rv, color: 'accent' },
          { icon: <CheckCircle2 className="w-5 h-5 text-success-600" />, label: '完成资源', value: rc, color: 'success' },
          { icon: <Target className="w-5 h-5 text-warning-600" />, label: '正确率', value: analytics.quizAccuracy != null ? `${analytics.quizAccuracy}%` : '--', color: 'warning' },
        ].map(s => {
          const cls: Record<string, string> = { primary: 'bg-primary-50 ring-1 ring-primary-100', accent: 'bg-accent-50 ring-1 ring-accent-100', warning: 'bg-warning-50 ring-1 ring-warning-100', success: 'bg-success-50 ring-1 ring-success-100' };
          return <div key={s.label} className="bg-white rounded-2xl p-5 shadow-soft hover:shadow-elevated transition-shadow"><div className="flex items-center justify-between mb-3"><div className={`w-10 h-10 rounded-xl ${cls[s.color]} flex items-center justify-center`}>{s.icon}</div></div><p className="text-sm text-surface-500 mb-1">{s.label}</p><p className="text-2xl font-bold text-surface-800">{typeof s.value === 'number' ? s.value : s.value}</p></div>;
        })}
      </div>

      {pathProgress && (
        <section className="bg-white rounded-2xl p-6 shadow-soft flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="font-display text-lg font-semibold text-surface-800">学习路径进度</h3>
            {pathProgress.pathCompleted ? <p className="mt-1 text-sm text-success-600">已完成全部 {pathProgress.totalStageCount} 个阶段</p> : <p className="mt-1 text-sm text-surface-500">{pathProgress.currentStageTitle || '当前阶段'} · 必需任务 {pathProgress.completedRequiredTaskCount}/{pathProgress.totalRequiredTaskCount} · 阶段 {pathProgress.completedStageCount}/{pathProgress.totalStageCount}</p>}
            <div className="mt-3 h-2 w-full max-w-md overflow-hidden rounded-full bg-surface-100"><div className="h-full bg-primary-500" style={{ width: `${pathProgress.taskProgressPercent}%` }} /></div>
          </div>
          {!pathProgress.pathCompleted && pathProgress.nextTask && <button onClick={continuePath} className="rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-primary-700">继续当前阶段</button>}
        </section>
      )}

      {pathProgress === null && (
        <section className="bg-white rounded-2xl p-6 shadow-soft text-sm text-surface-500">暂无可分析的学习路径。</section>
      )}

      <div className="grid grid-cols-2 gap-6">
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <div className="flex items-center justify-between mb-5"><h3 className="font-display text-lg font-semibold text-surface-800">练习正确率</h3></div>
          <div className="flex items-center gap-5"><Ring pct={analytics.quizAccuracy ?? 0} /><div className="text-sm text-surface-500">{analytics.quizAccuracy == null ? '完成练习后统计' : analytics.quizAccuracy >= 80 ? '优秀，继续保持' : analytics.quizAccuracy >= 60 ? '不错，有进步空间' : '需要更多练习'}<p className="text-surface-400 mt-1 text-xs">基于 {eb['quiz_result'] || 0} 次练习</p></div></div>
        </div>

        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <div className="flex items-center justify-between mb-5"><h3 className="font-display text-lg font-semibold text-surface-800">学习行为分布</h3></div>
          {Object.entries(analytics.eventBreakdown || {}).length === 0 ? <p className="text-surface-400 text-sm py-8 text-center">暂无数据</p> : (
            <div className="space-y-3">
              {Object.entries(analytics.eventBreakdown).sort(([, a], [, b]) => b - a).slice(0, 5).map(([k, v]) => {
                const max = Math.max(...Object.values(analytics.eventBreakdown));
                return <div key={k} className="space-y-1.5"><div className="flex items-center justify-between text-sm"><span className="text-surface-600">{({resource_view:'查看资源',resource_complete:'完成资源',quiz_result:'练习结果',feedback:'评价',practice_result:'实操'})[k]||k}</span><span className="text-surface-500">{v}</span></div><div className="h-2 bg-surface-100 rounded-full overflow-hidden"><div className="h-full bg-primary-500 rounded-full transition-all duration-700" style={{ width: `${Math.max((v / max) * 100, 4)}%` }} /></div></div>;
              })}
            </div>
          )}
        </div>
      </div>

      {analytics.completionTrend && analytics.completionTrend.some((d: any) => d.count > 0) && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4">资源完成趋势</h3>
          <div className="flex items-end gap-1 h-32">
            {analytics.completionTrend.slice(-7).map((d: any) => { const max = Math.max(...analytics.completionTrend.map((x: any) => x.count), 1); const h = Math.max((d.count/max)*100, d.count>0?6:2); return <div key={d.date} className="flex-1 flex flex-col items-center gap-1"><div className="w-full rounded-t-sm bg-success-500 transition-all hover:opacity-80" style={{height:`${h}%`,minHeight:d.count>0?'4px':'2px'}} /><span className="text-[8px] text-surface-400">{d.date.slice(5)}</span></div>; })}
          </div>
          <p className="text-[10px] text-surface-400 text-center mt-2">累计完成 <span className="font-semibold text-surface-600">{analytics.completionTrend.reduce((s: number, d: any) => s + d.count, 0)}</span> 个资源</p>
        </div>
      )}

      {analytics.recentEvents && analytics.recentEvents.length > 0 && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4">最近学习行为</h3>
          <div className="space-y-0">
            {analytics.recentEvents.slice(-6).reverse().map((evt: any, i: number) => (
              <div key={i} className={`flex items-center gap-3 py-2.5 ${i < 5 ? 'border-b border-surface-100' : ''}`}>
                <span className="text-xs flex-shrink-0">{({resource_view:'👁',resource_complete:'✅',task_complete:'✅',quiz_result:'📝',practice_result:'💻',feedback:'💬'})[evt.event]||'📌'}</span>
                <div className="flex-1 min-w-0"><p className="text-xs text-surface-700 truncate">{evt.event==='task_complete'?`完成任务「${evt.metadata?.title||''}」`:evt.event==='resource_view'?`查看了资源「${evt.metadata?.title||''}」`:evt.event==='resource_complete'?`完成了资源「${evt.metadata?.title||''}」`:evt.event==='quiz_result'?`练习正确 ${evt.metadata?.correct}/${evt.metadata?.total}`:evt.event}</p></div>
                <span className="text-[10px] text-surface-400 flex-shrink-0">{(()=>{try{const d=new Date(evt.timestamp);const diff=Date.now()-d.getTime();const m=Math.floor(diff/60000);return m<1?'刚刚':m<60?`${m}分钟前`:`${Math.floor(m/1440)}天前`}catch{return''}})()}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {(analytics.weakTopics ?? []).length > 0 && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4">薄弱知识点</h3>
          <div className="space-y-3">
            {analytics.weakTopics.slice(0, 5).map((t, i) => (
              <div key={i} className="flex items-center justify-between p-3 rounded-xl bg-surface-50">
                <div className="flex items-center gap-3"><span className="text-sm font-medium text-surface-700">{t.topic}</span>{t.priority === 'high' && <span className="px-2 py-0.5 bg-error-100 text-error-600 text-[10px] font-bold rounded-full">高优</span>}</div>
                <div className="flex items-center gap-3"><span className="text-xs text-surface-500">{t.wrongCount}/{t.totalCount}</span><button onClick={() => nav(`/resources?knowledgePoint=${encodeURIComponent(t.topic)}`)} className="text-xs text-primary-600 hover:text-primary-700 font-medium">查看资源 →</button></div>
              </div>
            ))}
          </div>
        </div>
      )}

      {analytics.recommendations && analytics.recommendations.length > 0 && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4 flex items-center gap-2"><Zap size={18} className="text-warning-500" />学习建议</h3>
          <div className="space-y-3">
            {analytics.recommendations.slice(0, 5).map((rec: RecommendationItem, i: number) => (
              <div key={i} className="flex items-start gap-3 p-3 rounded-xl bg-warning-50/50 border border-warning-100/50">
                <span className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${rec.priority === 'high' ? 'bg-error-500' : rec.priority === 'medium' ? 'bg-warning-500' : 'bg-surface-400'}`} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-surface-700">{rec.title}</p>
                  <p className="text-xs text-surface-500 mt-0.5">{rec.reason}</p>
                </div>
                {rec.target_resource_id && (
                  <button onClick={() => nav(`/resources/${rec.target_resource_id}`)} className="text-xs text-primary-600 hover:text-primary-700 font-medium flex-shrink-0">查看 →</button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {analytics.topResources && analytics.topResources.length > 0 && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4 flex items-center gap-2"><Star size={18} className="text-accent-500" />常用资源</h3>
          <div className="space-y-2.5">
            {analytics.topResources.slice(0, 5).map((r, i) => (
              <div key={i} className="flex items-center justify-between py-2">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-bold text-surface-400 w-5">{i + 1}</span>
                  <span className="text-sm text-surface-700 truncate max-w-[320px]">{r.title || r.resourceId}</span>
                </div>
                <span className="text-xs text-surface-500">访问 {r.count} 次</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {analytics.resourceTypeBreakdown && Object.keys(analytics.resourceTypeBreakdown).length > 0 && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4 flex items-center gap-2"><BarChart3 size={18} className="text-primary-500" />资源类型分布</h3>
          <div className="space-y-3">
            {Object.entries(analytics.resourceTypeBreakdown).sort(([, a], [, b]) => (b as number) - (a as number)).slice(0, 6).map(([k, v]) => {
              const max = Math.max(...Object.values(analytics.resourceTypeBreakdown).map(Number));
              const typeLabels: Record<string, string> = { lecture: '文档', mindmap: '思维导图', quiz: '练习', reading: '阅读', case_study: '案例', video: '视频', ppt: 'PPT' };
              return (
                <div key={k} className="space-y-1.5">
                  <div className="flex items-center justify-between text-sm"><span className="text-surface-600">{typeLabels[k] || k}</span><span className="text-surface-500">{v as number}</span></div>
                  <div className="h-2 bg-surface-100 rounded-full overflow-hidden"><div className="h-full bg-accent-500 rounded-full transition-all duration-700" style={{ width: `${Math.max(((v as number) / max) * 100, 4)}%` }} /></div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* M6: 进步曲线 — 近30天正确率+做题量双轴图 */}
      {analytics.progressCurve && analytics.progressCurve.length > 0 && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <div className="flex items-center justify-between mb-5">
            <h3 className="font-display text-lg font-semibold text-surface-800 flex items-center gap-2">
              <TrendingUp size={18} className="text-primary-500" />进步曲线（近30天）
            </h3>
            <div className="flex items-center gap-4 text-xs">
              <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 rounded-full bg-primary-500 inline-block" style={{ borderTop: '2.5px solid #3b82f6' }} />正确率</span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-accent-200 inline-block" />做题量</span>
            </div>
          </div>
          <DualAxisChart data={analytics.progressCurve} />
          <div className="flex justify-between mt-3 text-xs text-surface-400">
            <span>{analytics.progressCurve[0]?.date}</span>
            <span>{analytics.progressCurve[analytics.progressCurve.length - 1]?.date}</span>
          </div>
        </div>
      )}

      {analytics.quizTrend && analytics.quizTrend.length > 0 && !analytics.progressCurve && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4">练习正确率趋势</h3>
          <div className="h-32 flex items-end gap-1">
            {analytics.quizTrend.slice(-15).map((p: any, i: number) => { const h = Math.max((p.accuracy/100)*100, 4); return <div key={i} className="flex-1 flex flex-col items-center gap-1"><div className="w-full rounded-t-sm bg-primary-500 transition-all hover:opacity-80" style={{ height: `${h}%`, minHeight: '4px' }} title={`${p.topic||''}: ${p.accuracy}%`} /></div>; })}
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════ M6: 仪表盘新增面板 ══════════════════════════════════════════════ */}

      {/* M6: 今日学习卡片 */}
      {analytics.todayCard && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: '今日答题', value: analytics.todayCard.questionsAnswered ?? 0, unit: '题', icon: BookOpen, color: 'text-primary-500', trend: undefined },
            { label: '平均得分', value: analytics.todayCard.averageScore ?? '--', unit: '分', icon: Target,
              color: (analytics.todayCard.averageScore ?? 0) >= 60 ? 'text-success-500' : 'text-warning-500',
              trend: analytics.todayCard.rankChange as number | undefined },
            { label: '薄弱点', value: analytics.todayCard.weakPointsCount ?? 0, unit: '个', icon: AlertCircle, color: 'text-error-500', trend: undefined },
            { label: '学习时长', value: analytics.todayCard.studyMinutes ?? 0, unit: '分钟', icon: Clock, color: 'text-accent-500', trend: undefined },
          ].map((card, i) => (
            <div key={i} className="bg-white rounded-xl p-4 shadow-soft relative">
              <div className="flex items-center justify-between mb-2">
                <card.icon className={`w-5 h-5 ${card.color}`} />
                {card.trend !== undefined && card.trend !== 0 && (
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full flex items-center gap-0.5 ${card.trend > 0 ? 'bg-success-50 text-success-600' : 'bg-error-50 text-error-600'}`}>
                    {card.trend > 0 ? '↑' : '↓'} 趋势
                  </span>
                )}
              </div>
              <p className="text-2xl font-bold text-surface-800">{card.value}<span className="text-sm text-surface-400 ml-0.5">{card.unit}</span></p>
              <p className="text-xs text-surface-500">{card.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* M6: 能力热力图（含置信度+趋势）*/}
      {analytics.heatmap && analytics.heatmap.length > 0 && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4 flex items-center gap-2"><Brain size={18} className="text-primary-500" />能力热力图</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {analytics.heatmap.map((item: any, i: number) => {
              const s = item.mastery || 50;
              const conf = item.confidence ?? 0.5;
              const trend = item.trend;
              const bg = s >= 80 ? 'bg-success-100 border-success-300' : s >= 50 ? 'bg-primary-50 border-primary-200' : 'bg-error-50 border-error-200';
              const text = s >= 80 ? 'text-success-700' : s >= 50 ? 'text-primary-700' : 'text-error-700';
              return (
                <div key={i} className={`rounded-xl p-3 border ${bg} relative`} style={{ opacity: 0.4 + conf * 0.6 }}>
                  <div className="flex items-center gap-1.5">
                    <p className={`text-xs font-semibold ${text} truncate`}>{item.knowledgePoint}</p>
                    {trend === 'improving' && <TrendingUp size={12} className="text-success-500 flex-shrink-0" />}
                    {trend === 'declining' && <TrendingDown size={12} className="text-error-500 flex-shrink-0" />}
                  </div>
                  <div className="flex items-center justify-between mt-1">
                    <div className="flex items-baseline gap-1">
                      <span className="text-lg font-bold text-surface-700">{s}</span>
                      {conf < 0.4 && <span className="text-[9px] text-surface-400" title="置信度低">低置信</span>}
                    </div>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${bg} ${text}`}>{item.level}</span>
                  </div>
                  {item.evidenceCount > 0 && (
                    <p className="text-[9px] text-surface-400 mt-1">基于 {item.evidenceCount} 次作答</p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* M6: 薄弱榜单 Top 5（含建议措施）*/}
      {analytics.weaknessRanking && analytics.weaknessRanking.length > 0 && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4 flex items-center gap-2"><AlertCircle size={18} className="text-error-500" />薄弱知识点 Top 5</h3>
          <div className="space-y-2">
            {analytics.weaknessRanking.map((item: any, i: number) => (
              <div key={i} className="p-3 bg-surface-50 rounded-xl">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-bold text-surface-400 w-5">{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-surface-700 truncate">{item.name}</p>
                    <p className="text-xs text-surface-400">{item.reason}</p>
                  </div>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${item.priority === 'high' ? 'bg-error-50 text-error-600' : 'bg-warning-50 text-warning-600'}`}>{item.priority === 'high' ? '高优' : '中'}</span>
                </div>
                <div className="flex items-center gap-2 mt-2 pl-8">
                  <Zap size={12} className="text-warning-500 flex-shrink-0" />
                  <p className="text-xs text-surface-500 flex-1">{item.suggested_action || '建议针对性练习'}</p>
                  {item.resourceIds?.length > 0 && (
                    <button onClick={() => nav(`/resources?knowledgePoint=${encodeURIComponent(item.name)}`)}
                      className="text-[10px] text-primary-600 hover:text-primary-700 font-medium flex-shrink-0">查看资源 →</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 综合评估摘要 ── */}
      {analytics.assessmentSummary && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <div className="flex items-center gap-2 mb-4"><Brain size={18} className="text-primary-500" /><h3 className="font-display text-lg font-semibold text-surface-800">综合评估</h3></div>
          <p className="text-sm text-surface-600 leading-relaxed">{analytics.assessmentSummary}</p>
        </div>
      )}

      {/* ── 学习规律评分 ── */}
      {analytics.regularityScore != null && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <div className="flex items-center gap-2 mb-4"><Activity size={18} className="text-accent-500" /><h3 className="font-display text-lg font-semibold text-surface-800">学习规律</h3></div>
          <div className="flex items-center gap-5">
            <Ring pct={analytics.regularityScore} />
            <div className="text-sm text-surface-500">
              {analytics.regularityScore >= 70 ? '学习规律性强，建议继续保持' :
               analytics.regularityScore >= 40 ? '学习有一定规律，可以尝试固定时间' :
               '学习间隔不规律，建议每天固定时间学习'}
              <p className="text-xs text-surface-400 mt-1">基于学习日期间隔的规律性计算</p>
            </div>
          </div>
        </div>
      )}

      {/* ── 知识点掌握趋势 ── */}
      {analytics.topicMasteryTrend && analytics.topicMasteryTrend.length > 0 && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4">知识点掌握趋势</h3>
          <div className="space-y-4">
            {analytics.topicMasteryTrend.slice(0, 5).map((item: any, i: number) => (
              <div key={i}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-surface-700">{item.topic}</span>
                  <span className="text-xs text-surface-400">{item.points.length} 次记录</span>
                </div>
                <div className="flex items-end gap-0.5 h-12">
                  {item.points.slice(-10).map((pt: any, pi: number) => {
                    const h = Math.max((pt.accuracy / 100) * 100, 4);
                    return <div key={pi} className="flex-1 rounded-t-sm bg-primary-500 transition-all" style={{ height: `${h}%` }} title={`${pt.date}: ${pt.accuracy}%`} />;
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* M6: 目标追踪 */}
      {analytics.goalTracking && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4 flex items-center gap-2"><Target size={18} className="text-accent-500" />学习目标追踪</h3>

          {/* 进度条 */}
          <div className="mb-5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-surface-600">总体进度</span>
              <span className="text-sm font-semibold text-surface-800">{analytics.goalTracking.progressPercent ?? analytics.goalTracking.masteryPercentage ?? 0}%</span>
            </div>
            <div className="h-3 bg-surface-100 rounded-full overflow-hidden">
              <div className="h-full rounded-full bg-gradient-to-r from-primary-500 to-accent-500 transition-all duration-1000 ease-out"
                style={{ width: `${Math.min(100, analytics.goalTracking.progressPercent ?? analytics.goalTracking.masteryPercentage ?? 0)}%` }} />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            {/* 距考试天数 */}
            <div className="text-center p-3 bg-surface-50 rounded-xl">
              <p className="text-2xl font-bold text-surface-800">
                {analytics.goalTracking.daysUntilExam != null
                  ? (analytics.goalTracking.daysUntilExam > 0 ? analytics.goalTracking.daysUntilExam : '今天')
                  : '--'}
              </p>
              <p className="text-xs text-surface-500">距考试天数</p>
              {analytics.goalTracking.examDate && (
                <p className="text-[10px] text-surface-400 mt-0.5">{analytics.goalTracking.examDate}</p>
              )}
            </div>
            {/* 预估达成分位 */}
            <div className="text-center p-3 bg-surface-50 rounded-xl">
              <p className="text-2xl font-bold text-accent-600">
                {analytics.goalTracking.estimatedPercentile != null
                  ? `前 ${analytics.goalTracking.estimatedPercentile}%`
                  : '--'}
              </p>
              <p className="text-xs text-surface-500">预估达成分位</p>
            </div>
            {/* 已完成题目 */}
            <div className="text-center p-3 bg-surface-50 rounded-xl">
              <p className="text-2xl font-bold text-surface-800">{analytics.goalTracking.questionsCompleted ?? 0}<span className="text-sm text-surface-400">题</span></p>
              <p className="text-xs text-surface-500">累计做题</p>
            </div>
            {/* 平均掌握度 */}
            <div className="text-center p-3 bg-surface-50 rounded-xl">
              <p className="text-2xl font-bold text-primary-600">{analytics.goalTracking.masteryPercentage ?? 0}%</p>
              <p className="text-xs text-surface-500">平均掌握度</p>
            </div>
            {/* 预估总天数 */}
            <div className="text-center p-3 bg-surface-50 rounded-xl">
              <p className="text-2xl font-bold text-surface-800">{analytics.goalTracking.estimatedDays ?? 14}<span className="text-sm text-surface-400">天</span></p>
              <p className="text-xs text-surface-500">预估学习周期</p>
            </div>
            {/* 阶段进度 */}
            <div className="text-center p-3 bg-surface-50 rounded-xl">
              <p className="text-2xl font-bold text-surface-800">{analytics.goalTracking.stagesCompleted ?? 0}/{analytics.goalTracking.stagesTotal ?? 0}</p>
              <p className="text-xs text-surface-500">阶段进度</p>
            </div>
          </div>
        </div>
      )}

      {/* M6: 学习日历（近30天，表现等级着色）*/}
      {analytics.studyCalendar && analytics.studyCalendar.length > 0 && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display text-lg font-semibold text-surface-800 flex items-center gap-2"><Activity size={18} className="text-primary-500" />学习日历（近30天）</h3>
            <div className="flex items-center gap-3 text-[10px] text-surface-400">
              <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-success-400" />优秀</span>
              <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-primary-300" />良好</span>
              <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-warning-300" />需加强</span>
              <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-surface-200" />浏览</span>
              <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-surface-100" />无</span>
            </div>
          </div>
          <div className="grid grid-cols-7 gap-1.5">
            {['一','二','三','四','五','六','日'].map(d => <div key={d} className="text-center text-[10px] text-surface-400 py-1 font-medium">{d}</div>)}
            {analytics.studyCalendar.map((day, i) => {
              const lv = (day as any).performanceLevel ?? (day.active ? 1 : 0);
              const bg = lv === 4 ? 'bg-success-400 text-white' :
                         lv === 3 ? 'bg-primary-300 text-white' :
                         lv === 2 ? 'bg-warning-300 text-white' :
                         lv === 1 ? 'bg-surface-200 text-surface-600' :
                         'bg-surface-50 text-surface-400';
              const d = new Date(day.date);
              return (
                <div key={i} title={`${day.date} · ${day.questionCount ?? 0}题 · ${['无','浏览','需加强','良好','优秀'][lv]}`}
                  className={`aspect-square rounded-lg flex items-center justify-center text-xs font-medium transition-all hover:scale-110 cursor-default ${bg}`}>
                  {d.getDate()}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── AI 多维度学习评估 ── */}
      <div className="bg-white rounded-2xl p-6 shadow-soft">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2"><Brain size={18} className="text-primary-500" /><h3 className="font-display text-lg font-semibold text-surface-800">AI 学习评估</h3></div>
          <button onClick={async () => {
            try {
              const { generateAssessment } = await import('../api/learningAssessment');
              const result = await generateAssessment(sessionId || '');
              if (result?.data) setAiAssessment(result.data);
            } catch (e: any) {
              setAiAssessment({ status: 'error', summary: e?.message || '评估生成失败，请稍后重试' });
            }
          }} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-brand-500 bg-brand-50 hover:bg-brand-100 transition-colors">
            <Zap size={14} />生成评估
          </button>
        </div>
        {(() => {
          if (!aiAssessment) return <p className="text-sm text-surface-400 text-center py-6">点击「生成评估」获取 AI 多维度分析报告</p>;
          if (aiAssessment.status === 'insufficient_data') return <p className="text-sm text-surface-400 text-center py-6">{aiAssessment.summary}</p>;
          const scores = aiAssessment.scores || {};
          const dimLabels: Record<string, string> = {
            knowledge_mastery: '知识掌握', learning_progress: '学习进度', learning_efficiency: '学习效率',
            learning_regularity: '学习规律', engagement_level: '投入度', weakness_awareness: '薄弱认知', improvement_trend: '进步趋势',
          };
          return (
            <div className="space-y-4">
              {/* 雷达/环形图：各维度评分 */}
              <div className="grid grid-cols-4 gap-3">
                {Object.entries(dimLabels).map(([key, label]) => (
                  <div key={key} className="text-center">
                    <Ring pct={scores[key] ?? 50} />
                    <p className="text-[10px] text-surface-500 mt-1">{label}</p>
                  </div>
                ))}
              </div>
              {/* 综合分析 */}
              {aiAssessment.summary && (
                <div className="p-3 bg-surface-50 rounded-xl">
                  <p className="text-sm text-surface-600 leading-relaxed">{aiAssessment.summary}</p>
                </div>
              )}
              {/* 推荐行动 */}
              {aiAssessment.recommended_actions && (
                <div className="p-3 bg-primary-50/50 rounded-xl">
                  <p className="text-xs font-semibold text-primary-700 mb-1">💡 推荐行动</p>
                  <p className="text-sm text-surface-600 whitespace-pre-line">{aiAssessment.recommended_actions}</p>
                </div>
              )}
            </div>
          );
        })()}
      </div>

      <div className="text-center text-xs text-surface-400 pt-4 border-t border-surface-200">累计追踪 {analytics.eventCount} 条学习事件 · 数据驱动个性化学习</div>
    </div>
  );
}

/** M6: 双轴折线+柱状混合图 — 正确率折线（左轴）+ 做题量柱（右轴） */
function DualAxisChart({ data }: { data: { date: string; accuracy: number | null; questionCount: number }[] }) {
  const W = 720; const H = 220; const PAD_L = 42; const PAD_R = 48; const PAD_T = 16; const PAD_B = 20;
  const plotW = W - PAD_L - PAD_R;
  const plotH = H - PAD_T - PAD_B;

  const maxQ = Math.max(...data.map(d => d.questionCount), 5);
  const accPoints = data.filter(d => d.accuracy != null);
  const hasAcc = accPoints.length >= 2;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" preserveAspectRatio="xMidYMid meet">
      {/* 网格线 */}
      {[0, 0.25, 0.5, 0.75, 1].map(r => {
        const y = PAD_T + plotH * (1 - r);
        return <line key={r} x1={PAD_L} y1={y} x2={W - PAD_R} y2={y} stroke="#f1f5f9" strokeWidth="1" />;
      })}
      {/* 左轴标签 */}
      {[0, 25, 50, 75, 100].map(v => (
        <text key={`la${v}`} x={PAD_L - 6} y={PAD_T + plotH * (1 - v / 100) + 4} textAnchor="end" fill="#94a3b8" fontSize="10">{v}%</text>
      ))}
      <text x={12} y={PAD_T + plotH / 2} textAnchor="middle" fill="#94a3b8" fontSize="9" transform={`rotate(-90 12 ${PAD_T + plotH / 2})`}>正确率</text>

      {/* 右轴标签 */}
      {[0, Math.round(maxQ / 2), maxQ].map((v, i) => (
        <text key={`ra${v}`} x={W - PAD_R + 6} y={PAD_T + plotH * (1 - i / 2) + 4} textAnchor="start" fill="#94a3b8" fontSize="10">{v}</text>
      ))}
      <text x={W - 8} y={PAD_T + plotH / 2} textAnchor="middle" fill="#94a3b8" fontSize="9" transform={`rotate(90 ${W - 8} ${PAD_T + plotH / 2})`}>题数</text>

      {/* 柱状图 — 做题量 */}
      {data.map((d, i) => {
        const x = PAD_L + (i / Math.max(data.length - 1, 1)) * plotW;
        const barW = Math.max(3, plotW / data.length * 0.55);
        const barH = (d.questionCount / maxQ) * plotH;
        return <rect key={`bar${i}`} x={x - barW / 2} y={PAD_T + plotH - barH} width={barW} height={barH} rx="2" fill="#c7d2fe" opacity="0.7" />;
      })}

      {/* 折线 — 正确率 */}
      {hasAcc && (() => {
        const linePath = accPoints.map((d, i) => {
          const dataIdx = data.indexOf(d);
          const x = PAD_L + (dataIdx / Math.max(data.length - 1, 1)) * plotW;
          const y = PAD_T + plotH * (1 - (d.accuracy ?? 0) / 100);
          return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
        }).join(' ');
        const areaPath = linePath + ` L${PAD_L + plotW},${PAD_T + plotH} L${PAD_L},${PAD_T + plotH} Z`;
        return (
          <>
            <defs><linearGradient id="accGrad" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stopColor="#3b82f6" stopOpacity="0.25" /><stop offset="100%" stopColor="#3b82f6" stopOpacity="0.02" /></linearGradient></defs>
            <path d={areaPath} fill="url(#accGrad)" />
            <path d={linePath} fill="none" stroke="#3b82f6" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            {accPoints.map((d) => {
              const dataIdx = data.indexOf(d);
              const x = PAD_L + (dataIdx / Math.max(data.length - 1, 1)) * plotW;
              const y = PAD_T + plotH * (1 - (d.accuracy ?? 0) / 100);
              return <circle key={`dot${dataIdx}`} cx={x} cy={y} r="3.5" fill="#fff" stroke="#3b82f6" strokeWidth="2" />;
            })}
          </>
        );
      })()}
    </svg>
  );
}
