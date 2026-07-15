import { useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Target, Zap } from 'lucide-react';
import { useChatPanel } from '../components/layout/AppLayout';
import PathModeRouter from '../components/learning/PathModeViews';
import { PageEmpty, PageError, PageLoading } from '../components/common/PageState';
import { useLearningPath } from '../hooks/useLearningPath';
import { getCurrentLearner } from '../store/authStore';
import { adaptLearningPath, type PathDisplayMode, type PathRouteTarget } from '../utils/learningPathViewModel';

export default function LearningPathPage() {
  const nav = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const chat = useChatPanel();
  const { path, loading, error, fetchPath } = useLearningPath();
  const view = useMemo(() => adaptLearningPath(path, searchParams.get('mode')), [path, searchParams]);
  const isParent = getCurrentLearner()?.role === 'parent';

  const updateSearch = (key: string, value: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next);
  };
  const navigateTarget = (target: PathRouteTarget) => {
    if (!target.id || target.kind === 'unavailable') return;
    const context = new URLSearchParams({ pathMode: view.mode });
    const viewStage = searchParams.get('viewStage');
    if (viewStage) context.set('viewStage', viewStage);
    if (target.stageId) context.set('stageId', target.stageId);
    if (target.chapterId) context.set('chapterId', target.chapterId);
    const destination = target.kind === 'chapter' ? '/lecture/' : '/lecture/section/';
    nav(`${destination}${encodeURIComponent(target.id)}?${context.toString()}`);
  };

  if (loading) return <PageLoading text="加载学习路径中…" />;
  if (error && !path) return <PageError title="学习路径加载失败" description={error} onRetry={fetchPath} />;
  if (!path || view.dataCompleteness === 'empty') {
    return (
      <div className="space-y-6 animate-fade-in">
        <div><h2 className="font-display text-2xl font-bold text-surface-800">学习路径</h2><p className="text-surface-500 mt-1">基于你的学习画像智能规划的进阶路线</p></div>
        <PageEmpty
          icon={<Target size={40} className="text-surface-300" />}
          title="尚未生成学习路径"
          description="在聊天中明确告诉 AI 你的学习目标，例如：“我想用两周时间入门深度学习”。"
          action={<button onClick={() => chat.setOpen(true)} className="mt-4 px-5 py-2.5 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 transition-colors">去对话生成</button>}
        />
      </div>
    );
  }

  return (
    <div className="animate-fade-in flex-1 flex flex-col">
      <div className="flex items-center justify-between mb-5 flex-shrink-0">
        <div><h2 className="font-display text-2xl font-bold text-surface-800">学习路径</h2><p className="text-surface-500 mt-1">基于当前路径数据展示章节、日课或项目计划</p></div>
        {!isParent && <button onClick={() => chat.setOpen(true)} className="flex items-center gap-2 px-5 py-2.5 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 transition-colors"><Zap size={18} />完善路径</button>}
      </div>
      <PathModeRouter
        view={view}
        expandedStageKey={searchParams.get('viewStage')}
        onModeChange={(mode: PathDisplayMode) => updateSearch('mode', mode)}
        onExpandedStageChange={(stageKey) => updateSearch('viewStage', stageKey)}
        onNavigate={navigateTarget}
      />
    </div>
  );
}
