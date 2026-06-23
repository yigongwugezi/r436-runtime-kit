import { useState, useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Clock, Eye, CheckCircle2, FileText, Code, MessageSquare,
  Target, BookOpen, ArrowRight, ExternalLink, History,
  ListFilter, ChevronDown, ChevronUp, LayoutGrid,
} from 'lucide-react';
import type { TimelineEvent } from '../types/timeline';
import { timeAgo } from '../utils/format';
import { PageLoading, PageEmpty } from '../components/common/PageState';
import { useLearningEvents } from '../hooks/useLearningEvents';
import TimelineSummaryCard from '../components/timeline/TimelineSummaryCard';
import TimelineEventDetail from '../components/timeline/TimelineEventDetail';

/* ===================================================================
 * 常量
 * =================================================================== */
const EVENT_TYPE_FILTERS = [
  { value: '',         label: '全部',    icon: ListFilter },
  { value: 'resource_view',     label: '查看资源', icon: Eye },
  { value: 'resource_complete', label: '完成资源', icon: CheckCircle2 },
  { value: 'quiz_result',       label: '测验',    icon: FileText },
  { value: 'practice_result',   label: '实践',    icon: Code },
  { value: 'feedback',          label: '反馈',    icon: MessageSquare },
  { value: 'stage_complete',    label: '阶段更新', icon: Target },
] as const;

const TIME_RANGE_FILTERS = [
  { value: '',    label: '全部' },
  { value: '1',   label: '今天' },
  { value: '7',   label: '最近 7 天' },
  { value: '30',  label: '最近 30 天' },
] as const;

const EVENT_ICON: Record<string, React.ReactNode> = {
  resource_view:     <Eye className="w-4 h-4" />,
  resource_complete: <CheckCircle2 className="w-4 h-4" />,
  quiz_result:       <FileText className="w-4 h-4" />,
  practice_result:   <Code className="w-4 h-4" />,
  feedback:          <MessageSquare className="w-4 h-4" />,
  stage_complete:    <Target className="w-4 h-4" />,
  node_progress:     <BookOpen className="w-4 h-4" />,
};

const EVENT_COLOR_BG: Record<string, string> = {
  resource_view:     'bg-blue-100 text-blue-600',
  resource_complete: 'bg-green-100 text-green-600',
  quiz_result:       'bg-amber-100 text-amber-600',
  practice_result:   'bg-cyan-100 text-cyan-600',
  feedback:          'bg-purple-100 text-purple-600',
  stage_complete:    'bg-rose-100 text-rose-600',
  node_progress:     'bg-gray-100 text-gray-500',
};

/* ===================================================================
 * TimelineItem — 支持展开详情
 * =================================================================== */
function TimelineItem({
  event,
  onNavigate,
  defaultExpanded,
}: {
  event: TimelineEvent;
  onNavigate: (resourceId: string, stageId: string) => void;
  defaultExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded ?? false);
  const stageTitle = event.metadata?.stageTitle as string | undefined;
  const nodeStatus = event.metadata?.status as string | undefined;

  let description = '';
  if (event.resourceTitle) {
    description = event.resourceTitle;
  } else if (event.relatedChapter) {
    description = `章节：${event.relatedChapter}`;
  } else if (stageTitle) {
    description = stageTitle;
  } else if (event.relatedStageId) {
    description = `阶段 ${event.relatedStageId.replace(/[^0-9]/g, '')}`;
  } else if (nodeStatus) {
    description = `节点状态：${nodeStatus === 'completed' ? '已完成' : nodeStatus === 'in_progress' ? '学习中' : '已解锁'}`;
  }

  // 摘要标签
  let detail = '';
  if (event.event === 'quiz_result' && event.metadata) {
    const correct = event.metadata.correct as number | undefined;
    const total = event.metadata.total as number | undefined;
    if (correct != null && total != null) detail = `${correct}/${total}`;
    const accuracy = event.metadata.accuracy as number | undefined;
    if (accuracy != null && !detail) detail = `${accuracy}%`;
  }
  if (event.event === 'feedback' && event.metadata) {
    const rating = event.metadata.rating as number | undefined;
    if (rating != null) detail = `${'⭐'.repeat(rating)}`;
  }

  const iconBg = EVENT_COLOR_BG[event.event] || 'bg-gray-100 text-gray-500';

  return (
    <div className="relative pb-4 group">
      <div
        className="flex gap-4 cursor-pointer rounded-xl transition-colors hover:bg-gray-50/50 -mx-2 px-2 py-1"
        onClick={() => setExpanded(!expanded)}
      >
        {/* 时间线竖线 — 使用伪元素替代 last:hidden */}
        <div className="relative flex flex-col items-center flex-shrink-0">
          <div className={`relative z-10 w-9 h-9 rounded-xl ${iconBg} flex items-center justify-center shadow-sm`}>
            {EVENT_ICON[event.event] || <History className="w-4 h-4" />}
          </div>
          {/* 展开/折叠图标 */}
          <div className="mt-0.5">
            {expanded ? (
              <ChevronUp className="w-3 h-3 text-gray-300" />
            ) : (
              <ChevronDown className="w-3 h-3 text-gray-300" />
            )}
          </div>
        </div>

        {/* 内容 */}
        <div className="flex-1 min-w-0 pt-0.5">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-sm font-semibold text-gray-800">{event.label}</p>
              {description && (
                <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{description}</p>
              )}
              {detail && (
                <span className="inline-block mt-1 px-2 py-0.5 rounded-md text-[10px] font-medium bg-gray-50 text-gray-500 border border-gray-100">
                  {detail}
                </span>
              )}
            </div>
            <span className="text-[10px] text-gray-400 whitespace-nowrap flex-shrink-0 mt-0.5">
              {timeAgo(event.timestamp)}
            </span>
          </div>

          {/* 跳转按钮（阻止冒泡以免触发展开） */}
          {(event.resourceId || event.relatedStageId) && (
            <div className="flex items-center gap-2 mt-2" onClick={(e) => e.stopPropagation()}>
              {event.resourceId && (
                <button
                  onClick={() => onNavigate(event.resourceId, '')}
                  className="inline-flex items-center gap-1 text-[10px] font-medium text-brand-500 hover:text-brand-600 transition-colors"
                >
                  <ExternalLink className="w-3 h-3" />
                  查看资源
                </button>
              )}
              {event.relatedStageId && (
                <button
                  onClick={() => onNavigate('', event.relatedStageId)}
                  className="inline-flex items-center gap-1 text-[10px] font-medium text-gray-400 hover:text-gray-600 transition-colors"
                >
                  <ArrowRight className="w-3 h-3" />
                  跳转阶段
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 展开详情面板 */}
      {expanded && <TimelineEventDetail event={event} />}
    </div>
  );
}

/* ===================================================================
 * 过滤器横条
 * =================================================================== */
function FilterBar({
  eventType,
  timeRange,
  onEventTypeChange,
  onTimeRangeChange,
}: {
  eventType: string;
  timeRange: string;
  onEventTypeChange: (v: string) => void;
  onTimeRangeChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 mb-6">
      {/* 事件类型筛选 */}
      <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-thin">
        <ListFilter className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
        <div className="flex gap-1 flex-nowrap">
          {EVENT_TYPE_FILTERS.map((f) => {
            const Icon = f.icon;
            const active = eventType === f.value;
            return (
              <button
                key={f.value}
                onClick={() => onEventTypeChange(f.value)}
                className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[10px] font-medium transition-all ${
                  active
                    ? 'bg-gray-900 text-white shadow-sm'
                    : 'bg-gray-50 text-gray-500 hover:bg-gray-100'
                }`}
              >
                <Icon className="w-3 h-3" />
                {f.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* 时间范围筛选 */}
      <div className="flex items-center gap-1 ml-auto">
        <Clock className="w-3 h-3 text-gray-400" />
        {TIME_RANGE_FILTERS.map((f) => {
          const active = timeRange === f.value;
          return (
            <button
              key={f.value}
              onClick={() => onTimeRangeChange(f.value)}
              className={`px-2 py-1 rounded-md text-[10px] font-medium transition-all ${
                active
                  ? 'bg-gray-900 text-white'
                  : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50'
              }`}
            >
              {f.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ===================================================================
 * 主页面
 * =================================================================== */
export default function LearningTimelinePage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // 筛选状态 ← URL 参数
  const eventType = searchParams.get('type') ?? '';
  const timeRange = searchParams.get('range') ?? '';

  const updateFilter = useCallback((key: string, value: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) {
        next.set(key, value);
      } else {
        next.delete(key);
      }
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const { events, total, loading, error, refetch } = useLearningEvents(
    100,
    eventType || undefined,
    timeRange ? parseInt(timeRange) : undefined,
  );

  // 按天分组
  const grouped = useMemo(() => groupByDate(events), [events]);

  const handleNavigate = useCallback((resourceId: string, stageId: string) => {
    if (resourceId) {
      navigate(`/resources/${resourceId}`);
    } else if (stageId) {
      navigate(`/path?stage=${encodeURIComponent(stageId)}`);
    }
  }, [navigate]);

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 md:py-8">
      {/* ========== 头部 ========== */}
      <div className="mb-6">
        <h1 className="text-2xl md:text-3xl font-extrabold text-gray-900 mb-1 flex items-center gap-2">
          <History className="w-7 h-7 text-brand-500" />
          学习时间线
        </h1>
        <p className="text-sm text-gray-500">
          共 <span className="font-semibold text-gray-700">{total}</span> 条学习行为记录
          {events.length < total && (
            <span className="text-gray-400">
              ，筛选后 <span className="font-semibold">{events.length}</span> 条
            </span>
          )}
        </p>
      </div>

      {/* ========== 内容区：左列（时间线）+ 右列（统计卡片） ========== */}
      {loading ? (
        <PageLoading text="加载时间线…" />
      ) : error ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="w-16 h-16 rounded-2xl bg-red-50 flex items-center justify-center mb-4">
            <History className="w-7 h-7 text-red-300" />
          </div>
          <h3 className="text-base font-semibold text-gray-700 mb-1">加载失败</h3>
          <p className="text-sm text-gray-400 mb-5">{error}</p>
          <button
            onClick={refetch}
            className="px-5 py-2.5 bg-gray-900 text-white rounded-xl text-sm font-semibold hover:bg-gray-800 transition-all"
          >
            刷新重试
          </button>
        </div>
      ) : (
        <div className="flex flex-col lg:flex-row gap-6">
          {/* 左列：时间线 */}
          <div className="flex-1 min-w-0">
            {/* 筛选栏 — 始终显示（已加载数据时） */}
            <FilterBar
              eventType={eventType}
              timeRange={timeRange}
              onEventTypeChange={(v) => updateFilter('type', v)}
              onTimeRangeChange={(v) => updateFilter('range', v)}
            />

            {/* 时间线列表 */}
            {events.length === 0 && total === 0 ? (
              <PageEmpty
                icon={<History className="w-8 h-8" />}
                title="暂无学习行为记录"
                description="开始学习后，你的资源查看、练习提交、阶段完成等行为将显示在这里"
                action={
                  <button
                    onClick={() => navigate('/resources')}
                    className="mt-3 px-5 py-2.5 bg-gray-900 text-white rounded-xl text-sm font-semibold hover:bg-gray-800 transition-all inline-flex items-center gap-2"
                  >
                    <BookOpen className="w-4 h-4" />
                    前往资源库
                  </button>
                }
              />
            ) : events.length === 0 && total > 0 ? (
              <div className="flex flex-col items-center py-16 text-center">
                <LayoutGrid className="w-10 h-10 text-gray-200 mb-3" />
                <p className="text-sm text-gray-400">当前筛选条件下没有记录</p>
                <button
                  onClick={() => setSearchParams({}, { replace: true })}
                  className="mt-3 px-4 py-2 bg-gray-100 text-gray-500 rounded-lg text-xs font-medium hover:bg-gray-200 transition-colors"
                >
                  清除筛选
                </button>
              </div>
            ) : (
              <div className="space-y-1 scrollable-list">
                {grouped.map(([dateLabel, dateEvents]) => (
                  <div key={dateLabel}>
                    <div className="flex items-center gap-2 mb-3 mt-5 first:mt-0">
                      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-gray-100 text-gray-500 text-[10px] font-medium">
                        <Clock className="w-3 h-3" />
                        {dateLabel}
                      </div>
                      <div className="flex-1 h-px bg-gray-100" />
                      <span className="text-[10px] text-gray-300">{dateEvents.length} 条</span>
                    </div>
                    <div className="pl-1">
                      {dateEvents.map((evt) => (
                        <TimelineItem key={evt.id} event={evt} onNavigate={handleNavigate} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 右列：统计卡片 — 有事件时才显示 */}
          {events.length > 0 && (
            <div className="w-full lg:w-64 flex-shrink-0">
              <div className="lg:sticky lg:top-6">
                <TimelineSummaryCard events={events} total={total} />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ===================================================================
 * 按日期分组工具
 * =================================================================== */
function groupByDate(events: TimelineEvent[]): [string, TimelineEvent[]][] {
  const groups = new Map<string, TimelineEvent[]>();

  const today = new Date();
  const todayStr = formatDateLabel(today);
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const yesterdayStr = formatDateLabel(yesterday);

  for (const evt of events) {
    const d = new Date(evt.timestamp);
    let label: string;
    const dateStr = formatDateLabel(d);

    if (dateStr === todayStr) {
      label = '今天';
    } else if (dateStr === yesterdayStr) {
      label = '昨天';
    } else {
      label = dateStr;
    }

    if (!groups.has(label)) groups.set(label, []);
    groups.get(label)!.push(evt);
  }

  return Array.from(groups.entries());
}

function formatDateLabel(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}
