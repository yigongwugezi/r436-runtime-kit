import { useLearningPath } from '../hooks/useLearningPath';
import type { PathNode, LearningStage } from '../types/learningPath';
import {
  CheckCircle, Lock, Play, ArrowRight, Clock, GitFork, Target, BookOpen,
} from 'lucide-react';
import Loading from '../components/common/Loading';
import EmptyState from '../components/common/EmptyState';
import { formatDuration } from '../utils/format';

/* ===================================================================
 * 子组件
 * =================================================================== */

function NodeCard({ node, isLast }: { node: PathNode; isLast: boolean }) {
  const statusIcon = {
    locked: <Lock className="w-4 h-4 text-gray-300" />,
    available: <Play className="w-4 h-4 text-brand-500" />,
    in_progress: (
      <div className="w-4 h-4 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
    ),
    mastered: <CheckCircle className="w-4 h-4 text-green-500" />,
  };

  const statusBg = {
    locked: 'bg-gray-50 border-gray-100',
    available: 'bg-white border-brand-200 hover:border-brand-300 cursor-pointer',
    in_progress: 'bg-brand-50 border-brand-200',
    mastered: 'bg-green-50/50 border-green-200',
  };

  return (
    <div className="flex gap-3">
      {/* 时间线 */}
      <div className="flex flex-col items-center">
        <div className={`w-8 h-8 rounded-xl flex items-center justify-center border ${node.status === 'locked' ? 'bg-gray-100 border-gray-200' : 'bg-white border-brand-200'}`}>
          {statusIcon[node.status]}
        </div>
        {!isLast && <div className="w-0.5 flex-1 min-h-[20px] bg-gray-200 my-1" />}
      </div>

      {/* 内容 */}
      <div className={`flex-1 rounded-xl border p-4 mb-3 transition-all ${statusBg[node.status]}`}>
        <div className="flex items-start justify-between mb-2">
          <div>
            <h4 className="text-sm font-semibold text-gray-900">{node.topic}</h4>
            <p className="text-xs text-gray-400 mt-0.5">{node.description}</p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {node.isKeyPoint && (
              <span className="px-2 py-0.5 bg-amber-50 text-amber-600 border border-amber-200 rounded-md text-[10px] font-medium">
                重点
              </span>
            )}
            <div className="text-right">
              <div className="text-xs font-bold text-gray-700">{node.mastery}%</div>
              <div className="h-1.5 w-16 bg-gray-100 rounded-full mt-0.5 overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${node.mastery >= 80 ? 'bg-green-500' : node.mastery >= 50 ? 'bg-brand-500' : 'bg-gray-300'}`}
                  style={{ width: `${node.mastery}%` }}
                />
              </div>
            </div>
          </div>
        </div>

        {node.resources.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-gray-100">
            {node.resources.map((r) => (
              <span
                key={r.resourceId}
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium ${
                  r.completed ? 'bg-green-50 text-green-600' : 'bg-gray-50 text-gray-500'
                } ${r.essential ? 'ring-1 ring-brand-200' : ''}`}
              >
                {r.completed && <CheckCircle className="w-2.5 h-2.5" />}
                {r.title}
                {r.essential && ' *'}
              </span>
            ))}
          </div>
        )}

        {/* 前置依赖提示 */}
        {node.prerequisites.length > 0 && node.status === 'locked' && (
          <p className="text-[10px] text-gray-400 mt-2">
            前置要求：{node.prerequisites.join('、')}
          </p>
        )}
      </div>
    </div>
  );
}

function StageSection({ stage }: { stage: LearningStage }) {
  const completed = stage.nodes.filter((n) => n.status === 'mastered').length;
  const progress = Math.round((completed / stage.nodes.length) * 100);

  return (
    <div className="mb-8">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-bold text-gray-900">
            第 {stage.order} 阶段 · {stage.title}
          </h3>
          <p className="text-xs text-gray-400 mt-0.5">{stage.description}</p>
        </div>
        <div className="text-right flex-shrink-0">
          <div className="flex items-center gap-1.5 text-xs text-gray-500">
            <Clock className="w-3.5 h-3.5" />
            <span>{formatDuration(stage.estimatedDays * 60)}</span>
          </div>
          <div className="text-xs font-bold text-brand-600 mt-0.5">{progress}%</div>
        </div>
      </div>

      <div className="pl-1">
        {stage.nodes.map((node, i) => (
          <NodeCard key={node.id} node={node} isLast={i === stage.nodes.length - 1} />
        ))}
      </div>
    </div>
  );
}

/* ===================================================================
 * 主页面
 * =================================================================== */

export default function LearningPathPage() {
  const { path, loading } = useLearningPath();

  if (loading) return <Loading fullScreen text="加载学习路径..." />;

  if (!path) {
    return (
      <EmptyState
        icon={<GitFork className="w-8 h-8" />}
        title="暂无学习路径"
        description="通过对话让 AI 为你规划个性化学习路径"
      />
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 md:py-8">
      {/* 头部 */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-2">
          <Target className="w-5 h-5 text-brand-500" />
          <span className="text-xs font-bold text-brand-500 uppercase tracking-wider">Learning Path</span>
        </div>
        <h1 className="text-2xl md:text-3xl font-extrabold text-gray-900 mb-2">{path.title}</h1>
        <p className="text-sm text-gray-500 mb-4">{path.description}</p>

        {/* 总体进度 */}
        <div className="flex items-center gap-4 p-4 bg-white border border-gray-100 rounded-2xl">
          <div className="flex-1">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs text-gray-500">总体进度</span>
              <span className="text-sm font-bold text-gray-900">{path.overallProgress}%</span>
            </div>
            <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-brand-500 to-brand-600 rounded-full transition-all duration-500"
                style={{ width: `${path.overallProgress}%` }}
              />
            </div>
          </div>
          <div className="text-center flex-shrink-0 px-4 py-2 bg-gray-50 rounded-xl">
            <div className="text-sm font-bold text-gray-900">{path.stages.length}</div>
            <div className="text-[10px] text-gray-400">阶段</div>
          </div>
          <div className="text-center flex-shrink-0 px-4 py-2 bg-gray-50 rounded-xl">
            <div className="text-sm font-bold text-gray-900">{path.estimatedDays}</div>
            <div className="text-[10px] text-gray-400">预计天数</div>
          </div>
        </div>
      </div>

      {/* 阶段列表 */}
      {path.stages.map((stage) => (
        <StageSection key={stage.id} stage={stage} />
      ))}

      {/* 底部提示 */}
      <div className="text-center py-8">
        <p className="text-xs text-gray-400">
          学习路径根据你的画像和进度动态调整，每完成一个知识点后系统会自动更新后续规划
        </p>
      </div>
    </div>
  );
}
