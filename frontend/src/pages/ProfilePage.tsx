// @ts-nocheck
import { useState, useEffect } from 'react';
import { useChatPanel } from '../components/layout/AppLayout';
import { useProfile } from '../hooks/useProfile';
import { useLearningPath } from '../hooks/useLearningPath';
import { useChatStore } from '../store/chatStore';
import { RefreshCw, Sparkles, Brain, Target, Clock, TrendingUp, AlertCircle, BookOpen, Zap, Trophy, ChevronRight, GraduationCap, BarChart3 } from 'lucide-react';
import { PageLoading, PageError } from '../components/common/PageState';
import { getCurrentLearner } from '../store/authStore';

const DIM_LABELS: Record<string, string> = {
  major_background: '专业背景', knowledge_base: '知识基础', learning_goal: '学习目标',
  cognitive_style: '认知风格', error_patterns: '易错模式', coding_ability: '编程能力',
  learning_progress: '学习进度', interest_direction: '兴趣方向', learning_rhythm: '学习节奏',
};
const DIM_ICONS: Record<string, string> = {
  major_background: '🎓', knowledge_base: '📚', learning_goal: '🎯',
  cognitive_style: '🧠', error_patterns: '⚠️', coding_ability: '💻',
  learning_progress: '📊', interest_direction: '💡', learning_rhythm: '⏱️',
};

export default function ProfilePage() {
  const chat = useChatPanel();
  const { profile, loading, error, fetchProfile, buildProfile } = useProfile();
  const { path } = useLearningPath();
  const sessionId = useChatStore(s => s.currentSessionId);
  const isParent = getCurrentLearner()?.role === 'parent';
  const [isUpdating, setIsUpdating] = useState(false);
  const [recommendations, setRecommendations] = useState<any[]>([]);

  useEffect(() => { fetchProfile(); }, []);
  useEffect(() => {
    if (!sessionId) return;
    fetch(`/api/profile/recommendations?sessionId=${encodeURIComponent(sessionId)}`)
      .then(r => r.json()).then(d => setRecommendations(d?.data?.recommendations || [])).catch(() => {});
  }, [sessionId, profile]);

  const handleRefresh = async () => {
    if (isParent || !sessionId) return;
    setIsUpdating(true);
    try { await buildProfile('请重新构建我的学习画像'); await fetchProfile(); }
    catch { /* ignore */ }
    finally { setIsUpdating(false); }
  };

  if (loading && !profile) return <PageLoading text="加载学习画像…" />;
  if (error && !profile) return <PageError title="画像加载失败" description={error} onRetry={fetchProfile} />;

  const dims = profile?.dimensions || [];
  const weaknesses = profile?.weaknesses || [];
  const history = profile?.history || {};
  const preferences = profile?.preferences || {};
  const readiness = profile?.readiness || {};

  // 路径统计
  const totalKps = path?.stages?.reduce((s, st) => s + (st.chapters?.reduce((cs, ch) => cs + ch.sections?.reduce((ss, sec) => ss + (sec.knowledgePoints?.length ?? 0), 0), 0) ?? st.nodes?.length ?? 0), 0) ?? 0;
  const masteredKps = path?.stages?.reduce((s, st) => s + (st.chapters?.reduce((cs, ch) => cs + ch.sections?.reduce((ss, sec) => ss + (sec.knowledgePoints?.filter(k => k.status === 'mastered').length ?? 0), 0), 0) ?? st.nodes?.filter(n => n.status === 'mastered').length ?? 0), 0) ?? 0;

  if (!dims.length && !weaknesses.length && !history.totalStudyMinutes) return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h2 className="text-2xl font-bold">学习画像</h2><p className="text-gray-500 mt-1">通过自然对话自动构建，无需填表</p></div>
        {!isParent && <button onClick={handleRefresh} disabled={isUpdating} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"><RefreshCw size={16} className={isUpdating ? 'animate-spin' : ''} />{isUpdating ? '更新中...' : '构建画像'}</button>}
      </div>
      <div className="bg-white rounded-xl p-10 text-center shadow-sm">
        <Brain size={40} className="mx-auto mb-3 text-gray-300" />
        <h3 className="text-lg font-semibold mb-2">尚未构建学习画像</h3>
        <p className="text-gray-500 mb-4">在对话中告诉 AI 你的专业、基础、目标，系统会自动构建画像</p>
        <button onClick={() => chat.setOpen(true)} className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700"><Sparkles size={16} />开始对话</button>
      </div>
    </div>
  );

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div><h2 className="text-2xl font-bold">学习画像</h2><p className="text-gray-500 text-sm mt-1">对话驱动 · 动态更新 · 精准推荐</p></div>
        {!isParent && <button onClick={handleRefresh} disabled={isUpdating} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm"><RefreshCw size={14} className={isUpdating ? 'animate-spin' : ''} />更新画像</button>}
      </div>

      {/* ── 概览统计 ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { icon: <Clock size={18} className="text-blue-500" />, label: '累计学习', value: `${Math.floor((history.totalStudyMinutes || 0) / 60)}h`, color: 'bg-blue-50' },
          { icon: <Target size={18} className="text-emerald-500" />, label: '练习正确率', value: history.quizAccuracy != null ? `${history.quizAccuracy}%` : '暂无', color: 'bg-emerald-50' },
          { icon: <Trophy size={18} className="text-amber-500" />, label: '连续学习', value: `${history.streak || 0}天`, color: 'bg-amber-50' },
          { icon: <GraduationCap size={18} className="text-violet-500" />, label: '已掌握', value: `${masteredKps}/${totalKps}`, color: 'bg-violet-50' },
        ].map((stat) => (
          <div key={stat.label} className={`${stat.color} rounded-2xl p-4 text-center`}>
            <div className="flex justify-center mb-1.5">{stat.icon}</div>
            <p className="text-xl font-bold text-surface-800">{stat.value}</p>
            <p className="text-[10px] text-surface-400 mt-0.5">{stat.label}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* ── 画像维度 ── */}
        <div className="lg:col-span-2 space-y-4">
          <h3 className="font-semibold text-surface-700 flex items-center gap-2"><Brain size={16} className="text-blue-500" />学习画像维度</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {dims.map((dim: any) => {
              const key = dim.key || dim.id || '';
              const label = DIM_LABELS[key] || dim.label || dim.name || key;
              const text = dim.description || dim.explanation || dim.value || '';
              const score = dim.score || dim.value || 50;
              const scoreNum = typeof score === 'number' ? score : parseInt(String(score)) || 50;
              if (!text) return null;
              return (
                <div key={key} className="bg-white rounded-xl p-4 shadow-sm border border-surface-100">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-lg">{DIM_ICONS[key] || '📌'}</span>
                    <span className="text-sm font-semibold text-surface-700">{label}</span>
                    <span className="ml-auto text-[10px] text-surface-400">{dim.source === 'user_input' ? '来自对话' : dim.source === 'llm_generated' ? 'AI分析' : '系统推测'}</span>
                  </div>
                  <p className="text-sm text-surface-600 leading-relaxed">{text}</p>
                  <div className="flex items-center gap-2 mt-2">
                    <div className="flex-1 h-1.5 bg-surface-100 rounded-full overflow-hidden">
                      <div className="h-full bg-gradient-to-r from-blue-400 to-violet-400 rounded-full transition-all" style={{ width: `${scoreNum}%` }} />
                    </div>
                    <span className="text-[10px] font-medium text-surface-500">{scoreNum}%</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ── 右侧：薄弱 + 推荐 ── */}
        <div className="space-y-4">
          {/* 薄弱点 */}
          {weaknesses.length > 0 && (
            <div className="bg-white rounded-2xl p-5 shadow-sm border border-surface-100">
              <h3 className="font-semibold text-surface-700 flex items-center gap-2 mb-3"><AlertCircle size={16} className="text-amber-500" />薄弱环节</h3>
              <div className="space-y-2">
                {weaknesses.slice(0, 5).map((w: any, i: number) => (
                  <div key={i} className="p-3 bg-amber-50 rounded-xl">
                    <p className="text-sm font-medium text-surface-700">{w.topic || w.name || '未命名'}</p>
                    <p className="text-xs text-surface-400 mt-0.5">{w.reason || w.explanation || ''}</p>
                    {w.priority && (
                      <span className={`inline-block mt-1.5 text-[10px] px-2 py-0.5 rounded-full ${w.priority === 'high' ? 'bg-red-100 text-red-600' : 'bg-amber-100 text-amber-600'}`}>
                        {w.priority === 'high' ? '高优先级' : '中优先级'}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 学习偏好 */}
          <div className="bg-white rounded-2xl p-5 shadow-sm border border-surface-100">
            <h3 className="font-semibold text-surface-700 flex items-center gap-2 mb-3"><Zap size={16} className="text-violet-500" />学习偏好</h3>
            <div className="space-y-2 text-sm">
              {preferences.preferredFormats?.length > 0 && (
                <div className="flex items-center justify-between"><span className="text-surface-500">偏好形式</span><span className="text-surface-700">{preferences.preferredFormats.join('、')}</span></div>
              )}
              {preferences.paceMinutes > 0 && (
                <div className="flex items-center justify-between"><span className="text-surface-500">单次时长</span><span className="text-surface-700">{preferences.paceMinutes}分钟</span></div>
              )}
              {preferences.difficulty && preferences.difficulty !== 'unknown' && (
                <div className="flex items-center justify-between"><span className="text-surface-500">难度偏好</span><span className="text-surface-700">{preferences.difficulty === 'beginner' ? '入门' : preferences.difficulty === 'intermediate' ? '中级' : '进阶'}</span></div>
              )}
              {preferences.explainStyle && preferences.explainStyle !== 'unknown' && (
                <div className="flex items-center justify-between"><span className="text-surface-500">讲解风格</span><span className="text-surface-700">{preferences.explainStyle === 'diagram' ? '图解优先' : preferences.explainStyle === 'code' ? '代码驱动' : preferences.explainStyle === 'text' ? '文字详细' : preferences.explainStyle}</span></div>
              )}
              {!preferences.preferredFormats?.length && !preferences.paceMinutes && (
                <p className="text-xs text-surface-400">在对话中告诉 AI 你的学习偏好，系统会自动记录</p>
              )}
            </div>
          </div>

          {/* 推荐操作 */}
          <div className="bg-gradient-to-br from-blue-50 to-violet-50 rounded-2xl p-5">
            <h3 className="font-semibold text-surface-700 flex items-center gap-2 mb-3"><TrendingUp size={16} className="text-blue-500" />建议下一步</h3>
            <div className="space-y-2">
              {!path && (
                <button onClick={() => chat.setOpen(true)} className="w-full flex items-center gap-2 p-3 bg-white rounded-xl text-sm text-surface-700 hover:shadow-sm transition-all">
                  <Sparkles size={14} className="text-blue-500" />去对话生成学习路径<ChevronRight size={14} className="ml-auto text-surface-300" />
                </button>
              )}
              {path && masteredKps < totalKps && (
                <button onClick={() => window.location.href = '/path'} className="w-full flex items-center gap-2 p-3 bg-white rounded-xl text-sm text-surface-700 hover:shadow-sm transition-all">
                  <BookOpen size={14} className="text-emerald-500" />继续学习路径（{totalKps - masteredKps}个知识点待完成）<ChevronRight size={14} className="ml-auto text-surface-300" />
                </button>
              )}
              {weaknesses.length > 0 && (
                <button onClick={() => chat.setOpen(true)} className="w-full flex items-center gap-2 p-3 bg-white rounded-xl text-sm text-surface-700 hover:shadow-sm transition-all">
                  <Target size={14} className="text-amber-500" />专项练习薄弱环节<ChevronRight size={14} className="ml-auto text-surface-300" />
                </button>
              )}
              <button onClick={() => window.location.href = '/resources'} className="w-full flex items-center gap-2 p-3 bg-white rounded-xl text-sm text-surface-700 hover:shadow-sm transition-all">
                <BarChart3 size={14} className="text-violet-500" />查看学习资源库<ChevronRight size={14} className="ml-auto text-surface-300" />
              </button>
            </div>
          </div>

          {/* 个性化推荐 */}
          {recommendations.length > 0 && (
            <div className="bg-white rounded-2xl p-5 shadow-sm border border-surface-100">
              <h3 className="font-semibold text-surface-700 flex items-center gap-2 mb-3"><Zap size={16} className="text-amber-500" />为你推荐</h3>
              <div className="space-y-2">
                {recommendations.slice(0, 5).map((rec: any, i: number) => (
                  <div key={i} className={`p-3 rounded-xl border cursor-pointer hover:shadow-sm transition-all ${rec.priority === 'high' ? 'border-amber-200 bg-amber-50/50' : 'border-surface-100 bg-surface-50'}`}
                    onClick={() => { if (rec.target_resource_id) window.location.href = `/resources/${rec.target_resource_id}`; }}>
                    <div className="flex items-center gap-2">
                      <span className={`w-1.5 h-1.5 rounded-full ${rec.priority === 'high' ? 'bg-amber-400' : 'bg-surface-300'}`} />
                      <p className="text-sm font-medium text-surface-700 flex-1">{rec.title}</p>
                      <span className="text-[10px] text-surface-400">{rec.source === 'profile' ? '🎯 画像推荐' : '📊 数据分析'}</span>
                    </div>
                    <p className="text-xs text-surface-400 mt-1 ml-3.5">{rec.reason}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
