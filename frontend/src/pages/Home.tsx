import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSubjectStore } from '../store/subjectStore';
import { useLearningAnalytics } from '../hooks/useLearningAnalytics';
import { useProfile } from '../hooks/useProfile';
import { getCurrentLearner } from './LoginPage';
import { PlayCircle, FileText, BrainCircuit, Code2, Trophy, Flame, Clock, ChevronRight, Sparkles, Plus, Trash2 } from 'lucide-react';

export default function Home() {
  const nav = useNavigate();
  const { subjects, activeSubject, create, setActive, remove } = useSubjectStore();
  const { analytics } = useLearningAnalytics();
  const { profile } = useProfile();
  const user = getCurrentLearner();

  const streak = profile?.history?.streak || 0;
  const totalHours = profile?.history?.totalStudyMinutes ? Math.round(profile.history.totalStudyMinutes / 60) : 0;
  const completedResources = analytics?.completedResources || 0;
  const viewedResources = analytics?.viewedResources || 0;
  const quizAccuracy = analytics?.quizAccuracy != null ? Math.round(analytics.quizAccuracy) : null;

  // 折线图数据：从 completionTrend 取最近7天
  const chartData = useMemo(() => {
    if (analytics?.completionTrend?.length) {
      return analytics.completionTrend.slice(-7).map(p => p.count);
    }
    return [0, 0, 0, 0, 0, 0, 0];
  }, [analytics]);
  const chartMax = Math.max(...chartData, 4);
  const totalCompleted = chartData.reduce((a, b) => a + b, 0);

  // 计算今天在趋势数据中的位置
  const todayIdx = useMemo(() => {
    const trend = analytics?.completionTrend?.slice(-7) || [];
    if (!trend.length) return -1;
    const today = new Date();
    const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    const idx = trend.findIndex(p => p.date === todayStr);
    return idx >= 0 ? idx : trend.length - 1;
  }, [analytics]);

  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const submitCreate = () => { const n = newName.trim(); if (!n) return; const s = create(n); setNewName(''); setShowCreate(false); setActive(s); nav('/chat'); };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Welcome Banner */}
      <div className="relative overflow-hidden bg-gradient-to-r from-primary-600 via-primary-500 to-accent-500 rounded-2xl p-6 text-white gradient-animate">
        <div className="relative z-10">
          <div className="flex items-center gap-2 mb-2">
            <Flame className="w-5 h-5 text-warning-300" />
            <span className="text-sm font-medium text-white/80">连续学习 {streak} 天</span>
          </div>
          <h2 className="font-display text-2xl font-bold mb-2">欢迎回来，{user?.name || '学习者'}！</h2>
          <p className="text-white/80 mb-4">继续你的学习之旅，今天继续探索新知识</p>
          <button onClick={() => nav('/chat')} className="flex items-center gap-2 px-5 py-2.5 bg-white rounded-xl text-primary-600 font-semibold hover:bg-primary-50 transition-colors shadow-lg">
            <PlayCircle size={18} /> 开始学习 <ChevronRight size={18} />
          </button>
        </div>
        <div className="absolute right-8 top-1/2 -translate-y-1/2 opacity-10"><BrainCircuit size={180} /></div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-4 gap-5">
        <StatCard icon={<Clock className="w-5 h-5 text-primary-600" />} label="我的科目" value={`${subjects.length}个`} color="primary" />
        <StatCard icon={<FileText className="w-5 h-5 text-accent-600" />} label="浏览资源" value={`${viewedResources}次`} color="accent" />
        <StatCard icon={<Trophy className="w-5 h-5 text-warning-600" />} label="累计学习" value={`${totalHours}h`} color="warning" />
        <StatCard icon={<Code2 className="w-5 h-5 text-success-600" />} label="测验正确率" value={quizAccuracy != null ? `${quizAccuracy}%` : '--'} color="success" />
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-3 gap-6">
        {/* 左侧 - 占2列 */}
        <div className="col-span-2 flex flex-col space-y-6">
          {/* Subject List */}
          <div className="bg-white rounded-2xl p-6 shadow-soft">
            <div className="flex items-center justify-between mb-5">
              <h3 className="font-display text-lg font-semibold text-surface-800">我的科目</h3>
              <button onClick={() => setShowCreate(!showCreate)} className="text-sm text-primary-600 hover:text-primary-700 font-medium">+ 新建科目</button>
            </div>
            {showCreate && (
              <div className="flex items-center gap-2 mb-4 animate-fade-in">
                <input value={newName} onChange={e => setNewName(e.target.value)} onKeyDown={e => e.key==='Enter'&&submitCreate()} placeholder="科目名称" autoFocus maxLength={30} className="flex-1 px-4 py-2.5 bg-surface-50 border border-surface-200 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary-200 focus:border-primary-400 transition-all" />
                <button onClick={submitCreate} disabled={!newName.trim()} className="px-4 py-2.5 bg-primary-600 text-white rounded-xl text-sm font-medium hover:bg-primary-700 disabled:opacity-50 transition-colors whitespace-nowrap">创建</button>
                <button onClick={() => setShowCreate(false)} className="px-3 py-2.5 text-sm text-surface-400 hover:text-surface-600 whitespace-nowrap">取消</button>
              </div>
            )}
            <div className="space-y-3 max-h-[220px] overflow-y-auto pr-1">
              {subjects.length === 0 ? (
                <p className="text-surface-400 text-sm py-4 text-center">还没有科目，点击"新建科目"创建第一个</p>
              ) : subjects.map((s, idx) => (
                <div key={s.id} className="space-y-2 cursor-pointer group relative" onClick={() => { setActive(s); nav('/chat'); }}>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-surface-700 font-medium">{s.name}{activeSubject?.id===s.id&&<span className="ml-2 px-2 py-0.5 bg-primary-100 text-primary-700 rounded-full text-[10px] font-semibold">当前</span>}</span>
                    <button onClick={e => { e.stopPropagation(); if(confirm(`删除「${s.name}」？`)) remove(s.id); }} className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-md text-surface-300 hover:text-error-500 hover:bg-error-50"><Trash2 size={14} /></button>
                  </div>
                  <div className="h-2 bg-surface-100 rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-1000 ease-out" style={{ width: `${totalCompleted > 0 ? Math.min(100, Math.round((totalCompleted / Math.max(viewedResources || 1, 1)) * 100)) : 0}%`, background: `linear-gradient(90deg, ${idx===0?'#14b8a6, #3b82f6':idx===1?'#3b82f6, #8b5cf6':'#f59e0b, #ec4899'})` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 本周学习时长 - 折线图 */}
          <div className="bg-white rounded-2xl p-6 shadow-soft flex-1 flex flex-col">
            <div className="flex items-center justify-between mb-5">
              <h3 className="font-display text-lg font-semibold text-surface-800">本周学习时长</h3>
              <div className="flex items-center gap-2 text-sm"><span className="text-surface-500">总时长</span><span className="font-semibold text-surface-800">{totalHours}h</span></div>
            </div>
            <div className="flex-1 relative min-h-[160px]">
              <svg className="w-full h-full" viewBox="0 0 400 160" preserveAspectRatio="xMidYMid meet">
                {/* 网格线 */}
                {[0, 1, 2, 3, 4].map(i => (
                  <line key={`grid-${i}`} x1="30" y1={20 + i * 30} x2="390" y2={20 + i * 30} stroke="#f1f5f9" strokeWidth="1" />
                ))}
                {/* Y轴标签 */}
                <text x="28" y="24" textAnchor="end" fill="#94a3b8" fontSize="10">{chartMax}h</text>
                <text x="28" y="54" textAnchor="end" fill="#94a3b8" fontSize="10">{Math.round(chartMax * 0.75)}h</text>
                <text x="28" y="84" textAnchor="end" fill="#94a3b8" fontSize="10">{Math.round(chartMax * 0.5)}h</text>
                <text x="28" y="114" textAnchor="end" fill="#94a3b8" fontSize="10">{Math.round(chartMax * 0.25)}h</text>
                <text x="28" y="144" textAnchor="end" fill="#94a3b8" fontSize="10">0h</text>

                {/* 折线图 */}
                {(() => {
                  const data = chartData;
                  const maxH = chartMax || 1;
                  const trend = analytics?.completionTrend?.slice(-7) || [];
                  const points = data.map((h, i) => {
                    const x = 50 + (i / Math.max(data.length - 1, 1)) * 330;
                    const y = 140 - (h / maxH) * 120;
                    return `${x},${y}`;
                  }).join(' ');
                  const area = `${points} ${50 + 330},140 50,140`;
                  return (
                    <>
                      <defs>
                        <linearGradient id="lineGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                          <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.3" />
                          <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.02" />
                        </linearGradient>
                      </defs>
                      <polygon points={area} fill="url(#lineGrad)" />
                      <polyline points={points} fill="none" stroke="#3b82f6" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                      {data.map((h, i) => {
                        const x = 50 + (i / Math.max(data.length - 1, 1)) * 330;
                        const y = 140 - (h / maxH) * 120;
                        const isToday = i === todayIdx;
                        const isFuture = todayIdx >= 0 && i > todayIdx;
                        if (isFuture) return null;
                        return (
                          <g key={`dot-${i}`}>
                            {isToday && <circle cx={x} cy={y} r="10" fill="none" stroke="#3b82f6" strokeWidth="1.5" opacity="0.2" />}
                            <circle cx={x} cy={y} r={isToday ? 5 : 3.5} fill={isToday ? '#3b82f6' : '#fff'} stroke="#3b82f6" strokeWidth={isToday ? 2.5 : 2} />
                            {isToday && h > 0 && (
                              <text x={x} y={y - 12} textAnchor="middle" fill="#3b82f6" fontSize="11" fontWeight={700}>{h}h</text>
                            )}
                          </g>
                        );
                      })}
                    </>
                  );
                })()}

                {/* X轴标签 */}
                {(analytics?.completionTrend?.slice(-7) || []).map((p, i) => {
                  const date = p.date ? new Date(p.date) : null;
                  const label = date ? `${date.getMonth() + 1}/${date.getDate()}` : `${i + 1}`;
                  const isToday = i === todayIdx;
                  return (
                    <text key={`day-${i}`} x={50 + (i / Math.max(chartData.length - 1, 1)) * 330} y="158" textAnchor="middle" fill={isToday ? '#3b82f6' : '#94a3b8'} fontSize="10" fontWeight={isToday ? 600 : 400}>
                      {label}
                    </text>
                  );
                })}
              </svg>
            </div>
          </div>
        </div>

        {/* 右侧 - 占1列 */}
        <div className="flex flex-col space-y-6">
          {/* 快速操作 */}
          <div className="bg-white rounded-2xl p-6 shadow-soft">
            <h3 className="font-display text-lg font-semibold text-surface-800 mb-4">快速操作</h3>
            <div className="space-y-3">
              <QA icon={<Sparkles className="w-5 h-5" />} label="生成学习资源" desc="AI智能体协同生成" onClick={() => nav('/chat')} color="bg-gradient-to-r from-primary-500 to-accent-500" />
              <QA icon={<BrainCircuit className="w-5 h-5" />} label="更新学习画像" desc="对话式画像构建" onClick={() => nav('/profile')} color="bg-gradient-to-r from-warning-500 to-error-500" />
              <QA icon={<FileText className="w-5 h-5" />} label="浏览资源库" desc="查看个性化资源" onClick={() => nav('/resources')} color="bg-gradient-to-r from-accent-500 to-primary-500" />
            </div>
          </div>

          {/* 最近活动 */}
          <div className="bg-white rounded-2xl p-6 shadow-soft flex-1 flex flex-col min-h-0">
            <div className="flex items-center justify-between mb-4"><h3 className="font-display text-lg font-semibold text-surface-800">最近活动</h3></div>
            <div className="space-y-3 flex-1 overflow-y-auto pr-1">
              {analytics?.recentEvents && analytics.recentEvents.length > 0 ? (
                analytics.recentEvents.slice(0, 6).map((evt, i) => {
                  const isComplete = evt.event?.includes('complete');
                  const isQuiz = evt.event?.includes('quiz');
                  const isPractice = evt.event?.includes('practice');
                  const label = evt.event === 'resource_complete' ? '完成了资源' : evt.event === 'resource_view' ? '浏览了资源' : evt.event === 'quiz_result' ? '完成测验' : evt.event === 'practice_result' ? '完成练习' : evt.event === 'feedback' ? '提交反馈' : '学习活动';
                  const metaTitle = evt.metadata && typeof evt.metadata === 'object' && 'resourceTitle' in evt.metadata ? String(evt.metadata.resourceTitle) : '';
                  return (
                    <div key={i} className="flex items-center gap-3 p-3 rounded-xl bg-surface-50 hover:bg-surface-100 transition-colors cursor-pointer">
                      <div className="w-8 h-8 rounded-lg bg-primary-100 flex items-center justify-center flex-shrink-0">
                        {isComplete ? <Trophy size={16} className="text-success-600" /> : isQuiz ? <FileText size={16} className="text-accent-600" /> : isPractice ? <Code2 size={16} className="text-warning-600" /> : <PlayCircle size={16} className="text-primary-600" />}
                      </div>
                      <div className="flex-1 min-w-0"><p className="text-sm font-medium text-surface-700 truncate">{metaTitle || label}</p><p className="text-[10px] text-surface-400">{label}</p></div>
                    </div>
                  );
                })
              ) : (
                <p className="text-surface-400 text-sm py-4 text-center">暂无活动记录<br /><span className="text-xs">开始学习后这里会显示近期动态</span></p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, color }: { icon: any; label: string; value: string; color: string }) {
  const cls: Record<string, string> = { primary: 'bg-primary-50 ring-1 ring-primary-100', accent: 'bg-accent-50 ring-1 ring-accent-100', warning: 'bg-warning-50 ring-1 ring-warning-100', success: 'bg-success-50 ring-1 ring-success-100' };
  return (
    <div className="bg-white rounded-2xl p-5 shadow-soft hover:shadow-elevated transition-shadow">
      <div className={`w-10 h-10 rounded-xl ${cls[color]} flex items-center justify-center mb-3`}>{icon}</div>
      <p className="text-sm text-surface-500 mb-1">{label}</p><p className="text-2xl font-bold text-surface-800">{value}</p>
    </div>
  );
}

function QA({ icon, label, desc, onClick, color }: any) {
  return (
    <button onClick={onClick} className="w-full flex items-center gap-4 p-4 rounded-xl bg-surface-50 hover:bg-surface-100 transition-all group">
      <div className={`w-10 h-10 rounded-xl ${color} flex items-center justify-center text-white`}>{icon}</div>
      <div className="flex-1 text-left"><p className="text-sm font-semibold text-surface-800">{label}</p><p className="text-xs text-surface-500">{desc}</p></div>
      <ChevronRight size={18} className="text-surface-400 group-hover:text-surface-600 group-hover:translate-x-1 transition-all" />
    </button>
  );
}