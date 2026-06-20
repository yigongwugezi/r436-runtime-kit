import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLearningPath } from '../hooks/useLearningPath';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';
import type { PathNode, LearningStage, PathNodeStatus, StageStatus } from '../types/learningPath';
import { RESOURCE_TYPE_LABELS } from '../utils/constants';
import {
  CheckCircle, Lock, Play, ArrowRight, Clock, GitFork, Target, AlertTriangle,
  BookOpen, ChevronDown, ChevronRight, Sparkles, Star, ExternalLink, RefreshCw,
  Circle, CheckCircle2, MoreHorizontal, Layers, Flag, ListChecks,
} from 'lucide-react';
import SourceBadge from '../components/common/SourceBadge';
import {
  PageLoading, PageEmpty, PageError, SourceTag, FallbackBanner, RefreshOverlay,
} from '../components/common/PageState';
import { formatDuration, timeAgo } from '../utils/format';
import { logStudyEvent } from '../api/feedback';

/* ===================================================================
 * 节点状态常量
 * =================================================================== */
const STATUS_CONFIG: Record<PathNodeStatus, { icon: any; label: string; bg: string; iconColor: string }> = {
  locked:      { icon: Lock,        label: '未解锁',  bg: 'bg-gray-50 border-gray-100',    iconColor: 'text-gray-300' },
  available:   { icon: Circle,      label: '未开始',  bg: 'bg-white border-gray-200',      iconColor: 'text-gray-400' },
  in_progress: { icon: Play,        label: '进行中',  bg: 'bg-brand-50 border-brand-200',  iconColor: 'text-brand-500' },
  mastered:    { icon: CheckCircle2, label: '已完成',  bg: 'bg-green-50/70 border-green-200', iconColor: 'text-green-500' },
};

/* ===================================================================
 * 节点卡片 — 点击跳转到该节点的资源
 * =================================================================== */
function NodeCard({ node, isLast, isRecommended, onStatusChange }: {
  node: PathNode;
  isLast: boolean;
  isRecommended: boolean;
  onStatusChange: (nodeId: string, status: PathNodeStatus) => void;
}) {
  const navigate = useNavigate();
  const cfg = STATUS_CONFIG[node.status];
  const isLocked = node.status === 'locked';

  // 点击节点体 → 跳转到资源库并筛选该节点对应的资源（按 taskId 精确匹配）
  const handleNodeClick = () => {
    if (isLocked) return;
    navigate(`/resources?taskId=${node.id}`);
  };

  const statusIcon = node.status === 'in_progress' ? (
    <div className="w-4 h-4 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
  ) : (
    <cfg.icon className={`w-4 h-4 ${cfg.iconColor}`} />
  );

  return (
    <div className="flex gap-3 group">
      {/* 时间线 */}
      <div className="flex flex-col items-center flex-shrink-0">
        {isRecommended && (
          <div className="relative mb-1">
            <div className="absolute -top-1 -left-1 w-5 h-5 bg-amber-400 rounded-full animate-ping opacity-30" />
            <Star className="w-4 h-4 text-amber-500 relative z-10" />
          </div>
        )}
        <div
          title={cfg.label}
          className={`w-9 h-9 rounded-xl flex items-center justify-center border-2 transition-all ${
            isLocked ? 'bg-gray-100 border-gray-200' : 'bg-white border-brand-200 shadow-sm'
          } ${isRecommended ? 'ring-2 ring-amber-300 ring-offset-2' : ''}`}
        >
          {statusIcon}
        </div>
        {!isLast && (
          <div className={`w-0.5 flex-1 min-h-[24px] my-1 transition-colors ${
            node.status === 'mastered' ? 'bg-green-300' : 'bg-gray-200'
          }`} />
        )}
      </div>

      {/* 内容 — 点击跳转资源 */}
      <div
        onClick={handleNodeClick}
        className={`flex-1 rounded-xl border p-4 mb-3 transition-all duration-200 ${cfg.bg} ${
          isLocked ? 'opacity-70' : 'cursor-pointer hover:shadow-md hover:border-gray-300'
        }`}
      >
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
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
              {/* 状态标记（只读，不可手动切换） */}
              <span
                className={`ml-auto text-[10px] font-semibold px-2 py-0.5 rounded-md border ${
                  isLocked ? 'text-gray-300 border-gray-100' :
                  node.status === 'mastered' ? 'text-green-600 border-green-200 bg-green-50' :
                  node.status === 'in_progress' ? 'text-brand-600 border-brand-200 bg-brand-50' :
                  'text-gray-400 border-gray-200 bg-white'
                }`}
              >
                {cfg.label}
              </span>
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
 * 阶段状态计算
 * =================================================================== */
function getStageStatus(stage: LearningStage): StageStatus {
  const counts = { mastered: 0, inProgress: 0, available: 0, locked: 0 };
  stage.nodes.forEach((n) => {
    if (n.status === 'mastered') counts.mastered++;
    else if (n.status === 'in_progress') counts.inProgress++;
    else if (n.status === 'available') counts.available++;
    else counts.locked++;
  });
  if (counts.mastered === stage.nodes.length) return 'completed';
  if (counts.inProgress > 0 || counts.mastered > 0) return 'in_progress';
  return 'not_started';
}

/** 阶段状态展示配置 */
const STAGE_STATUS_CONFIG: Record<StageStatus, { icon: any; label: string; bg: string; iconBg: string; iconColor: string }> = {
  not_started:  { icon: Circle,      label: '未开始',  bg: 'bg-gray-50 border-gray-100',              iconBg: 'bg-gray-50',   iconColor: 'text-gray-300' },
  in_progress:  { icon: Play,        label: '学习中',  bg: 'bg-brand-50/60 border-brand-100',         iconBg: 'bg-brand-50',  iconColor: 'text-brand-500' },
  completed:    { icon: CheckCircle,  label: '已完成',  bg: 'bg-green-50/60 border-green-100',          iconBg: 'bg-green-50',  iconColor: 'text-green-500' },
};

/* ===================================================================
 * 阶段组件（增强版）
 * =================================================================== */
function StageSection({ stage, defaultExpanded, onStatusChange, onCompleteStage, onViewResources }: {
  stage: LearningStage;
  defaultExpanded: boolean;
  onStatusChange: (nodeId: string, status: PathNodeStatus) => void;
  onCompleteStage: (stageId: string) => void;
  onViewResources: (stageId: string) => void;
}) {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(defaultExpanded);
  const completed = stage.nodes.filter((n) => n.status === 'mastered').length;
  const progress = Math.round((stage.nodes.length > 0 ? (completed / stage.nodes.length) * 100 : 0));
  const status = getStageStatus(stage);
  const statusCfg = STAGE_STATUS_CONFIG[status];

  // 找到推荐起点（第一个 available 或 in_progress 的节点）
  const recommendedIdx = stage.nodes.findIndex((n) => n.status === 'available' || n.status === 'in_progress');
  const allDone = status === 'completed';

  return (
    <div className={`mb-6 rounded-2xl border transition-all ${statusCfg.bg}`}>
      {/* 阶段头部（可点击展开） */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-5 hover:bg-white/50 transition-all group"
      >
        <div className="flex items-center gap-4 min-w-0 flex-1">
          {/* 阶段图标 */}
          <div className={`w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 ${statusCfg.iconBg}`}>
            <statusCfg.icon className={`w-5.5 h-5.5 ${statusCfg.iconColor}`} />
          </div>

          <div className="text-left flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">
                阶段 {stage.order}
              </span>
              {/* 阶段状态标签 */}
              <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${
                status === 'completed' ? 'bg-green-100 text-green-700' :
                status === 'in_progress' ? 'bg-brand-100 text-brand-700' :
                'bg-gray-100 text-gray-500'
              }`}>
                {statusCfg.label}
              </span>
              {/* 进度百分比 */}
              <span className={`text-[10px] font-semibold ${
                progress === 100 ? 'text-green-500' : progress > 0 ? 'text-brand-500' : 'text-gray-400'
              }`}>
                {completed}/{stage.nodes.length} 知识点
              </span>
            </div>
            <h3 className="text-base font-bold text-gray-900 mt-1">{stage.title}</h3>
            <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{stage.objective || stage.description}</p>

            {/* 阶段摘要信息条 */}
            <div className="flex flex-wrap items-center gap-3 mt-2 text-[10px] text-gray-400">
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                约 {stage.estimatedDays} 天
              </span>
              <span className="flex items-center gap-1">
                <ListChecks className="w-3 h-3" />
                {stage.tasks?.length || stage.nodes.length} 个学习任务
              </span>
              {stage.resourceTypes && stage.resourceTypes.length > 0 && (
                <span className="flex items-center gap-1">
                  <Layers className="w-3 h-3" />
                  {stage.resourceTypes.map((rt) => RESOURCE_TYPE_LABELS[rt] || rt).join('、')}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 flex-shrink-0 ml-4">
          <div className="w-8 h-8 rounded-lg bg-white/80 flex items-center justify-center transition-transform"
            style={{ transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)' }}>
            <ChevronDown className="w-4 h-4 text-gray-400" />
          </div>
        </div>
      </button>

      {/* 展开内容 */}
      {expanded && (
        <div className="px-5 pb-5">
          {/* ===== 阶段详情信息卡 ===== */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
            {/* 学习目标 */}
            {stage.objective && (
              <div className="p-3 bg-white/80 rounded-xl border border-gray-100">
                <div className="flex items-center gap-2 mb-1.5">
                  <Flag className="w-3.5 h-3.5 text-brand-500" />
                  <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">学习目标</span>
                </div>
                <p className="text-xs text-gray-700 leading-relaxed">{stage.objective}</p>
              </div>
            )}

            {/* 学习任务列表 */}
            {stage.tasks && stage.tasks.length > 0 && (
              <div className="p-3 bg-white/80 rounded-xl border border-gray-100">
                <div className="flex items-center gap-2 mb-1.5">
                  <ListChecks className="w-3.5 h-3.5 text-emerald-500" />
                  <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">学习任务</span>
                </div>
                <ul className="space-y-1">
                  {stage.tasks.map((task, ti) => (
                    <li key={ti} className="text-xs text-gray-600 flex items-start gap-1.5">
                      <span className="text-emerald-400 mt-0.5">•</span>
                      {task}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* 推荐资源类型 */}
            {stage.resourceTypes && stage.resourceTypes.length > 0 && (
              <div className="p-3 bg-white/80 rounded-xl border border-gray-100">
                <div className="flex items-center gap-2 mb-1.5">
                  <BookOpen className="w-3.5 h-3.5 text-purple-500" />
                  <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">推荐资源类型</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {stage.resourceTypes.map((rt) => (
                    <span key={rt} className="px-2 py-1 bg-purple-50 text-purple-600 rounded-md text-[10px] font-medium border border-purple-100">
                      {RESOURCE_TYPE_LABELS[rt] || rt}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* 排序理由 */}
            {stage.orderingReason && (
              <div className="p-3 bg-white/80 rounded-xl border border-gray-100">
                <div className="flex items-center gap-2 mb-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                  <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">排序理由</span>
                </div>
                <p className="text-xs text-gray-600 leading-relaxed">{stage.orderingReason}</p>
              </div>
            )}
          </div>

          {/* ===== 操作按钮 ===== */}
          <div className="flex flex-wrap items-center gap-2 mb-4">
            {/* 查看本阶段资源 */}
            <button
              onClick={(e) => { e.stopPropagation(); onViewResources(stage.id); }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-brand-500 text-white rounded-lg text-[11px] font-semibold hover:bg-brand-600 transition-all shadow-sm"
            >
              <BookOpen className="w-3.5 h-3.5" />
              查看阶段资源
            </button>

            {/* 完成阶段 */}
            {!allDone && (
              <button
                onClick={(e) => { e.stopPropagation(); onCompleteStage(stage.id); }}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-green-500 text-white rounded-lg text-[11px] font-semibold hover:bg-green-600 transition-all shadow-sm"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                标记阶段完成
              </button>
            )}

            {/* 进度条 */}
            <div className="flex-1 min-w-[100px] ml-auto">
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-[9px] text-gray-400">阶段进度</span>
                <span className="text-[9px] font-semibold text-gray-500">{progress}%</span>
              </div>
              <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-700 ${
                    progress >= 100 ? 'bg-green-500' : progress > 0 ? 'bg-brand-500' : 'bg-gray-200'
                  }`}
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          </div>

          {/* ===== 知识点节点列表 ===== */}
          <div className="pl-2">
            {stage.nodes.map((node, i) => (
              <NodeCard
                key={node.id}
                node={node}
                isLast={i === stage.nodes.length - 1}
                isRecommended={i === recommendedIdx}
                onStatusChange={onStatusChange}
              />
            ))}
          </div>
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
  const { path, loading, error, fetchPath, updateNodeStatus } = useLearningPath();
  const dataVersion = useChatStore((state) => state.dataVersion);
  const subjectId = useSubjectStore((s) => s.activeSubject?.id);

  // —— 完成阶段：标记所有未完成节点为 mastered + 记录学习事件 ——
  const handleCompleteStage = async (stageId: string) => {
    if (!path) return;
    const stage = path.stages.find((s) => s.id === stageId);
    if (!stage) return;
    stage.nodes.forEach((node) => {
      if (node.status !== 'mastered') {
        updateNodeStatus(node.id, 'mastered');
      }
    });
    await logStudyEvent({
      event: 'node_progress',
      sessionId: useChatStore.getState().currentSessionId,
      metadata: {
        stageId,
        stageTitle: stage.title,
        completedNodes: stage.nodes.length,
        action: 'complete_stage',
        subjectId,
      },
    });
  };

  // —— 跳转到资源库并筛选当前阶段 ——
  const handleViewResources = (stageId: string) => {
    navigate(`/resources?relatedStageId=${stageId}`);
  };

  // —— Loading（首次无数据） ——
  if (loading && !path) return <PageLoading text="加载学习路径..." />;

  // —— Error（首次无数据） ——
  if (error && !path) {
    return (
      <PageError
        title="路径加载失败"
        description={error}
        onRetry={fetchPath}
        onGoChat={() => navigate('/chat')}
      />
    );
  }

  // —— Empty（从未生成过路径） ——
  if (!path) {
    return (
      <PageEmpty
        icon={<GitFork className="w-8 h-8" />}
        title="暂无学习路径"
        description="通过对话让系统为你规划学习路径"
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

  // —— Empty（空阶段或 source 为 none） ——
  if (!path.stages || path.stages.length === 0 || path.source === 'none') {
    return (
      <PageEmpty
        icon={<GitFork className="w-8 h-8" />}
        title="暂无学习路径"
        description={'当前会话还没有真实生成的学习路径。请先在 AI 对话中补充学习目标、基础和时间安排，然后说\u201C开始生成学习方案\u201D。'}
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

  const isFallback = path.source === 'system_inferred';

  // 统计阶段状态
  const stageStatuses = path.stages.map((s) => getStageStatus(s));
  const completedStages = stageStatuses.filter((s) => s === 'completed').length;
  const inProgressStages = stageStatuses.filter((s) => s === 'in_progress').length;

  // 找到当前应该开始/继续的阶段
  const currentStageIdx = path.stages.findIndex((s) =>
    s.nodes.some((n) => n.status === 'in_progress' || n.status === 'available')
  );
  const firstAvailableStage = currentStageIdx >= 0 ? currentStageIdx : 0;

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 md:py-8 relative">
      {/* ========== 刷新遮罩 ========== */}
      {loading && path && <RefreshOverlay />}

      {/* ========== Fallback 提示 ========== */}
      {isFallback && !loading && (
        <FallbackBanner message="当前学习路径基于系统兜底规则生成，可能不够精准。建议在 AI 对话中补充学习目标以获取个性化路径。" />
      )}

      {/* ========== 错误横幅（已有路径但刷新失败） ========== */}
      {error && path && (
        <div className="mb-6 p-3 bg-red-50 border border-red-100 rounded-xl flex items-center gap-2 text-xs text-red-600">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          {error}
          <button onClick={fetchPath} className="ml-auto flex items-center gap-1 px-2 py-1 bg-red-100 rounded-lg hover:bg-red-200 transition-colors">
            <RefreshCw className="w-3 h-3" /> 重试
          </button>
        </div>
      )}

      {/* ========== 头部 ========== */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-2">
          <Target className="w-5 h-5 text-brand-500" />
          <span className="text-xs font-bold text-brand-500 uppercase tracking-wider">Study Workflow Path</span>
        </div>
        <h1 className="text-2xl md:text-3xl font-extrabold text-gray-900 mb-1">{path.title}</h1>
        <p className="text-sm text-gray-500 mb-2">{path.description}</p>
        <div className="flex flex-wrap items-center gap-3 text-xs text-gray-400 mb-2">
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            路径生成：{timeAgo(path.createdAt)}
          </span>
          <span className="flex items-center gap-1 text-brand-600">
            <RefreshCw className="w-3 h-3" />
            {dataVersion > 0 ? '基于最新对话' : '基于初始画像'}
          </span>
          <SourceTag source={path.source} />
        </div>

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

          {/* 数据指标 — 增加"进行中" */}
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
              <div className="text-sm font-bold text-green-600">{completedStages}</div>
              <div className="text-[10px] text-green-500">已完成</div>
            </div>
            <div className="text-center px-4 py-2 bg-brand-50 rounded-xl">
              <div className="text-sm font-bold text-brand-600">{inProgressStages}</div>
              <div className="text-[10px] text-brand-500">进行中</div>
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
            onStatusChange={updateNodeStatus}
            onCompleteStage={handleCompleteStage}
            onViewResources={handleViewResources}
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
        <div className="flex items-center justify-center gap-2 mt-3">
          <SourceBadge source="agent_generated" size="xs" />
          <span className="text-[10px] text-gray-300">路径由 PlannerAgent 智能体基于当前画像生成</span>
        </div>
      </div>
    </div>
  );
}
