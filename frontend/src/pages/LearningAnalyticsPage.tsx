// @ts-nocheck
import { useNavigate } from 'react-router-dom';
import { TrendingUp, Zap, Target, BookOpen, Clock, Brain, AlertCircle, Star, RefreshCw, BarChart3, Activity, CheckCircle2 } from 'lucide-react';
import { PageLoading, PageEmpty, PageError, RefreshOverlay } from '../components/common/PageState';
import { formatDuration } from '../utils/format';
import { useLearningAnalytics } from '../hooks/useLearningAnalytics';
import type { RecommendationItem } from '../types/analytics';
import { useSubjectStore } from '../store/subjectStore';

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
  const subjectId = useSubjectStore(s => s.activeSubject?.id);
  const { analytics, loading, error, refetch } = useLearningAnalytics();
  if (!subjectId) return <PageEmpty icon={<TrendingUp className="w-8 h-8" />} title="请先选择科目" description="在左侧边栏选择一个科目后查看学习分析" />;
  if (loading && !analytics) return <PageLoading text="正在分析学习数据…" />;
  if (error && !analytics) return <PageError title="加载分析数据失败" description={error} onRetry={refetch} />;
  if (!analytics) return null;

  const rv = analytics.resourceViewCount ?? analytics.eventBreakdown['resource_view'] ?? 0;
  const rc = analytics.resourceCompleteCount ?? analytics.eventBreakdown['resource_complete'] ?? 0;

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

      <div className="grid grid-cols-2 gap-6">
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <div className="flex items-center justify-between mb-5"><h3 className="font-display text-lg font-semibold text-surface-800">练习正确率</h3></div>
          <div className="flex items-center gap-5"><Ring pct={analytics.quizAccuracy ?? 0} /><div className="text-sm text-surface-500">{analytics.quizAccuracy == null ? '完成练习后统计' : analytics.quizAccuracy >= 80 ? '优秀，继续保持' : analytics.quizAccuracy >= 60 ? '不错，有进步空间' : '需要更多练习'}<p className="text-surface-400 mt-1 text-xs">基于 {analytics.eventBreakdown['quiz_result'] || 0} 次练习</p></div></div>
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
                <span className="text-xs flex-shrink-0">{({resource_view:'👁',resource_complete:'✅',quiz_result:'📝',practice_result:'💻',feedback:'💬'})[evt.event]||'📌'}</span>
                <div className="flex-1 min-w-0"><p className="text-xs text-surface-700 truncate">{evt.event==='resource_view'?`查看了资源「${evt.metadata?.title||''}」`:evt.event==='resource_complete'?`完成了资源「${evt.metadata?.title||''}」`:evt.event==='quiz_result'?`练习正确 ${evt.metadata?.correct}/${evt.metadata?.total}`:evt.event}</p></div>
                <span className="text-[10px] text-surface-400 flex-shrink-0">{(()=>{try{const d=new Date(evt.timestamp);const diff=Date.now()-d.getTime();const m=Math.floor(diff/60000);return m<1?'刚刚':m<60?`${m}分钟前`:`${Math.floor(m/1440)}天前`}catch{return''}})()}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {analytics.weakTopics.length > 0 && (
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
              const typeLabels: Record<string, string> = { lecture: '讲义', mindmap: '思维导图', quiz: '练习', reading: '阅读', case_study: '案例', video: '视频', ppt: 'PPT' };
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

      {analytics.quizTrend && analytics.quizTrend.length > 0 && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4">练习正确率趋势</h3>
          <div className="h-32 flex items-end gap-1">
            {analytics.quizTrend.slice(-15).map((p: any, i: number) => { const h = Math.max((p.accuracy/100)*100, 4); return <div key={i} className="flex-1 flex flex-col items-center gap-1"><div className="w-full rounded-t-sm bg-primary-500 transition-all hover:opacity-80" style={{ height: `${h}%`, minHeight: '4px' }} title={`${p.topic||''}: ${p.accuracy}%`} /></div>; })}
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════ M6: 仪表盘新增面板 ══════════════════════════════════════════════ */}

      {/* 今日学习卡片 */}
      {analytics.todayCard && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: '今日答题', value: analytics.todayCard.questionsAnswered ?? '-', unit: '题', icon: BookOpen, color: 'text-primary-500' },
            { label: '平均得分', value: analytics.todayCard.averageScore ?? '-', unit: '分', icon: Target, color: analytics.todayCard.averageScore >= 60 ? 'text-success-500' : 'text-warning-500' },
            { label: '薄弱点', value: analytics.todayCard.weakPointsCount ?? 0, unit: '个', icon: AlertCircle, color: 'text-error-500' },
            { label: '学习时长', value: analytics.todayCard.studyMinutes ?? 0, unit: '分钟', icon: Clock, color: 'text-accent-500' },
          ].map((card, i) => (
            <div key={i} className="bg-white rounded-xl p-4 shadow-soft">
              <card.icon className={`w-5 h-5 ${card.color} mb-2`} />
              <p className="text-2xl font-bold text-surface-800">{card.value}<span className="text-sm text-surface-400 ml-0.5">{card.unit}</span></p>
              <p className="text-xs text-surface-500">{card.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* 能力热力图 */}
      {analytics.heatmap && analytics.heatmap.length > 0 && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4 flex items-center gap-2"><Brain size={18} className="text-primary-500" />能力热力图</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {analytics.heatmap.map((item: any, i: number) => {
              const s = item.mastery || 50;
              const bg = s >= 80 ? 'bg-success-100 border-success-300' : s >= 50 ? 'bg-primary-50 border-primary-200' : 'bg-error-50 border-error-200';
              const text = s >= 80 ? 'text-success-700' : s >= 50 ? 'text-primary-700' : 'text-error-700';
              return (
                <div key={i} className={`rounded-xl p-3 border ${bg}`}>
                  <p className={`text-xs font-semibold ${text} truncate`}>{item.knowledgePoint}</p>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-lg font-bold text-surface-700">{s}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${bg} ${text}`}>{item.level}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 薄弱榜单 Top 5 */}
      {analytics.weaknessRanking && analytics.weaknessRanking.length > 0 && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4 flex items-center gap-2"><AlertCircle size={18} className="text-error-500" />薄弱知识点 Top 5</h3>
          <div className="space-y-2">
            {analytics.weaknessRanking.map((item: any, i: number) => (
              <div key={i} className="flex items-center gap-3 p-3 bg-surface-50 rounded-xl">
                <span className="text-sm font-bold text-surface-400 w-5">{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-surface-700 truncate">{item.name}</p>
                  <p className="text-xs text-surface-400">{item.reason}</p>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${item.priority === 'high' ? 'bg-error-50 text-error-600' : 'bg-warning-50 text-warning-600'}`}>{item.priority === 'high' ? '高优' : '中'}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 目标追踪 */}
      {analytics.goalTracking && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4 flex items-center gap-2"><Target size={18} className="text-accent-500" />学习目标追踪</h3>
          <div className="grid grid-cols-2 gap-4">
            {[
              { label: '预估总天数', value: `${analytics.goalTracking.estimatedDays ?? 14} 天` },
              { label: '已完成题目', value: `${analytics.goalTracking.questionsCompleted ?? 0} 题` },
              { label: '平均掌握度', value: `${analytics.goalTracking.masteryPercentage ?? 0}%` },
              { label: '阶段进度', value: `${analytics.goalTracking.stagesCompleted ?? 0}/${analytics.goalTracking.stagesTotal ?? 0}` },
            ].map((item, i) => (
              <div key={i} className="text-center p-3 bg-surface-50 rounded-xl">
                <p className="text-2xl font-bold text-surface-800">{item.value}</p>
                <p className="text-xs text-surface-500">{item.label}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 学习日历 */}
      {analytics.studyCalendar && analytics.studyCalendar.length > 0 && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4 flex items-center gap-2"><Activity size={18} className="text-primary-500" />学习日历（近30天）</h3>
          <div className="grid grid-cols-7 gap-1">
            {['一','二','三','四','五','六','日'].map(d => <div key={d} className="text-center text-[10px] text-surface-400 py-1">{d}</div>)}
            {analytics.studyCalendar.map((day: any, i: number) => (
              <div key={i} className={`aspect-square rounded-lg flex items-center justify-center text-xs ${day.active ? 'bg-primary-500 text-white font-semibold' : 'bg-surface-50 text-surface-400'}`}>
                {new Date(day.date).getDate()}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="text-center text-xs text-surface-400 pt-4 border-t border-surface-200">累计追踪 {analytics.eventCount} 条学习事件 · 数据驱动个性化学习</div>
    </div>
  );
}
