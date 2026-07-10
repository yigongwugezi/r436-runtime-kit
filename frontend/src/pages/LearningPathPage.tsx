// @ts-nocheck
import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
function focusChatInput() { document.querySelector<HTMLTextAreaElement>('[data-chat-input]')?.focus(); }
import { useLearningPath } from '../hooks/useLearningPath';
import { PlayCircle, BookOpen, Code2, FileCheck, Lock, CheckCircle2, Circle, Loader2, ChevronRight, Zap, Target, ArrowLeft, FileText, Brain, Calendar, ExternalLink, Clock } from 'lucide-react';
import { PageLoading, PageEmpty, PageError } from '../components/common/PageState';
import { getCurrentLearner } from '../store/authStore';

const statusStyle: Record<string, { bg: string; border: string; text: string; icon: string }> = {
  mastered: { bg: 'bg-success-50', border: 'border-success-200', text: 'text-success-700', icon: 'text-success-500' },
  completed: { bg: 'bg-success-50', border: 'border-success-200', text: 'text-success-700', icon: 'text-success-500' },
  in_progress: { bg: 'bg-primary-50', border: 'border-primary-300', text: 'text-primary-700', icon: 'text-primary-500' },
  available: { bg: 'bg-surface-50', border: 'border-surface-200', text: 'text-surface-700', icon: 'text-surface-400' },
  locked: { bg: 'bg-surface-100', border: 'border-surface-200', text: 'text-surface-400', icon: 'text-surface-300' },
};
const _def = { bg: 'bg-surface-50', border: 'border-surface-200', text: 'text-surface-700', icon: 'text-surface-400' };

const nodeBorder: Record<string, string> = {
  mastered: 'bg-success-50 border-success-200',
  in_progress: 'bg-primary-50 border-primary-200',
  available: 'bg-surface-50 border-surface-200',
  locked: 'bg-surface-100 border-surface-200',
};

function truncateTitle(title: string, maxLen: number = 6): string {
  if (!title) return '';
  return title.length > maxLen ? title.slice(0, maxLen) + '…' : title;
}

const nodeStatusIcon = (status: string, size: number = 16) => {
  if (status === 'mastered' || status === 'completed') return <CheckCircle2 size={size} />;
  if (status === 'in_progress') return <Loader2 size={size} className="animate-spin" />;
  return <Circle size={size - 2} />;
};

const nodeStatusColor = (status: string) => {
  if (status === 'mastered' || status === 'completed') return 'bg-success-100 text-success-600';
  if (status === 'in_progress') return 'bg-primary-100 text-primary-600';
  if (status === 'locked') return 'bg-surface-100 text-surface-400';
  return 'bg-surface-50 text-surface-400';
};

// ====== 布局常量 ======
const GRAPH_MIN_Y = 150;
const GRAPH_MAX_Y = 200;
const AXIS_TOP = 320;
const AXIS_PAD = 48;
const NODE_BOX_HEIGHT = 56;

export default function LearningPathPage() {
  const nav = useNavigate();
  // Chat panel always visible in 3-col layout (§2.5)
  const { path, loading, error, fetchPath } = useLearningPath();

  const stages = path?.stages || [];
  const allNodes = stages.flatMap(s => s.nodes || []);
  const totalNodes = allNodes.length;
  const masteredNodes = allNodes.filter(n => n.status === 'mastered' || n.status === 'completed').length;
  const progress = path?.overallProgress ?? (totalNodes > 0 ? Math.round((masteredNodes / totalNodes) * 100) : 0);
  const estimatedDays = path?.estimatedDays || 14;
  const isParent = getCurrentLearner()?.role === 'parent';
  const maxNodesInStage = Math.max(...stages.map(s => s.nodes?.length || 0), 1);

  // ====== 核心算法 ======
  const { stageLayouts, totalDays, dayToPixelX } = useMemo(() => {
    const fallbackDays = Math.ceil(estimatedDays / Math.max(stages.length, 1));

    let cumDays = 0;
    const stageData = stages.map((s, i) => {
      const days = s.estimatedDays || fallbackDays;
      cumDays += days;
      return {
        stage: s,
        index: i,
        days,
        endDay: cumDays,
        startDay: cumDays - days + 1,
        nodeCount: s.nodes?.length || 1,
      };
    });

    const totalDays = cumDays || estimatedDays;

    const layouts = stageData.map((data, i) => {
      const { startDay, endDay, nodeCount } = data;
      const xRatio = totalDays > 1 ? (startDay - 1) / (totalDays - 1) : 0.5;
      const wave = Math.sin((i / Math.max(stages.length - 1, 1)) * Math.PI * 1.2);
      const cy = GRAPH_MIN_Y + (GRAPH_MAX_Y - GRAPH_MIN_Y) * ((1 - wave) / 2);
      const scale = 0.85 + (nodeCount / maxNodesInStage) * 0.3;

      return {
        ...data,
        xRatio,
        cy,
        scale,
      };
    });

    const dayToPixelX = (day: number, graphWidth: number) => {
      if (totalDays <= 1) return AXIS_PAD + graphWidth * 0.5;
      const ratio = (day - 1) / (totalDays - 1);
      return AXIS_PAD + ratio * (graphWidth - AXIS_PAD * 2);
    };

    return { stageLayouts: layouts, totalDays, dayToPixelX };
  }, [stages, estimatedDays, maxNodesInStage]);

  // ====== 容器宽度 ======
  const graphRef = React.useRef<HTMLDivElement>(null);
  const [graphW, setGraphW] = useState(800);

  useEffect(() => {
    const el = graphRef.current;
    if (!el) return;
    const getWidth = () => {
      if (el.offsetWidth > 0) setGraphW(el.offsetWidth);
    };
    getWidth();
    const observer = new ResizeObserver(getWidth);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const ratioToLeftPct = useCallback((ratio: number) => {
    if (graphW <= 0) return '50%';
    const px = AXIS_PAD + ratio * (graphW - AXIS_PAD * 2);
    return `${(px / graphW) * 100}%`;
  }, [graphW]);

  const formatDuration = (minutes: number) => {
    if (!minutes || minutes <= 0) return '0分钟';
    if (minutes < 60) return `${minutes}分钟`;
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m > 0 ? `${h}h${m}m` : `${h}h`;
  };

  const inProgressStage = stages.find(s => s.nodes?.some(n => n.status === 'in_progress'));
  const [activeStageId, setActiveStageId] = useState<string | null>(null);
  const [activeNodeId, setActiveNodeId] = useState<string | null>(null);

  const activeStage = stages.find(s => s.id === activeStageId);
  const activeNode = activeStage?.nodes?.find(n => n.id === activeNodeId);

  const handleStageClick = useCallback((stageId: string) => {
    setActiveStageId(stageId);
    setActiveNodeId(null);
  }, []);

  const handleBackToGraph = useCallback(() => {
    setActiveStageId(null);
    setActiveNodeId(null);
  }, []);

  const handleNodeClick = useCallback((nodeId: string) => {
    nav(`/resources?taskId=${encodeURIComponent(nodeId)}`);
  }, [nav]);

  const ss = (k: string) => statusStyle[k] || _def;
  const nb = (k: string) => nodeBorder[k] || 'bg-surface-50 border-surface-200';

  if (loading) return <PageLoading text="加载学习路径中…" />;
  if (error && stages.length === 0) return <PageError title="学习路径加载失败" description={error} onRetry={fetchPath} />;

  if (!path || stages.length === 0) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div className="flex items-center justify-between">
          <div><h2 className="font-display text-2xl font-bold text-surface-800">学习路径</h2><p className="text-surface-500 mt-1">基于你的学习画像智能规划的进阶路线</p></div>
        </div>
        <PageEmpty
          icon={<Target size={40} className="text-surface-300" />}
          title="尚未生成学习路径"
          description={<span>在聊天中告诉 AI 你的学习目标，例如：<br /><span className="text-primary-600 font-medium">"我想用两周时间入门深度学习"</span></span>}
          action={<button onClick={() => focusChatInput()} className="mt-4 px-5 py-2.5 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 transition-colors">去对话生成</button>}
        />
      </div>
    );
  }

  const isDetailView = !!activeStageId;

  return (
    <div className="animate-fade-in flex-1 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-5 flex-shrink-0">
        <div>
          <h2 className="font-display text-2xl font-bold text-surface-800">学习路径</h2>
          <p className="text-surface-500 mt-1">基于你的学习画像智能规划的进阶路线</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 px-4 py-2 bg-surface-50 rounded-xl">
            <Target size={18} className="text-primary-500" />
            <span className="text-sm font-medium text-surface-600">进度: {progress}%</span>
          </div>
          {!isParent && (
          <button onClick={() => focusChatInput()} className="flex items-center gap-2 px-5 py-2.5 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 transition-colors">
            <Zap size={18} />完善路径
          </button>
          )}
        </div>
      </div>

      {/* Overview card */}
      <div className="bg-white rounded-2xl p-5 shadow-soft mb-4 flex-shrink-0">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="font-display text-lg font-semibold text-surface-800">{path.title}</h3>
            <p className="text-surface-500 text-sm mt-0.5">{path.description || '个性化学习路径规划'}</p>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 bg-accent-50 rounded-lg">
            <Calendar size={14} className="text-accent-500" />
            <span className="text-sm text-accent-700 font-medium">预计 {totalDays} 天</span>
          </div>
        </div>
        <div className="relative h-2.5 bg-surface-100 rounded-full overflow-hidden">
          <div className="absolute inset-y-0 left-0 bg-gradient-to-r from-primary-500 to-accent-500 rounded-full transition-all duration-1000" style={{ width: `${progress}%` }} />
        </div>
        <div className="flex items-center justify-between mt-2 text-sm">
          <span className="text-surface-500">已完成 {masteredNodes} 个知识点</span>
          <span className="text-surface-500">共 {totalNodes} 个知识点 · {stages.length} 个阶段</span>
        </div>
      </div>

      {/* Main content - 两栏，撑满剩余高度 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 flex-1 min-h-0">
        {/* 左侧：学习节点图 */}
        <div className="lg:col-span-2 bg-white rounded-2xl p-6 shadow-soft flex flex-col min-h-0">
          {isDetailView ? (
            <div className="animate-fade-in flex-1 overflow-auto">
              <button onClick={handleBackToGraph} className="flex items-center gap-1.5 text-sm text-surface-500 hover:text-primary-600 transition-colors mb-4">
                <ArrowLeft size={16} />
                <span>返回学习节点</span>
              </button>

              <div className="mb-4">
                <h3 className="font-display text-lg font-semibold text-surface-800 mb-1">{activeStage?.title}</h3>
                <div className="flex items-center gap-3 text-sm text-surface-500">
                  {activeStage?.objective && <span>{activeStage.objective}</span>}
                  {activeStage?.estimatedDays && (
                    <span className="flex items-center gap-1 text-xs text-surface-400">
                      <Calendar size={12} />预计 {activeStage.estimatedDays} 天
                    </span>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 gap-2.5">
                {activeStage?.nodes?.map((node: any, ni: number) => {
                  const nc = nb(node.status || 'available');
                  const nStatus = node.status || 'available';
                  const resourceCount = node.resources?.length || 0;
                  const essentialCount = node.resources?.filter((r: any) => r.essential)?.length || 0;
                  return (
                    <div
                      key={node.id}
                      onClick={() => handleNodeClick(node.id)}
                      className={`flex items-center gap-3 p-3.5 rounded-xl cursor-pointer transition-all border ${nc} hover:shadow-elevated hover:border-primary-300 group`}
                    >
                      <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${nodeStatusColor(nStatus)}`}>
                        {nodeStatusIcon(nStatus, 18)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-surface-400 font-medium w-4 text-right">{ni + 1}</span>
                          <p className="text-sm font-semibold text-surface-800 truncate group-hover:text-primary-600 transition-colors">{node.topic}</p>
                          {node.isKeyPoint && (
                            <span className="text-[10px] px-1.5 py-0.5 bg-warning-100 text-warning-700 rounded-full font-medium flex-shrink-0">重点</span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 mt-1 text-[10px] text-surface-400">
                          {resourceCount > 0 ? (
                            <>
                              <span className="flex items-center gap-1"><BookOpen size={10} />{resourceCount} 个资源</span>
                              {essentialCount > 0 && <span className="text-error-500">{essentialCount} 个必学</span>}
                            </>
                          ) : (
                            <span className="text-surface-300 italic">暂无资源</span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <div className="w-14 h-1.5 bg-surface-100 rounded-full overflow-hidden">
                          <div className={`h-full rounded-full ${(node.mastery || 0) >= 80 ? 'bg-success-500' : (node.mastery || 0) >= 40 ? 'bg-primary-500' : 'bg-surface-300'}`} style={{ width: `${node.mastery || 0}%` }} />
                        </div>
                        <span className="text-xs font-medium text-surface-500 w-7 text-right tabular-nums">{node.mastery || 0}%</span>
                        <ExternalLink size={14} className="text-surface-300 group-hover:text-primary-400 transition-colors" />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col min-h-0">
              <h3 className="font-display text-lg font-semibold text-surface-800 mb-3 flex-shrink-0">学习节点 · 时间规划</h3>
              <div className="relative flex-1" ref={graphRef}>
                <svg className="absolute inset-0 w-full h-full pointer-events-none" style={{ zIndex: 0 }}>
                  {stageLayouts.map((layout, i) => {
                    if (i >= stageLayouts.length - 1) return null;
                    const sx = dayToPixelX(layout.startDay, graphW);
                    const sy = layout.cy;
                    const nextLayout = stageLayouts[i + 1];
                    const tx = dayToPixelX(nextLayout.startDay, graphW);
                    const ty = nextLayout.cy;
                    const locked = nextLayout.stage.nodes?.every(n => n.status === 'locked');
                    const midX = (sx + tx) / 2;
                    const d = `M${sx},${sy} C${midX},${sy} ${midX},${ty} ${tx},${ty}`;
                    return <path key={`conn-${layout.stage.id}`} d={d} fill="none" stroke={locked ? '#e2e8f0' : '#93c5fd'} strokeWidth="2.5" strokeDasharray="5,5" />;
                  })}

                  {stageLayouts.map((layout) => {
                    const cx = dayToPixelX(layout.startDay, graphW);
                    return (
                      <line key={`drop-${layout.stage.id}`} x1={cx} y1={layout.cy + NODE_BOX_HEIGHT / 2 + 40} x2={cx} y2={AXIS_TOP} stroke="#cbd5e1" strokeWidth="1.5" strokeDasharray="4,4" opacity="0.7" />
                    );
                  })}

                  {(() => {
                    const axStart = dayToPixelX(1, graphW);
                    const axEnd = dayToPixelX(totalDays, graphW);
                    const stageStartDays = new Set(stageLayouts.map(l => l.startDay));
                    const stageEndDays = new Set(stageLayouts.map(l => l.endDay));
                    const showAllLabels = totalDays <= 20;

                    return (
                      <>
                        <line x1={axStart} y1={AXIS_TOP} x2={axEnd} y2={AXIS_TOP} stroke="#cbd5e1" strokeWidth="2" />
                        <circle cx={axStart} cy={AXIS_TOP} r="4" fill="#64748b" />
                        <text x={axStart - 8} y={AXIS_TOP + 18} textAnchor="end" fill="#64748b" fontSize="11" fontWeight={600}>开始</text>
                        <polygon points={`${axEnd},${AXIS_TOP} ${axEnd - 10},${AXIS_TOP - 5} ${axEnd - 10},${AXIS_TOP + 5}`} fill="#cbd5e1" />
                        <text x={axEnd + 8} y={AXIS_TOP + 18} textAnchor="start" fill="#64748b" fontSize="11" fontWeight={600}>完成</text>

                        {Array.from({ length: totalDays }, (_, idx) => {
                          const day = idx + 1;
                          const dx = dayToPixelX(day, graphW);
                          const isStageStart = stageStartDays.has(day);
                          const isStageEnd = stageEndDays.has(day);
                          const isImportant = isStageStart || isStageEnd;

                          return (
                            <g key={`tick-${day}`}>
                              <line x1={dx} y1={AXIS_TOP - (isImportant ? 8 : 5)} x2={dx} y2={AXIS_TOP + (isImportant ? 8 : 5)} stroke={isStageStart ? '#3b82f6' : isStageEnd ? '#94a3b8' : '#e2e8f0'} strokeWidth={isImportant ? 2 : 1} />
                              {isStageStart && (
                                <>
                                  <circle cx={dx} cy={AXIS_TOP} r="5" fill="#3b82f6" stroke="#fff" strokeWidth="2" />
                                  <text x={dx} y={AXIS_TOP + 22} textAnchor="middle" fill="#3b82f6" fontSize="10" fontWeight={700}>D{day}</text>
                                </>
                              )}
                              {isStageEnd && !isStageStart && (
                                <>
                                  <circle cx={dx} cy={AXIS_TOP} r="3.5" fill="#94a3b8" stroke="#fff" strokeWidth="1.5" />
                                  <text x={dx} y={AXIS_TOP + 18} textAnchor="middle" fill="#94a3b8" fontSize="9">D{day}</text>
                                </>
                              )}
                              {!isImportant && showAllLabels && day % 3 === 0 && (
                                <text x={dx} y={AXIS_TOP + 15} textAnchor="middle" fill="#cbd5e1" fontSize="9">{day}</text>
                              )}
                            </g>
                          );
                        })}

                        {stageLayouts.map((layout, i) => {
                          if (layout.startDay === layout.endDay) return null;
                          const sx = dayToPixelX(layout.startDay, graphW);
                          const ex = dayToPixelX(layout.endDay, graphW);
                          const midX = (sx + ex) / 2;
                          return (
                            <g key={`range-${i}`}>
                              <rect x={sx} y={AXIS_TOP - 35} width={ex - sx} height="20" rx="4" fill="#f1f5f9" opacity="0.8" />
                              <text x={midX} y={AXIS_TOP - 21} textAnchor="middle" fill="#64748b" fontSize="10" fontWeight={500}>{truncateTitle(layout.stage.title, 8)}</text>
                            </g>
                          );
                        })}
                      </>
                    );
                  })()}

                  {(() => {
                    const axStart = dayToPixelX(1, graphW);
                    let progressEndDay = 0;
                    let isInProgress = false;
                    for (let i = 0; i < stageLayouts.length; i++) {
                      const layout = stageLayouts[i];
                      const nodes = layout.stage.nodes || [];
                      const allDone = nodes.every(n => n.status === 'mastered' || n.status === 'completed');
                      const hasActive = nodes.some(n => n.status === 'in_progress');
                      if (allDone) { progressEndDay = layout.endDay; }
                      else if (hasActive) { progressEndDay = layout.startDay; isInProgress = true; break; }
                      else { break; }
                    }
                    if (progressEndDay === 0) return null;
                    const endX = dayToPixelX(progressEndDay, graphW);
                    return <line x1={axStart} y1={AXIS_TOP} x2={endX} y2={AXIS_TOP} stroke={isInProgress ? '#3b82f6' : '#22c55e'} strokeWidth="3" strokeLinecap="round" opacity="0.8" />;
                  })()}
                </svg>

                {/* HTML层：学习节点 */}
                {stageLayouts.map((layout) => {
                  const { stage, startDay, endDay, xRatio, cy, scale } = layout;
                  const hasActive = stage.nodes?.some(n => n.status === 'in_progress');
                  const allMastered = stage.nodes?.every(n => n.status === 'mastered' || n.status === 'completed');
                  const allLocked = stage.nodes?.every(n => n.status === 'locked');
                  const stageDuration = stage.nodes?.reduce((sum: number, n: any) => sum + (n.duration || 0), 0) || 0;
                  const stageStatus = allMastered ? 'mastered' : hasActive ? 'in_progress' : allLocked ? 'locked' : 'available';
                  const _s = ss(stageStatus);
                  const iconSize = Math.round(24 * scale);
                  const boxSize = Math.round(NODE_BOX_HEIGHT * scale);
                  return (
                    <div key={stage.id} className="absolute transform -translate-x-1/2 -translate-y-1/2" style={{ left: ratioToLeftPct(xRatio), top: cy, zIndex: 10 }}>
                      <button onClick={() => handleStageClick(stage.id)} disabled={allLocked} className={`relative flex flex-col items-center transition-all ${allLocked ? 'cursor-not-allowed' : 'cursor-pointer group'}`}>
                        <div className={`rounded-2xl ${_s.bg} border-2 ${_s.border} flex items-center justify-center transition-all group-hover:scale-110 group-hover:shadow-md`} style={{ width: boxSize, height: boxSize }}>
                          {allMastered && <CheckCircle2 size={iconSize} className={_s.icon} />}
                          {hasActive && !allMastered && <Loader2 size={iconSize} className={`${_s.icon} animate-spin`} />}
                          {!hasActive && !allMastered && !allLocked && <Circle size={iconSize} className={_s.icon} />}
                          {allLocked && <Lock size={iconSize} className={_s.icon} />}
                        </div>
                        <div className="mt-1.5 px-2.5 py-1 rounded-lg text-center bg-white shadow-sm border border-surface-100 relative group/title max-w-[90px] hover:max-w-[280px] transition-all duration-300 hover:z-20 overflow-hidden">
                          <p className={`text-[11px] font-semibold whitespace-nowrap ${allLocked ? 'text-surface-400' : 'text-surface-700'}`}>
                            {stage.title}
                          </p>
                          {/* 右侧渐变虚化遮罩 - hover时消失 */}
                          <div className="absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-white via-white/70 to-transparent pointer-events-none rounded-r-lg group-hover/title:opacity-0 transition-opacity duration-200" />
                        </div>
                        <div className="flex items-center gap-1 mt-0.5">
                          <Calendar size={9} className="text-surface-400" />
                          <span className={`text-[9px] font-medium ${allLocked ? 'text-surface-300' : 'text-surface-500'}`}>{startDay === endDay ? `第${startDay}天` : `第${startDay}-${endDay}天`}</span>
                        </div>
                        <div className="flex items-center gap-1 mt-0.5">
                          <Clock size={9} className="text-surface-400" />
                          <span className={`text-[9px] font-medium ${allLocked ? 'text-surface-300' : 'text-surface-500'}`}>{formatDuration(stageDuration)}</span>
                        </div>
                        {hasActive && <div className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-primary-500 rounded-full flex items-center justify-center shadow-sm"><span className="text-[10px] text-white font-bold">{layout.index + 1}</span></div>}
                      </button>
                    </div>
                  );
                })}

                <div className="absolute" style={{ left: `${(AXIS_PAD / graphW) * 100}%`, top: AXIS_TOP + 30, zIndex: 5 }}>
                  <span className="text-[10px] text-surface-400">{stages.filter(s => s.nodes?.every(n => n.status === 'mastered' || n.status === 'completed')).length}/{stages.length} 阶段完成 · 共 {totalDays} 天</span>
                </div>
              </div>

              <div className="flex items-center gap-6 pt-3 border-t border-surface-100 flex-shrink-0">
                <div className="flex items-center gap-2"><CheckCircle2 size={14} className="text-success-500" /><span className="text-xs text-surface-600">已掌握</span></div>
                <div className="flex items-center gap-2"><Loader2 size={14} className="text-primary-500" /><span className="text-xs text-surface-600">进行中</span></div>
                <div className="flex items-center gap-2"><Circle size={14} className="text-surface-400" /><span className="text-xs text-surface-600">待解锁</span></div>
                <div className="flex items-center gap-2"><Lock size={14} className="text-surface-300" /><span className="text-xs text-surface-600">未解锁</span></div>
              </div>
            </div>
          )}
        </div>

        {/* 右侧：概览卡片 */}
        <div className="bg-white rounded-2xl p-6 shadow-soft flex flex-col justify-center">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4">学习概览</h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-surface-500">总体进度</span>
              <span className="text-sm font-semibold text-primary-600">{progress}%</span>
            </div>
            <div className="relative h-2 bg-surface-100 rounded-full overflow-hidden">
              <div className="absolute inset-y-0 left-0 bg-gradient-to-r from-primary-500 to-accent-500 rounded-full" style={{ width: `${progress}%` }} />
            </div>
            <div className="grid grid-cols-2 gap-3 mt-4">
              <div className="bg-surface-50 rounded-xl p-4 text-center">
                <p className="text-2xl font-bold text-surface-800">{stages.length}</p>
                <p className="text-xs text-surface-400 mt-1">学习阶段</p>
              </div>
              <div className="bg-surface-50 rounded-xl p-4 text-center">
                <p className="text-2xl font-bold text-surface-800">{totalNodes}</p>
                <p className="text-xs text-surface-400 mt-1">知识点</p>
              </div>
              <div className="bg-success-50 rounded-xl p-4 text-center">
                <p className="text-2xl font-bold text-success-600">{masteredNodes}</p>
                <p className="text-xs text-success-500 mt-1">已掌握</p>
              </div>
              <div className="bg-primary-50 rounded-xl p-4 text-center">
                <p className="text-2xl font-bold text-primary-600">{totalDays}</p>
                <p className="text-xs text-primary-500 mt-1">预计天数</p>
              </div>
            </div>
            <div className="mt-4 pt-4 border-t border-surface-100">
              <div className="flex items-center justify-between">
                <span className="text-sm text-surface-500 flex items-center gap-1.5">
                  <Clock size={14} className="text-primary-400" />
                  今日学习时长
                </span>
                <span className="text-lg font-bold text-primary-600">{formatDuration(path?.todayDuration || 0)}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}