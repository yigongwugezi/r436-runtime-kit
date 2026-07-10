import { useState, useEffect } from 'react';
import { useChatPanel } from '../components/layout/AppLayout';
import { useProfile } from '../hooks/useProfile';
import { useChatStore } from '../store/chatStore';
import { RefreshCw, Sparkles } from 'lucide-react';
import { PageLoading, PageError } from '../components/common/PageState';
import { getCurrentLearner } from '../store/authStore';

const DIM_LABELS: Record<string, string> = {
  major_background: '专业背景',
  knowledge_base: '知识基础',
  learning_goal: '学习目标',
  cognitive_style: '认知风格',
  error_patterns: '易错模式',
  coding_ability: '编程能力',
  learning_progress: '学习进度',
  interest_direction: '兴趣方向',
  learning_rhythm: '学习节奏',
};

export default function ProfilePage() {
  const chat = useChatPanel();
  const { profile, loading, error, fetchProfile, buildProfile } = useProfile();
  const sessionId = useChatStore(s => s.currentSessionId);
  const isParent = getCurrentLearner()?.role === 'parent';
  const [isUpdating, setIsUpdating] = useState(false);

  useEffect(() => { fetchProfile(); }, []);

  const handleRefresh = async () => {
    if (isParent) return;
    if (!sessionId) { chat.setOpen(true); return; }
    setIsUpdating(true);
    try { await buildProfile('请重新构建我的学习画像'); await fetchProfile(); }
    catch { /* ignore */ }
    finally { setIsUpdating(false); }
  };

  if (loading && !profile) return <PageLoading text="加载学习画像…" />;
  if (error && !profile) return <PageError title="画像加载失败" description={error} onRetry={fetchProfile} />;

  const dims = profile?.dimensions || [];

  if (!dims.length) return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h2 className="text-2xl font-bold">学习画像</h2><p className="text-gray-500 mt-1">通过自然对话自动构建，无需填表</p></div>
        {!isParent && <button onClick={handleRefresh} disabled={isUpdating} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"><RefreshCw size={16} className={isUpdating ? 'animate-spin' : ''} />{isUpdating ? '更新中...' : '构建画像'}</button>}
      </div>
      <div className="bg-white rounded-xl p-10 text-center shadow-sm">
        <h3 className="text-lg font-semibold mb-2">尚未构建学习画像</h3>
        <p className="text-gray-500 mb-4">在对话中告诉 AI 你的专业、基础、目标，系统会自动构建画像</p>
        <button onClick={() => chat.setOpen(true)} className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700"><Sparkles size={16} />开始对话</button>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h2 className="text-2xl font-bold">学习画像</h2><p className="text-gray-500 mt-1">通过自然对话自动构建，随学随新</p></div>
        {!isParent && <button onClick={handleRefresh} disabled={isUpdating} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"><RefreshCw size={16} className={isUpdating ? 'animate-spin' : ''} />更新画像</button>}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {dims.map((dim: any) => {
          const key = dim.key || dim.id || '';
          const label = DIM_LABELS[key] || dim.label || dim.name || key;
          const value = dim.value || dim.description || '';
          const explanation = dim.explanation || '';
          const source = dim.source || '';

          if (!value && !explanation) return null;

          return (
            <div key={key} className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
              <h3 className="font-semibold text-gray-800 mb-2">{label}</h3>
              {value && value !== '待补充' && (
                <p className="text-gray-700">{value}</p>
              )}
              {explanation && explanation !== value && (
                <p className="text-gray-500 text-sm mt-1">{explanation}</p>
              )}
              {source && (
                <span className="inline-block mt-2 text-xs text-gray-400 bg-gray-50 px-2 py-0.5 rounded">
                  {source === 'user_input' ? '来自对话' : source === 'llm_generated' ? 'AI 分析' : source === 'inferred' ? '系统推测' : source}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
