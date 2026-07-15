import { BookOpen, Calendar, CheckCircle2, Circle, Clock, ExternalLink, Layers, Target } from 'lucide-react';
import type { LearningPathViewModel, PathDisplayMode, PathRouteTarget, PathViewItem, PathViewStage } from '../../utils/learningPathViewModel';
import { summarizePathText } from '../../utils/learningPathViewModel';

interface Props {
  view: LearningPathViewModel;
  expandedStageKey?: string | null;
  onModeChange: (mode: PathDisplayMode) => void;
  onExpandedStageChange: (stageKey: string | null) => void;
  onNavigate: (target: PathRouteTarget) => void;
}

const modeLabels: Array<{ id: PathDisplayMode; label: string }> = [
  { id: 'textbook', label: '教材模式' },
  { id: 'daily', label: '日课模式' },
  { id: 'project', label: '项目模式' },
  { id: 'focus', label: '精进模式' },
];

function durationText(minutes: number | undefined, source: 'complete' | 'stage' | 'items' | 'partial' | 'missing'): string {
  if (!minutes) return '时长未提供';
  const value = minutes >= 60 ? `${Math.floor(minutes / 60)}h${minutes % 60 ? `${minutes % 60}m` : ''}` : `${minutes} 分钟`;
  return source === 'partial' ? `已提供 ${value}` : value;
}

function progressText(completed: number | null, total: number | null): string {
  return completed !== null && total !== null && total > 0 ? `${completed}/${total} 完成` : '暂无进度数据';
}

function TextPreview({ value, className = '' }: { value?: string; className?: string }) {
  if (!value) return null;
  const summary = summarizePathText(value);
  if (summary === value.replace(/\s+/g, ' ').trim()) {
    return <p className={`text-sm text-surface-500 whitespace-pre-wrap ${className}`}>{summary}</p>;
  }
  return (
    <details className={className}>
      <summary className="text-sm text-surface-500 cursor-pointer list-none">
        {summary} <span className="text-primary-600">展开全文</span>
      </summary>
      <p className="mt-2 text-sm text-surface-600 whitespace-pre-wrap break-words">{value}</p>
    </details>
  );
}

function ItemRow({ item, onNavigate }: { item: PathViewItem; onNavigate: (target: PathRouteTarget) => void }) {
  const completed = item.status === 'mastered' || item.status === 'completed';
  const available = item.target.kind !== 'unavailable';
  return (
    <button
      type="button"
      disabled={!available}
      onClick={() => available && onNavigate(item.target)}
      title={available ? '打开学习项' : item.target.reason}
      className={`w-full flex items-start gap-3 p-3 rounded-xl border text-left transition-colors ${
        available ? 'bg-white border-surface-200 hover:border-primary-300 hover:shadow-sm' : 'bg-surface-50 border-surface-200 cursor-not-allowed opacity-70'
      }`}
    >
      <span className={`mt-0.5 ${completed ? 'text-success-500' : 'text-surface-400'}`}>
        {completed ? <CheckCircle2 size={16} /> : <Circle size={15} />}
      </span>
      <span className="flex-1 min-w-0">
        <span className={`block text-sm font-medium ${completed ? 'text-surface-500 line-through' : 'text-surface-800'}`}>{item.title}</span>
        {item.goal && <span className="block mt-0.5 text-xs text-surface-500 line-clamp-2">{item.goal}</span>}
        <span className="mt-1 flex items-center gap-2 text-[11px] text-surface-400">
          <span className="inline-flex items-center gap-1"><Clock size={11} />{durationText(item.estimatedMinutes, item.estimatedMinutes ? 'items' : 'missing')}</span>
          {item.taskType && <span>{item.taskType}</span>}
          {item.contentType && <span>{item.contentType}</span>}
        </span>
      </span>
      {available ? <ExternalLink size={14} className="mt-1 text-surface-300" /> : null}
    </button>
  );
}

function StageText({ stage }: { stage: PathViewStage }) {
  return (
    <div className="min-w-0">
      <h3 className="font-display text-base font-bold text-surface-900">{stage.ordinal}. {stage.title}</h3>
      <TextPreview value={stage.objective || stage.description} className="mt-1" />
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-surface-400">
        <span>{progressText(stage.completedCount, stage.itemCount)}</span>
        <span>{durationText(stage.estimatedMinutes, stage.durationSource)}</span>
        {stage.estimatedDays ? <span>{stage.estimatedDays} 天</span> : null}
      </div>
    </div>
  );
}

function TextbookStage({ stage, expanded, onToggle, onNavigate }: { stage: PathViewStage; expanded: boolean; onToggle: () => void; onNavigate: Props['onNavigate'] }) {
  const hasContent = stage.chapters.length > 0 || stage.items.length > 0;
  return (
    <section className="bg-white rounded-2xl shadow-soft overflow-hidden">
      <button type="button" onClick={onToggle} className="w-full flex items-start gap-4 p-5 text-left hover:bg-surface-50">
        <span className="w-10 h-10 rounded-xl bg-primary-100 text-primary-600 flex items-center justify-center flex-shrink-0 font-bold">{stage.ordinal}</span>
        <StageText stage={stage} />
      </button>
      {expanded && (
        <div className="border-t border-surface-100 p-4 space-y-4">
          {!hasContent ? <p className="text-sm text-surface-400">该阶段暂无可展示的学习项。</p> : null}
          {stage.chapters.map((chapter, index) => (
            <div key={chapter.id || `chapter-${index}`} className="rounded-xl bg-surface-50 border border-surface-100 p-3">
              <button
                type="button"
                disabled={chapter.target.kind === 'unavailable'}
                onClick={() => chapter.target.kind !== 'unavailable' && onNavigate(chapter.target)}
                title={chapter.target.kind === 'unavailable' ? chapter.target.reason : '打开章节'}
                className="w-full flex items-center gap-2 text-left disabled:cursor-not-allowed disabled:opacity-60"
              >
                <BookOpen size={16} className="text-primary-500" />
                <span className="flex-1 text-sm font-semibold text-surface-800">{chapter.title}</span>
                <span className="text-xs text-surface-400">{chapter.items.length > 0 ? `${chapter.items.length} 项` : '暂无学习项'}</span>
              </button>
              {chapter.items.length > 0 && <div className="mt-3 grid gap-2">{chapter.items.map((item, itemIndex) => <ItemRow key={item.id || `item-${itemIndex}`} item={item} onNavigate={onNavigate} />)}</div>}
            </div>
          ))}
          {stage.items.length > 0 && (
            <div className="grid gap-2">
              {stage.items.map((item, index) => <ItemRow key={item.id || `item-${index}`} item={item} onNavigate={onNavigate} />)}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function ScheduleStage({ stage, mode, onNavigate }: { stage: PathViewStage; mode: 'daily' | 'project' | 'focus'; onNavigate: Props['onNavigate'] }) {
  const items = stage.chapters.flatMap((chapter) => chapter.items).concat(stage.items);
  const heading = mode === 'daily' ? '计划单位' : mode === 'project' ? '项目里程碑' : '精进阶段';
  return (
    <section className="bg-white rounded-2xl shadow-soft p-5">
      <div className="flex items-start gap-4">
        <span className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 font-bold ${mode === 'daily' ? 'bg-violet-100 text-violet-600' : 'bg-amber-100 text-amber-600'}`}>{stage.ordinal}</span>
        <div className="flex-1 min-w-0"><StageText stage={stage} /></div>
      </div>
      <p className="mt-4 text-xs font-medium text-surface-500">{heading}</p>
      {items.length > 0 ? <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">{items.map((item, index) => <ItemRow key={item.id || `item-${index}`} item={item} onNavigate={onNavigate} />)}</div> : <p className="mt-2 text-sm text-surface-400">该阶段暂无可展示的学习项。</p>}
    </section>
  );
}

export default function PathModeRouter({ view, expandedStageKey, onModeChange, onExpandedStageChange, onNavigate }: Props) {
  return (
    <div className="space-y-5">
      <section className="bg-white rounded-2xl shadow-soft p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <h2 className="font-display text-xl font-bold text-surface-900">{view.title}</h2>
            <TextPreview value={view.description} className="mt-1" />
          </div>
          <div className="flex flex-wrap gap-2 text-sm text-surface-600">
            <span className="inline-flex items-center gap-1 px-3 py-1.5 bg-surface-50 rounded-xl"><Layers size={15} />{view.stageCount} 个阶段</span>
            <span className="inline-flex items-center gap-1 px-3 py-1.5 bg-surface-50 rounded-xl"><Target size={15} />{view.progress === null ? '暂无进度数据' : `${view.progress}%`}</span>
            <span className="inline-flex items-center gap-1 px-3 py-1.5 bg-surface-50 rounded-xl"><Clock size={15} />{durationText(view.estimatedMinutes, view.durationSource)}</span>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2" role="tablist" aria-label="学习路径展示模式">
          {modeLabels.map((mode) => (
            <button key={mode.id} type="button" role="tab" aria-selected={view.mode === mode.id} onClick={() => onModeChange(mode.id)} className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${view.mode === mode.id ? 'bg-primary-600 text-white' : 'bg-surface-100 text-surface-600 hover:bg-surface-200'}`}>{mode.label}</button>
          ))}
        </div>
        <div className="mt-3 text-xs text-surface-400">
          {view.itemCount !== null && view.completedCount !== null ? `已完成 ${view.completedCount} / 共 ${view.itemCount} 项` : '学习项或进度数据未完整提供'}
        </div>
      </section>

      {view.dataCompleteness === 'empty' ? (
        <section className="bg-white rounded-2xl shadow-soft p-8 text-center"><Calendar size={28} className="mx-auto text-surface-300" /><p className="mt-3 text-surface-600">该学习路径暂未包含阶段内容。</p></section>
      ) : view.mode === 'textbook' ? (
        <div className="space-y-4">{view.stages.map((stage, index) => {
          const stageKey = stage.id || `view-stage-${index}`;
          return <TextbookStage key={stageKey} stage={stage} expanded={expandedStageKey === stageKey} onToggle={() => onExpandedStageChange(expandedStageKey === stageKey ? null : stageKey)} onNavigate={onNavigate} />;
        })}</div>
      ) : (
        <div className="space-y-4">{view.stages.map((stage, index) => <ScheduleStage key={stage.id || `stage-${index}`} stage={stage} mode={view.mode as 'daily' | 'project' | 'focus'} onNavigate={onNavigate} />)}</div>
      )}
    </div>
  );
}
