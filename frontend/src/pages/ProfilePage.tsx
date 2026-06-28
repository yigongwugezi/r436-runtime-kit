// @ts-nocheck
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useChatPanel } from '../components/layout/AppLayout';
import { useProfile } from '../hooks/useProfile';
import { useChatStore } from '../store/chatStore';
import { Brain, BookOpen, Clock, AlertCircle, Heart, Code, Edit3, TrendingUp, RefreshCw, Sparkles, ChevronRight } from 'lucide-react';
import { PageLoading, PageError } from '../components/common/PageState';
import { DIMENSION_LABELS } from '../types/profile';
import type { DimensionKey } from '../types/profile';

const dimIcons: Record<string, React.ComponentType<{ size?: number | string; className?: string }>> = {
  major_background: BookOpen, knowledge_base: Brain, learning_goal: Heart,
  cognitive_style: Brain, error_patterns: AlertCircle, coding_ability: Code,
  learning_progress: Clock, interest_direction: Heart, learning_rhythm: TrendingUp,
};
const colorGradientMap: Record<number, string> = {
  0: 'from-blue-500 to-cyan-400', 1: 'from-violet-500 to-purple-400', 2: 'from-amber-500 to-orange-400',
  3: 'from-rose-500 to-pink-400', 4: 'from-emerald-500 to-teal-400', 5: 'from-orange-500 to-amber-400',
  6: 'from-blue-500 to-cyan-400', 7: 'from-violet-500 to-purple-400', 8: 'from-amber-500 to-orange-400',
};

export default function ProfilePage() {
  const nav = useNavigate();
  const chat = useChatPanel();
  const { profile, loading, error, fetchProfile, buildProfile } = useProfile();
  const sessionId = useChatStore(s => s.currentSessionId);

  const [isUpdating, setIsUpdating] = useState(false);
  const [selectedDimension, setSelectedDimension] = useState<string | null>(null);

  useEffect(() => { fetchProfile(); }, []);

  const handleRefresh = async () => {
    if (!sessionId) { chat.setOpen(true); return; }
    setIsUpdating(true);
    try {
      await buildProfile('请重新构建我的学习画像');
      await fetchProfile();
    } catch { /* ignore */ }
    finally { setIsUpdating(false); }
  };

  if (loading && !profile) return <PageLoading text="加载学习画像…" />;
  if (error && !profile) return <PageError title="画像加载失败" description={error} onRetry={fetchProfile} />;
  if (!profile || !profile.dimensions?.length) return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div><h2 className="font-display text-2xl font-bold text-surface-800">学习画像</h2><p className="text-surface-500 mt-1">基于AI对话构建的个性化学习特征分析</p></div>
        <button onClick={handleRefresh} disabled={isUpdating} className="flex items-center gap-2 px-5 py-2.5 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 transition-colors disabled:opacity-50"><RefreshCw size={18} className={isUpdating ? 'animate-spin' : ''} />{isUpdating ? '更新中...' : '构建画像'}</button>
      </div>
      <div className="bg-white rounded-2xl p-12 shadow-soft text-center">
        <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-primary-100 to-accent-100 flex items-center justify-center mx-auto mb-6"><Brain size={36} className="text-primary-400" /></div>
        <h3 className="text-lg font-semibold text-surface-700 mb-2">尚未构建学习画像</h3>
        <p className="text-surface-500 text-sm max-w-md mx-auto mb-6">在对话中告诉 AI 你的专业背景、学习目标和时间安排，系统将自动分析并生成你的个性化学习画像</p>
        <button onClick={() => chat.setOpen(true)} className="inline-flex items-center gap-2 px-6 py-3 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 transition-colors"><Sparkles size={18} />开始对话</button>
      </div>
    </div>
  );

  const dims = profile.dimensions || [];
  const n = dims.length || 1;
  const avgScore = n > 0 ? Math.round(dims.reduce((a, b) => a + (b.score || 0), 0) / n) : 0;
  const totalHours = Math.round((profile.history?.totalStudyMinutes || 0) / 60);
  const completedTopics = profile.history?.completedTopics?.length || 0;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div><h2 className="font-display text-2xl font-bold text-surface-800">学习画像</h2><p className="text-surface-500 mt-1">基于AI对话构建的个性化学习特征分析</p></div>
        <button onClick={handleRefresh} disabled={isUpdating} className="flex items-center gap-2 px-5 py-2.5 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 transition-colors disabled:opacity-50"><RefreshCw size={18} className={isUpdating ? 'animate-spin' : ''} />{isUpdating ? '更新中...' : '更新画像'}</button>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* 基本信息卡片 */}
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <div className="flex flex-col items-center text-center mb-6">
            <div className="w-24 h-24 rounded-2xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center text-white text-4xl font-bold mb-4 shadow-lg">{(profile.nickname || '学')[0]}</div>
            <h3 className="text-xl font-bold text-surface-800">{profile.nickname || '学习者'}</h3>
            <p className="text-surface-500">{dims.find(d => d.key === 'major_background')?.value || '未知专业'}</p>
            <div className="flex items-center gap-1 mt-2 text-sm text-surface-400"><span>更新于 {profile.updatedAt ? new Date(profile.updatedAt).toLocaleDateString('zh-CN') : '未知'}</span></div>
          </div>
          <div className="space-y-4 pt-4 border-t border-surface-100">
            <div className="flex items-center justify-between"><span className="text-sm text-surface-500">累计学习时长</span><span className="font-semibold text-surface-800">{totalHours} 小时</span></div>
            <div className="flex items-center justify-between"><span className="text-sm text-surface-500">完成专题</span><span className="font-semibold text-surface-800">{completedTopics} 个</span></div>
            <div className="flex items-center justify-between"><span className="text-sm text-surface-500">测验准确率</span><span className="font-semibold text-surface-800">{profile.history?.quizAccuracy != null ? `${Math.round(profile.history.quizAccuracy)}%` : '暂无'}</span></div>
          </div>
          <button onClick={() => chat.setOpen(true)} className="w-full mt-6 flex items-center justify-center gap-2 px-4 py-3 bg-surface-50 rounded-xl text-surface-600 hover:bg-surface-100 transition-colors"><Edit3 size={16} /><span className="text-sm font-medium">对话更新画像</span></button>
        </div>

        {/* 雷达图 */}
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <div className="flex items-center justify-between mb-5"><h3 className="font-display text-lg font-semibold text-surface-800">{n}维能力画像</h3><span className="text-xs text-surface-400">综合 {avgScore} 分</span></div>
          <div className="relative flex items-center justify-center h-64">
            {n > 0 && (
              <svg viewBox="0 0 220 220" className="w-full h-full">
                {[100, 80, 60, 40, 20].map((r, idx) => {
                  const pts = dims.map((_, i) => { const a = (i * 360 / n - 90) * (Math.PI / 180); const rr = r * 0.85; return `${110 + rr * Math.cos(a)},${110 + rr * Math.sin(a)}`; }).join(' ');
                  return <polygon key={idx} points={pts} fill="none" stroke="#e2e8f0" strokeWidth="1" />;
                })}
                <polygon points={dims.map((d, i) => { const a = (i * 360 / n - 90) * (Math.PI / 180); const r = (d.score || 0) * 0.85; return `${110 + r * Math.cos(a)},${110 + r * Math.sin(a)}`; }).join(' ')} fill="url(#gradient)" fillOpacity="0.3" stroke="url(#gradient)" strokeWidth="2" />
                {dims.map((_, i) => { const a = (i * 360 / n - 90) * (Math.PI / 180); return <line key={i} x1={110} y1={110} x2={110 + 85 * Math.cos(a)} y2={110 + 85 * Math.sin(a)} stroke="#e2e8f0" strokeWidth="0.5" />; })}
                <defs><linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stopColor="#3b82f6" /><stop offset="100%" stopColor="#14b8a6" /></linearGradient></defs>
                {dims.map((d, i) => { const a = (i * 360 / n - 90) * (Math.PI / 180); const r = (d.score || 0) * 0.85; return <circle key={d.key} cx={110 + r * Math.cos(a)} cy={110 + r * Math.sin(a)} r="4" fill="#3b82f6" stroke="#fff" strokeWidth="2" />; })}
                {dims.map((d, i) => { const a = (i * 360 / n - 90) * (Math.PI / 180); const lr = 102; const label = d.label?.length > 4 ? d.label.slice(0, 4) : d.label; return <text key={d.key} x={110 + lr * Math.cos(a)} y={110 + lr * Math.sin(a)} textAnchor="middle" dominantBaseline="middle" className="text-[9px] font-semibold fill-surface-600">{label}</text>; })}
              </svg>
            )}
          </div>
        </div>

        {/* 学习目标 & 短板 */}
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <div className="flex items-center justify-between mb-5"><h3 className="font-display text-lg font-semibold text-surface-800">学习目标</h3></div>
          <div className="space-y-3">
            {(() => {
              const goalDim = dims.find(d => d.key === 'learning_goal');
              const rawValue = goalDim?.value;
              const goals: string[] = typeof rawValue === 'string' ? rawValue.split(/[,，、]/).filter(Boolean) : Array.isArray(rawValue) ? rawValue : rawValue && typeof rawValue === 'object' ? Object.values(rawValue).filter(v => typeof v === 'string') as string[] : [];
              const displayGoals = goals.length > 0 ? goals : ['请在对话中设置学习目标'];
              return displayGoals.map((goal, idx) => (
                <div key={idx} className="flex items-center gap-3 p-4 rounded-xl bg-gradient-to-r from-primary-50 to-accent-50 border border-primary-100">
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center text-white text-sm font-bold">{idx + 1}</div>
                  <p className="text-sm font-medium text-surface-700">{goal.trim()}</p>
                </div>
              ));
            })()}
          </div>
          <button onClick={() => chat.setOpen(true)} className="w-full mt-4 flex items-center justify-center gap-2 px-4 py-3 border-2 border-dashed border-surface-200 rounded-xl text-surface-400 hover:border-primary-300 hover:text-primary-600 transition-colors"><Sparkles size={16} /><span className="text-sm font-medium">对话设置目标</span></button>
        </div>
      </div>

      {/* 维度详情 */}
      <div className="bg-white rounded-2xl p-6 shadow-soft">
        <div className="flex items-center justify-between mb-6"><h3 className="font-display text-lg font-semibold text-surface-800">维度详情</h3><div className="flex items-center gap-2 text-sm"><span className="text-surface-400">综合评分</span><span className="text-2xl font-bold text-surface-800">{avgScore}</span></div></div>
        <div className="grid grid-cols-3 gap-4">
          {dims.map((dimension, idx) => {
            const key = dimension.key as string;
            const Icon = dimIcons[key] || Brain;
            const isSelected = selectedDimension === key;
            return (
              <div key={key} onClick={() => setSelectedDimension(isSelected ? null : key)} className={`p-5 rounded-xl border-2 cursor-pointer transition-all ${isSelected ? 'border-primary-500 bg-primary-50' : 'border-transparent bg-surface-50 hover:border-surface-200'}`}>
                <div className="flex items-start justify-between mb-4"><div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${colorGradientMap[idx % 9]} flex items-center justify-center shadow-lg`}><Icon size={22} className="text-white" /></div><span className="text-2xl font-bold text-surface-800">{dimension.score}</span></div>
                <h4 className="font-semibold text-surface-800 mb-2">{dimension.label}</h4><p className="text-sm text-surface-500">{dimension.value || dimension.description}</p>
                <div className="mt-4 h-2 bg-surface-100 rounded-full overflow-hidden"><div className={`h-full rounded-full bg-gradient-to-r ${colorGradientMap[idx % 9]} transition-all duration-1000`} style={{ width: `${dimension.score}%` }} /></div>
                {isSelected && (
                  <div className="mt-4 pt-4 border-t border-surface-200 animate-fade-in">
                    <div className="flex items-center gap-2 text-sm text-surface-500"><span className="text-surface-400">置信度:</span><span className="font-semibold text-surface-700">{dimension.confidence ? Math.round(dimension.confidence * 100) : 0}%</span></div>
                    {dimension.explanation && <p className="text-xs text-surface-500 mt-2">{dimension.explanation}</p>}
                    <div className="flex items-center gap-2 mt-2 text-xs text-surface-400"><span>来源: {dimension.source || '未知'}</span></div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 知识短板 */}
      {profile.weaknesses?.length > 0 && (
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4">知识短板</h3>
          <div className="space-y-3 max-h-[260px] overflow-y-auto pr-1">{profile.weaknesses.map((w, i) => (
            <div key={i} className="flex items-center gap-4 p-3 rounded-xl bg-surface-50 hover:bg-surface-100 transition-colors group">
              <div className="flex-1 min-w-0"><div className="flex items-center gap-2 mb-1.5"><span className="text-sm font-semibold text-surface-800">{w.topic}</span>{w.priority > 0 && <span className="px-2 py-0.5 bg-error-100 text-error-600 text-[10px] font-bold rounded-full">P{w.priority}</span>}</div><div className="flex items-center gap-3"><div className="flex-1 max-w-[140px] h-2 bg-error-100 rounded-full overflow-hidden"><div className="h-full bg-error-400 rounded-full" style={{ width: `${w.mastery}%` }} /></div><span className="text-xs font-semibold text-error-500 tabular-nums">{w.mastery}%</span></div></div>
              <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity"><button onClick={() => nav(`/resources?knowledgePoint=${encodeURIComponent(w.topic)}`)} className="px-3 py-1.5 bg-primary-50 text-primary-700 rounded-lg text-[11px] font-medium hover:bg-primary-100">资源</button></div>
            </div>
          ))}</div>
        </div>
      )}

      {/* 学习偏好 */}
      {profile.preferences && (
        <div className="text-center text-sm text-surface-400 pt-6 border-t border-surface-200">
          <span className="font-semibold text-surface-500 mr-2">学习偏好</span>{(profile.preferences.preferredFormats || ['文本']).join(' / ')} <span className="mx-2">·</span> {profile.preferences.paceMinutes}min/次 <span className="mx-2">·</span> {profile.preferences.difficulty === 'beginner' ? '入门' : profile.preferences.difficulty === 'intermediate' ? '进阶' : profile.preferences.difficulty === 'advanced' ? '高级' : '未知'} <span className="mx-2">·</span> {profile.preferences.explainStyle === 'diagram' ? '图解优先' : profile.preferences.explainStyle === 'code' ? '代码优先' : profile.preferences.explainStyle === 'case' ? '案例优先' : profile.preferences.explainStyle === 'theory' ? '理论优先' : '未知'}
        </div>
      )}

      {/* 对话式更新横幅 */}
      <div className="bg-gradient-to-r from-primary-50 to-accent-50 rounded-2xl p-6 border border-primary-100">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4"><div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center text-white"><Sparkles size={28} /></div><div><h3 className="font-display text-lg font-semibold text-surface-800">对话式画像更新</h3><p className="text-surface-500 mt-1">通过自然语言对话，智能更新你的学习特征</p></div></div>
          <button onClick={() => chat.setOpen(true)} className="flex items-center gap-2 px-6 py-3 bg-white rounded-xl font-semibold text-primary-600 hover:bg-primary-50 transition-colors shadow-card">开始对话 <ChevronRight size={18} /></button>
        </div>
      </div>
    </div>
  );
}
