import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLearningPath } from '../hooks/useLearningPath';
import type { PathNode, LearningStage } from '../types/learningPath';
import { RESOURCE_TYPE_LABELS } from '../utils/constants';
import {
  CheckCircle, Lock, Play, ArrowRight, Clock, GitFork, Target, AlertTriangle,
  BookOpen, ChevronDown, ChevronRight, Sparkles, Star, ExternalLink,
} from 'lucide-react';
import Loading from '../components/common/Loading';
import EmptyState from '../components/common/EmptyState';
import { formatDuration } from '../utils/format';

/* ===================================================================
 * 节点状态常量
 * =================================================================== */
const STATUS_CONFIG = {
  locked:      { icon: Lock,        label: '未解锁',  bg: 'bg-gray-50 border-gray-100',    iconColor: 'text-gray-300' },
  available:   { icon: Play,        label: '可开始',  bg: 'bg-white border-brand-200',      iconColor: 'text-brand-500' },
  in_progress: { icon: Sparkles,    label: '学习中',  bg: 'bg-brand-50 border-brand-200',   iconColor: 'text-brand-500' },
  mastered:    { icon: CheckCircle, label: '已掌握',  bg: 'bg-green-50/70 border-green-200', iconColor: 'text-green-500' },
} as const;

/* ===================================================================
 * 节点卡片 — 带资源点击跳转
 * =================================================================== */
function NodeCard({ node, isLast, isRecommended }: {
  node: PathNode;
  isLast: boolean;
  isRecommended: boolean;
}) {
  const navigate = useNavigate();
  const cfg = STATUS_CONFIG[node.status];
  const isLocked = node.status === 'locked';

  const statusIcon = node.status === 'in_progress' ? (
    <div className="w-4 h-4 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
  ) : (
    <cfg.icon className={`w-4 h-4 ${cfg.iconColor}`} />
  );

  return (
    <div className="flex gap-3 group">
      {/* 时间线 */}
      <div className="flex flex-col items-center flex-shrink-0">
        {/* 推荐标记 */}
        {isRecommended && (
          <div className="relative mb-1">
            <div className="absolute -top-1 -left-1 w-5 h-5 bg-amber-400 rounded-full animate-ping opacity-30" />
            <Star className="w-4 h-4 text-amber-500 relative z-10" />
          </div>
        )}
        <div className={`w-9 h-9 rounded-xl flex items-center justify-center border-2 transition-all ${
          isLocked ? 'bg-gray-100 border-gray-200' : 'bg-white border-brand-200 shadow-sm'
        } ${isRecommended ? 'ring-2 ring-amber-300 ring-offset-2' : ''}`}>
          {statusIcon}
        </div>
        {!isLast && (
          <div className={`w-0.5 flex-1 min-h-[24px] my-1 transition-colors ${
            node.status === 'mastered' ? 'bg-green-300' : 'bg-gray-200'
          }`} />
        )}
      </div>

      {/* 内容 */}
      <div className={`flex-1 rounded-xl border p-4 mb-3 transition-all duration-200 ${
        cfg.bg
      } ${!isLocked ? 'hover:shadow-md cursor-pointer' : 'opacity-70'}`}>
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h4 className={`text-sm font-semibold ${isLocked ? 'text-gray-400' : 'text-gray-900'}`}>
                {node.topic}
              </h4>
              {node.isKeyPoint && (
                <span className="px-1.5 py-0.5 bg-amber-50 text-amber-600 border border-amber-200 rounded text-[10px] font-medium">⭐ 重点</span>
              )}
              {isRecommended && (
                <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 border border-amber-300 rounded text-[10px] font-medium animate-pulse">
                  推荐起点
                </span>
              )}
            </div>
            <p className="text-xs text-gray-400 line-clamp-2">{node.description}</p>
          </div>

          {/* 掌握度 */}
          <div className="text-right flex-shrink-0 ml-3">
            <div className={`text-xs font-bold ${isLocked ? 'text-gray-300' : 'text-gray-700'}`}>
              {node.mastery}%
            </div>
            <div className="h-1.5 w-14 bg-gray-100 rounded-full mt-1 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  node.mastery >= 80 ? 'bg-green-500' : node.mastery >= 40 ? 'bg-brand-500' : 'bg-gray-300'
                }`}
                style={{ width: `${node.mastery}%` }}
              />
            </div>
          </div>
        </div>

        {/* 关联资源 — 可点击跳转 */}
        {node.resources.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-gray-100/80">
            {node.resources.map((r) => (
              <button
                key={r.resourceId}
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(`/resources/${r.resourceId}`);
                }}
                disabled={isLocked}
                className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium transition-all ${
                  r.completed
                    ? 'bg-green-50 text-green-600 cursor-default'
                    : isLocked
                      ? 'bg-gray-50 text-gray-300 cursor-not-allowed'
                      : 'bg-gray-50 text-gray-500 hover:bg-brand-50 hover:text-brand-600'
                } ${r.essential ? 'ring-1 ring-brand-300' : ''}`}
                title={r.completed ? '已完成' : isLocked ? '解锁后可用' : `跳转到 ${r.title}`}
              >
                {r.completed && <CheckCircle className="w-2.5 h-2.5" />}
                {r.title}
                {r.essential && ' 必学'}
                {!isLocked && !r.completed && <ExternalLink className="w-2.5 h-2.5 ml-0.5 opacity-50" />}
              </button>
            ))}
          </div>
        )}

        {/* 前置依赖 */}
        {node.prerequisites.length > 0 && isLocked && (
          <p className="text-[10px] text-gray-400 mt-2 flex items-center gap-1">
            <Lock className="w-3 h-3" />
            前置要求：{node.prerequisites.join('、')}
          </p>
        )}

        {/* 艾宾浩斯复习提醒 */}
        {node.reviewSchedule && node.status === 'mastered' && (
          <p className="text-[10px] text-amber-500 mt-2 flex items-center gap-1">
            ⏰ 第 {node.reviewSchedule.reviewCount} 次复习 · {
              new Date(node.reviewSchedule.nextReviewAt).toLocaleDateString('zh-CN')
            }
          </p>
        )}
      </div>
    </div>
  );
}

/* ===================================================================
 * 阶段组件
 * =================================================================== */
function StageSection({ stage, defaultExpanded }: { stage: LearningStage; defaultExpanded: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const completed = stage.nodes.filter((n) => n.status === 'mastered').length;
  const progress = Math.round((completed / stage.nodes.length) * 100);

  // 找到推荐起点（第一个 available 或 in_progress 的节点）
  const recommendedIdx = stage.nodes.findIndex((n) => n.status === 'available' || n.status === 'in_progress');

  return (
    <div className="mb-6">
      {/* 阶段头部 */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 bg-white border border-gray-100 rounded-2xl hover:shadow-sm transition-all group"
      >
        <div className="flex items-center gap-4">
          {/* 阶段图标 */}
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
            progress === 100 ? 'bg-green-50' : progress > 0 ? 'bg-brand-50' : 'bg-gray-50'
          }`}>
            {progress === 100 ? (
              <CheckCircle className="w-5 h-5 text-green-500" />
            ) : progress > 0 ? (
              <Play className="w-5 h-5 text-brand-500" />
            ) : (
              <Lock className="w-5 h-5 text-gray-300" />
            )}
          </div>

          <div className="text-left flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">
                阶段 {stage.order}
              </span>
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                progress === 100 ? 'bg-green-50 text-green-600' : progress > 0 ? 'bg-brand-50 text-brand-600' : 'bg-gray-50 text-gray-400'
              }`}>
                {progress}%
              </span>
            </div>
            <h3 className="text-base font-bold text-gray-900 mt-0.5">{stage.title}</h3>
            <p className="text-xs text-gray-400 mt-0.5">{stage.objective || stage.description}</p>
          </div>
        </div>

        <div className="flex items-center gap-4 flex-shrink-0">
          <div className="hidden sm:flex items-center gap-1.5 text-xs text-gray-400">
            <Clock className="w-3.5 h-3.5" />
            <span>约 {stage.estimatedDays} 天</span>
          </div>
          <div className="w-8 h-8 rounded-lg bg-gray-50 flex items-center justify-center transition-transform"
            style={{ transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)' }}>
            <ChevronDown className="w-4 h-4 text-gray-400" />
          </div>
        </div>
      </button>

      {/* 阶段节点列表 */}
      {expanded && (
        <div className="mt-3 pl-2">
          {stage.nodes.map((node, i) => (
            <NodeCard
              key={node.id}
              node={node}
              isLast={i === stage.nodes.length - 1}
              isRecommended={i === recommendedIdx}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ===================================================================
 * 主页面
 * =================================================================== */
export default function LearningPathPage() {
  const navigate = useNavigate();
  const { path, loading, error } = useLearningPath();

  if (loading && !path) return <Loading fullScreen text="加载学习路径..." />;

  if (error && !path) {
    return (
      <EmptyState
        icon={<AlertTriangle className="w-8 h-8" />}
        title="路径加载失败"
        description={error}
      />
    );
  }

  if (!path) {
    return (
      <EmptyState
        icon={<GitFork className="w-8 h-8" />}
        title="暂无学习路径"
        description="通过 AI 对话让系统为你规划个性化学习路径"
        action={
          <button
            onClick={() => navigate('/chat')}
            className="mt-3 px-5 py-2.5 bg-gray-900 text-white rounded-xl text-sm font-semibold hover:bg-gray-800 transition-all inline-flex items-center gap-2"
          >
            <Sparkles className="w-4 h-4" />
            去对话页生成学习路径
          </button>
        }
      />
    );
  }

  // 找到当前应该开始/继续的阶段和节点
  const currentStageIdx = path.stages.findIndex((s) =>
    s.nodes.some((n) => n.status === 'in_progress' || n.status === 'available')
  );
  const firstAvailableStage = currentStageIdx >= 0 ? currentStageIdx : 0;

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 md:py-8">
      {/* ========== 头部 ========== */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-2">
          <Target className="w-5 h-5 text-brand-500" />
          <span className="text-xs font-bold text-brand-500 uppercase tracking-wider">Personalized Learning Path</span>
        </div>
        <h1 className="text-2xl md:text-3xl font-extrabold text-gray-900 mb-1">{path.title}</h1>
        <p className="text-sm text-gray-500 mb-4">{path.description}</p>

        {/* 总体进度卡片 */}
        <div className="flex flex-col sm:flex-row items-stretch gap-3 p-4 bg-white border border-gray-100 rounded-2xl shadow-sm">
          {/* 进度条 */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs text-gray-500">总进度</span>
              <span className="text-sm font-bold text-gray-900">{path.overallProgress}%</span>
            </div>
            <div className="h-2.5 bg-gray-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-brand-500 to-brand-600 rounded-full transition-all duration-700 relative"
                style={{ width: `${path.overallProgress}%` }}
              >
                {path.overallProgress > 0 && path.overallProgress < 100 && (
                  <div className="absolute right-0 top-1/2 -translate-y-1/2 w-3 h-3 bg-white border-2 border-brand-500 rounded-full shadow-sm" />
                )}
              </div>
            </div>
          </div>

          {/* 数据指标 */}
          <div className="flex gap-2 flex-shrink-0">
            <div className="text-center px-4 py-2 bg-brand-50 rounded-xl">
              <div className="text-sm font-bold text-brand-600">{path.stages.length}</div>
              <div className="text-[10px] text-brand-500">阶段</div>
            </div>
            <div className="text-center px-4 py-2 bg-amber-50 rounded-xl">
              <div className="text-sm font-bold text-amber-600">{path.estimatedDays}</div>
              <div className="text-[10px] text-amber-500">预计天数</div>
            </div>
            <div className="text-center px-4 py-2 bg-green-50 rounded-xl">
              <div className="text-sm font-bold text-green-600">
                {path.stages.reduce((sum, s) => sum + s.nodes.filter((n) => n.status === 'mastered').length, 0)}
              </div>
              <div className="text-[10px] text-green-500">已掌握</div>
            </div>
          </div>
        </div>
      </div>

      {/* ========== 当前位置指示 ========== */}
      {firstAvailableStage >= 0 && path.overallProgress < 100 && (
        <div className="mb-6 p-4 bg-brand-50/60 border border-brand-100 rounded-2xl flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-brand-100 flex items-center justify-center flex-shrink-0">
            <Play className="w-4.5 h-4.5 text-brand-600" />
          </div>
          <div className="flex-1">
            <p className="text-sm font-semibold text-brand-800">
              推荐从「{path.stages[firstAvailableStage]?.title}」继续学习
            </p>
            <p className="text-xs text-brand-500 mt-0.5">
              下方已自动展开当前阶段，带有 ⭐ 标记的节点是推荐起点
            </p>
          </div>
          <ArrowRight className="w-4 h-4 text-brand-400" />
        </div>
      )}

      {/* ========== 阶段列表 ========== */}
      <div>
        {path.stages.map((stage, idx) => (
          <StageSection
            key={stage.id}
            stage={stage}
            defaultExpanded={idx === 0 || idx === firstAvailableStage}
          />
        ))}
      </div>

      {/* ========== 完成提示 ========== */}
      {path.overallProgress >= 100 && (
        <div className="text-center py-8">
          <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-3">
            <CheckCircle className="w-8 h-8 text-green-500" />
          </div>
          <p className="text-lg font-bold text-gray-800 mb-1">🎉 所有阶段已完成！</p>
          <p className="text-sm text-gray-500">你已掌握该课程所有核心知识点</p>
        </div>
      )}

      {/* 底部说明 */}
      <div className="text-center py-8 border-t border-gray-50 mt-6">
        <p className="text-xs text-gray-400">
          学习路径根据你的画像和进度动态调整 · 每完成一个知识点后自动更新规划
        </p>
      </div>
    </div>
  );
}
