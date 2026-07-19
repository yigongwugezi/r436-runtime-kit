import { useEffect, useRef, useState } from 'react';
import { ExternalLink, Loader2, RefreshCw, Search, Sparkles } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useSubjectStore } from '../../store/subjectStore';
import Markdown from '../../utils/markdown';
import MermaidDiagram from '../../utils/mermaid';
import WorkflowProgress from '../common/WorkflowProgress';
import { cancelWorkflow, consumeWorkflowEvents, readWorkflow, startWorkflow, type WorkflowEvent, type WorkflowState } from '../../api/workflows';
import {
  clearWorkflowTask,
  isActiveWorkflowStatus,
  isTerminalWorkflowStatus,
  readWorkflowTask,
  saveWorkflowTask,
  workflowStateFromEvent,
  type WorkflowTaskScope,
} from '../../utils/workflowTaskRecovery';
import {
  generateSectionMindmap,
  generatedResourceLabels,
  getSectionMindmap,
  getGeneratedSectionResources,
  streamSectionResourceRecommendations,
  submitSectionResourceFeedback,
  submitGeneratedSectionResourceFeedback,
} from '../../api/sectionResources';
import type { ChapterMindmap, GeneratedSectionResource, GeneratedSectionResourceType, SearchProgressEvent, SectionRecommendationResult } from '../../types/sectionResources';
import type { Section } from '../../types/learningPath';

interface Props {
  sessionId: string;
  pathId: string;
  stageId: string;
  chapterId: string;
  chapterTitle: string;
  section: Section | undefined;
  taskId: string;
  dayId?: string;
  globalDayIndex?: number;
  lectureContent: string;
  sections: Section[];
  legacyMindmapId?: string;
}

const resourceGroups: Array<{ label: string; types: GeneratedSectionResourceType[] }> = [
  { label: '学习材料', types: ['summary_card', 'concept_comparison', 'worked_example', 'mistake_checklist', 'review_notes'] },
  { label: '结构化可视化', types: ['knowledge_map', 'process_flow', 'concept_diagram', 'execution_trace', 'code_trace'] },
];
const generatedResourceTypes = new Set<GeneratedSectionResourceType>(resourceGroups.flatMap((group) => group.types));
const platformLabels: Record<string, string> = { bilibili: 'B站', youtube: 'YouTube', vimeo: 'Vimeo', icourse163: '中国大学MOOC', xuetangx: '学堂在线', smartedu: '智慧教育平台', imooc: '慕课网', youku: '优酷', iqiyi: '爱奇艺', douyin: '抖音', tencent_video: '腾讯视频' };
const trustLabels: Record<string, string> = { official: '官方来源', educational: '教育来源', general: '普通来源' };
const matchLevelLabels: Record<string, string> = { exact_topic: '精确匹配', chapter_level: '章节匹配', course_level: '课程拓展', expanded_research: '拓展论文' };
type GeneratedFeedback = NonNullable<GeneratedSectionResource['feedback']>['feedback'];
const searchStageLabels: Record<SearchProgressEvent['stage'], string> = {
  topic_analysis: '\u5df2\u8bc6\u522b\u5b66\u4e60\u4e3b\u9898',
  cache: '\u5df2\u68c0\u67e5\u8fd1\u671f\u7ed3\u679c',
  primary_search: '\u6b63\u5728\u641c\u7d22\u9996\u9009\u516c\u5f00\u8d44\u6e90',
  fallback_search: '\u6b63\u5728\u8865\u5145\u76f8\u5173\u516c\u5f00\u8d44\u6e90',
  quality_filter: '\u6b63\u5728\u68c0\u67e5\u8d44\u6e90\u76f8\u5173\u6027',
  personalized_ranking: '\u6b63\u5728\u6839\u636e\u5b66\u4e60\u9700\u6c42\u6392\u5e8f',
  completed: '\u641c\u7d22\u5b8c\u6210',
  cancelled: '\u641c\u7d22\u5df2\u53d6\u6d88', failed: '\u641c\u7d22\u5931\u8d25', stale_cache: '\u5df2\u52a0\u8f7d\u8fd1\u671f\u6709\u6548\u8d44\u6e90',
};

function safeExternalUrl(url: string): boolean {
  try { return ['http:', 'https:'].includes(new URL(url).protocol); } catch { return false; }
}

function resourceErrorMessage(error: any): string {
  const detail = error?.response?.data?.detail;
  return typeof detail === 'string' ? detail : typeof detail?.message === 'string' ? detail.message : '资源加载失败，请刷新重试。';
}

export default function SectionResourceWorkspace(props: Props) {
  const nav = useNavigate();
  const { sessionId, pathId, stageId, chapterId, chapterTitle, section, taskId, dayId, globalDayIndex, lectureContent, sections, legacyMindmapId } = props;
  const subjectId = useSubjectStore((state) => state.activeSubject?.id ?? state.activeClassSubject?.subject);
  const [recommendations, setRecommendations] = useState<SectionRecommendationResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchProgress, setSearchProgress] = useState<SearchProgressEvent[]>([]);
  const [progressExpanded, setProgressExpanded] = useState(true);
  const [resourceFilter, setResourceFilter] = useState<'all' | 'video' | 'article' | 'course' | 'paper' | 'document'>('all');
  const [generated, setGenerated] = useState<GeneratedSectionResource[]>([]);
  const [generating, setGenerating] = useState<GeneratedSectionResourceType | null>(null);
  const [selectedType, setSelectedType] = useState<GeneratedSectionResourceType>('knowledge_map');
  const [generatedFeedback, setGeneratedFeedback] = useState<GeneratedFeedback>('helpful');
  const [preview, setPreview] = useState<GeneratedSectionResource | null>(null);
  const [mindmap, setMindmap] = useState<ChapterMindmap | null>(null);
  const [mindmapLoading, setMindmapLoading] = useState(false);
  const [notice, setNotice] = useState('');
  const requestSerial = useRef(0);
  const workflowSerial = useRef(0);
  const searchAbort = useRef<AbortController | null>(null);
  const workflowAbort = useRef<AbortController | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const pageScope = { sessionId, subjectId: subjectId || '', pathId, stageId, chapterId, sectionId: section?.id || '' };
  const resourceSearchScope: WorkflowTaskScope = { ...pageScope, workflowType: 'resource_search' };

  useEffect(() => () => { searchAbort.current?.abort(); workflowAbort.current?.abort(); }, []);

  useEffect(() => {
    let active = true;
    if (!sessionId || !section?.id || !pathId || !stageId || !taskId) { setGenerated([]); return; }
    const controller = new AbortController();
    getGeneratedSectionResources(section.id, sessionId, subjectId, { pathId, stageId, taskId, dayId, globalDayIndex }, controller.signal)
      .then((items) => active && setGenerated(items))
      .catch((error) => { if (active && !controller.signal.aborted) { setGenerated([]); setNotice(resourceErrorMessage(error)); } });
    return () => { active = false; controller.abort(); };
  }, [sessionId, section?.id, subjectId, pathId, stageId, taskId, dayId, globalDayIndex]);

  useEffect(() => {
    let active = true;
    if (!sessionId || !section?.id) { setMindmap(null); return; }
    getSectionMindmap(section.id, sessionId).then((item) => active && setMindmap(item)).catch(() => active && setMindmap(null));
    return () => { active = false; };
  }, [sessionId, section?.id]);

  useEffect(() => {
    if (!sessionId || !section?.id) return;
    const record = readWorkflowTask(resourceSearchScope);
    if (!record) return;
    const controller = new AbortController();
    let active = true;
    const restore = async () => {
      try {
        const task = await readWorkflow(record.taskId, sessionId);
        if (!active) return;
        if (task.workflow_type !== record.workflowType) { clearWorkflowTask(resourceSearchScope); return; }
        if (!isActiveWorkflowStatus(task.status)) {
          clearWorkflowTask(resourceSearchScope);
          if (task.status === 'completed') setRecommendations(task.result?.data?.recommendations ?? null);
          return;
        }
        setSearching(true); setSearchProgress([]); setProgressExpanded(true);
        await consumeWorkflowEvents(record.taskId, (event) => {
          if (!active || !event.stage_id || event.event.startsWith('workflow_')) return;
          const safe = event.safe_metadata || {};
          setSearchProgress((events) => {
            const next: SearchProgressEvent = {
              event: 'search_progress', stage: event.stage_id as SearchProgressEvent['stage'], status: event.status as SearchProgressEvent['status'],
              fallback_used: event.used_fallback, source_count: Number(safe.source_count || 0), result_count: Number(safe.result_count || 0),
            };
            const index = events.findIndex((item) => item.stage === next.stage);
            if (index < 0) return [...events, next];
            const updated = [...events]; updated[index] = next; return updated;
          });
        }, controller.signal);
        const latest = await readWorkflow(record.taskId, sessionId);
        if (!active) return;
        if (latest.status === 'completed') setRecommendations(latest.result?.data?.recommendations ?? null);
        if (isTerminalWorkflowStatus(latest.status)) clearWorkflowTask(resourceSearchScope);
      } catch {
        if (active) clearWorkflowTask(resourceSearchScope);
      } finally {
        if (active) { setSearching(false); setProgressExpanded(false); }
      }
    };
    void restore();
    return () => { active = false; controller.abort(); };
  }, [sessionId, subjectId, pathId, stageId, chapterId, section?.id]);

  useEffect(() => {
    if (!sessionId || !section?.id) return;
    const scopes: WorkflowTaskScope[] = [
      { ...pageScope, workflowType: 'generated_resource' },
      { ...pageScope, workflowType: 'generated_resource_regeneration' },
    ];
    const scope = scopes.find((item) => readWorkflowTask(item));
    if (!scope) return;
    const record = readWorkflowTask(scope);
    if (!record || !generatedResourceTypes.has(record.resourceType as GeneratedSectionResourceType)) { clearWorkflowTask(scope); return; }
    const controller = new AbortController();
    let active = true;
    const restore = async () => {
      try {
        const task = await readWorkflow(record.taskId, sessionId);
        if (!active) return;
        if (task.workflow_type !== record.workflowType) { clearWorkflowTask(scope); return; }
        setSelectedType(record.resourceType as GeneratedSectionResourceType);
        setWorkflow({ taskId: record.taskId, workflowType: task.workflow_type, status: task.status, events: [], preview: '', elapsedMs: task.elapsed_ms || 0 });
        if (isActiveWorkflowStatus(task.status)) {
          setGenerating(record.resourceType as GeneratedSectionResourceType);
          await consumeWorkflowEvents(record.taskId, (event: WorkflowEvent) => {
            if (active) setWorkflow((current) => current?.taskId === record.taskId ? workflowStateFromEvent(current, event) : current);
          }, controller.signal);
        }
        const latest = await readWorkflow(record.taskId, sessionId);
        if (!active) return;
        if (latest.status === 'completed') {
          const resource = latest.result?.data?.resource as GeneratedSectionResource | undefined;
          if (resource) {
            setGenerated((items) => [resource, ...items.filter((item) => item.id !== resource.id)]);
            setPreview(resource);
          } else {
            const items = await getGeneratedSectionResources(section.id, sessionId, subjectId, { pathId, stageId, taskId, dayId, globalDayIndex });
            if (active) setGenerated(items);
          }
        }
        if (isTerminalWorkflowStatus(latest.status)) clearWorkflowTask(scope);
      } catch {
        if (active) { clearWorkflowTask(scope); setWorkflow(null); }
      } finally { if (active) setGenerating(null); }
    };
    void restore();
    return () => { active = false; controller.abort(); };
  }, [sessionId, subjectId, pathId, stageId, chapterId, section?.id]);

  const searchResources = async (filter = resourceFilter) => {
    if (!sessionId || !section) return;
    searchAbort.current?.abort();
    const controller = new AbortController();
    searchAbort.current = controller;
    const requestId = ++requestSerial.current;
    setSearching(true);
    setSearchProgress([]);
    setProgressExpanded(true);
    setNotice('');
    try {
      const result = await streamSectionResourceRecommendations(section.id, {
        sessionId, sectionTitle: section.title, knowledgePoints: section.knowledgePoints,
        subjectId,
        language: 'zh-CN', resourceTypes: filter === 'all' ? ['video', 'article', 'course', 'document', 'paper'] : [filter],
        refresh: false,
      }, (event) => {
        if (requestId === requestSerial.current) setSearchProgress((events) => {
          const index = events.findIndex((item) => item.stage === event.stage);
          if (index < 0) return [...events, event];
          const next = [...events]; next[index] = event; return next;
        });
      }, controller.signal, (started) => {
        saveWorkflowTask({ ...resourceSearchScope, taskId: started.task_id, createdAt: Date.now() });
      });
      if (requestId === requestSerial.current) {
        setRecommendations(result);
        setProgressExpanded(false);
        clearWorkflowTask(resourceSearchScope);
      }
    } catch (error) {
      if (requestId === requestSerial.current && !(error instanceof DOMException && error.name === 'AbortError')) {
        setRecommendations({ query: [], resources: [], status: 'failed', warnings: ['外部资源检索失败，请稍后重试。'] });
      }
    } finally { if (requestId === requestSerial.current) setSearching(false); }
  };
  const cancelSearch = () => {
    searchAbort.current?.abort();
    setSearching(false);
    setSearchProgress((events) => {
      const event: SearchProgressEvent = {
        event: 'search_progress', stage: 'cancelled', status: 'cancelled',
        source_count: events[events.length - 1]?.source_count || 0,
        result_count: events[events.length - 1]?.result_count || 0,
      };
      const index = events.findIndex((item) => item.stage === 'cancelled');
      if (index < 0) return [...events, event];
      const next = [...events]; next[index] = event; return next;
    });
    setProgressExpanded(true);
    clearWorkflowTask(resourceSearchScope);
  };
  const search = () => searchResources(resourceFilter);

  const giveFeedback = async (resource: any, feedback: 'helpful' | 'not_relevant' | 'too_hard' | 'too_easy') => {
    if (!sessionId || !section || !subjectId) return;
    setNotice('');
    try {
      await submitSectionResourceFeedback(section.id, { sessionId, subjectId, url: resource.url, resourceType: resource.resource_type, feedback });
      setRecommendations((current) => current ? { ...current, resources: current.resources.map((item) => item.url === resource.url ? { ...item, feedback } : item) } : current);
    } catch { setNotice('反馈保存失败，请稍后重试。'); }
  };

  const generate = async (resourceType: GeneratedSectionResourceType, feedback: GeneratedFeedback | '' = '') => {
    if (!sessionId || !section) return;
    if (workflow && isActiveWorkflowStatus(workflow.status)) return;
    workflowAbort.current?.abort();
    const controller = new AbortController();
    workflowAbort.current = controller;
    const requestId = ++workflowSerial.current;
    setGenerating(resourceType);
    setNotice('');
    try {
      const started = await startWorkflow(feedback ? 'generated_resource_regeneration' : 'generated_resource', {
        sessionId, resourceType, pathId, stageId, chapterId, sectionTitle: section.title,
        subjectId, knowledgePoints: section.knowledgePoints, lectureContent, feedback,
        regenerate: generated.some((item) => item.resourceType === resourceType),
      });
      setWorkflow({ taskId: started.task_id, workflowType: started.workflow_type, status: started.status, events: [], preview: '', elapsedMs: 0 });
      const workflowScope: WorkflowTaskScope = { ...pageScope, workflowType: started.workflow_type };
      saveWorkflowTask({ ...workflowScope, taskId: started.task_id, createdAt: Date.now(), resourceType });
      await consumeWorkflowEvents(started.task_id, (event: WorkflowEvent) => {
        if (requestId !== workflowSerial.current) return;
        setWorkflow((current) => current?.taskId === started.task_id ? workflowStateFromEvent(current, event) : current);
      }, controller.signal);
      const task = await readWorkflow(started.task_id, sessionId);
      if (requestId !== workflowSerial.current) return;
      if (task.status !== 'completed') {
        if (isTerminalWorkflowStatus(task.status)) clearWorkflowTask(workflowScope);
        return;
      }
      const result = task.result?.data as { resource: GeneratedSectionResource };
      if (!result?.resource) {
        clearWorkflowTask(workflowScope);
        const items = await getGeneratedSectionResources(section.id, sessionId, subjectId, { pathId, stageId, taskId, dayId, globalDayIndex });
        setGenerated(items);
        return;
      }
      const previous = generated.find((item) => item.resourceType === resourceType);
      const next: GeneratedSectionResource = {
        ...result.resource,
        feedback: feedback ? { ...previous?.feedback, feedback } : result.resource.feedback,
      };
      setGenerated((items) => [next, ...items.filter((item) => item.id !== next.id)]);
      setPreview(next);
      clearWorkflowTask(workflowScope);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) setNotice('资源生成失败，请稍后重试。');
    } finally { if (requestId === workflowSerial.current) setGenerating(null); }
  };

  const cancelGeneration = async () => {
    if (!workflow || !sessionId) return;
    await cancelWorkflow(workflow.taskId, sessionId).catch(() => undefined);
    workflowAbort.current?.abort();
    setWorkflow((current) => current ? { ...current, status: 'cancelled' } : current);
    setGenerating(null);
    clearWorkflowTask({ ...pageScope, workflowType: workflow.workflowType });
  };

  const regenerateFromFeedback = async () => {
    if (!preview || !sessionId || !section) return;
    try {
      const savedFeedback = { ...preview.feedback, feedback: generatedFeedback };
      await submitGeneratedSectionResourceFeedback(section.id, preview.resourceType, {
        sessionId,
        subjectId,
        feedback: generatedFeedback,
        rating: savedFeedback.rating,
        comment: savedFeedback.comment,
      });
      setGenerated((items) => items.map((item) => item.id === preview.id ? { ...item, feedback: savedFeedback } : item));
      setPreview((item) => item ? { ...item, feedback: savedFeedback } : item);
      if (generatedFeedback === 'helpful') {
        setNotice('已记录，这将用于优化后续同类资源推荐。');
        return;
      }
      await generate(preview.resourceType, generatedFeedback);
    } catch { setNotice('反馈保存或重新生成失败，请稍后重试。'); }
  };

  const openGeneratedDetail = (resource: GeneratedSectionResource) => {
    if (!section) return;
    const returnTo = `/lecture/section/${encodeURIComponent(section.id)}?panel=resources`;
    const query = new URLSearchParams({
      source: 'lecture', activePanel: 'related_resources', returnTo, sessionId,
      subjectId: subjectId || '', pathId, stageId, chapterId, sectionId: section.id,
    });
    nav(`/resources/${encodeURIComponent(resource.id)}?${query.toString()}`);
  };

  const generateMindmap = async () => {
    if (!sessionId || !section) return;
    setMindmapLoading(true);
    setNotice('');
    try {
      const result = await generateSectionMindmap(section.id, {
        sessionId, pathId, stageId, sectionTitle: section.title,
        subjectId, knowledgePoints: section.knowledgePoints, lectureContent,
        regenerate: Boolean(mindmap),
      });
      setMindmap(result.mindmap);
    } catch { setNotice('思维导图生成失败，请稍后重试。'); } finally { setMindmapLoading(false); }
  };

  return <div className="p-4 space-y-4">
    {notice && <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">{notice}</p>}
    {workflow && <WorkflowProgress key={`${workflow.taskId}:${workflow.status}`} state={workflow} onCancel={cancelGeneration} onRetry={() => generating ? undefined : generate(selectedType)} />}

    {/* ── 一键推送 ── */}
    <button onClick={() => searching ? cancelSearch() : search()} disabled={!section}
      className="w-full flex items-center justify-center gap-2 px-3 py-3 rounded-xl bg-surface-800 text-white text-xs font-semibold hover:bg-surface-900 disabled:opacity-40 transition-colors">
      <Search size={14} />{searching ? '取消搜索' : recommendations ? '重新推送' : '一键推送'}
    </button>
    <p className="text-[10px] text-surface-400 text-center -mt-3 mb-1">基于画像 + 知识点智能匹配</p>

    {/* ── 分类推送 ── */}
    <div className="grid grid-cols-2 gap-1.5">
      {[
        { key: 'all', label: '全部' },
        { key: 'video', label: '教学视频' },
        { key: 'article', label: '文章' },
        { key: 'course', label: '课程' },
        { key: 'document', label: '文档' },
        { key: 'paper', label: '学术论文' },
      ].map(({ key, label }) => (
        <button key={label}
          onClick={() => {
            const filter = key as typeof resourceFilter;
            setResourceFilter(filter);
            void searchResources(filter);
          }}
          disabled={!section}
          className="flex items-center justify-center gap-1 px-2.5 py-2 rounded-lg bg-surface-50 text-surface-600 text-[10px] font-medium hover:bg-surface-100 disabled:opacity-30 transition-colors">
          {label}
        </button>
      ))}
    </div>

    {/* ── 推送结果 ── */}
    {searchProgress.length > 0 && <details open={searching || progressExpanded} onToggle={(event) => setProgressExpanded((event.currentTarget as HTMLDetailsElement).open)} className="rounded-xl border border-surface-100 bg-surface-50 p-3 text-[11px] text-surface-600">
      <summary className="cursor-pointer font-medium text-surface-700">
        {searching ? '\u6b63\u5728\u4e3a\u4f60\u5bfb\u627e\u5b66\u4e60\u8d44\u6e90' : `\u641c\u7d22\u5b8c\u6210 \u00b7 \u68c0\u67e5 ${searchProgress[searchProgress.length - 1]?.source_count || 0} \u4e2a\u6765\u6e90 \u00b7 \u63a8\u8350 ${searchProgress[searchProgress.length - 1]?.result_count || 0} \u6761\u9ad8\u76f8\u5173\u8d44\u6e90`}
      </summary>
      <ol className="mt-2 space-y-1.5">
        {searchProgress.map((event) => <li key={event.stage} className="flex gap-2">
          <span className={event.status === 'running' ? 'animate-spin text-primary-600' : event.status === 'failed' ? 'text-amber-600' : 'text-success-600'}>{event.status === 'running' ? '\u25cc' : event.status === 'cancelled' ? '\u25cb' : event.status === 'failed' ? '!' : '\u2713'}</span>
          <span>{searchStageLabels[event.stage]}{event.fallback_used ? '\uff0c\u9996\u9009\u7ed3\u679c\u4e0d\u8db3\uff0c\u5df2\u81ea\u52a8\u5c1d\u8bd5\u5907\u7528\u6765\u6e90' : ''}{event.stale ? '\uff0c\u5b9e\u65f6\u641c\u7d22\u6682\u65f6\u4e0d\u7a33\u5b9a' : ''}</span>
        </li>)}
      </ol>
    </details>}

    {recommendations && (
      <div className="space-y-1.5">
        {!recommendations.resources.length && <p className="rounded-lg bg-surface-50 px-3 py-2 text-[11px] text-surface-500">{recommendations.status === 'search_unavailable' ? '外部搜索暂不可用，请稍后重试。' : recommendations.status === 'expanded_no_results' ? '已扩大搜索范围，仍未找到高相关公开资源。' : recommendations.status === 'no_high_relevance' ? '暂无高相关公开资源，可调整知识点后重试。' : '未找到与当前小节匹配的公开资源。'}</p>}
        {recommendations.resources.filter(r => resourceFilter === 'all' || r.resource_type === resourceFilter).map(r => (
          <div key={r.url} className="rounded-lg bg-surface-50 p-2.5">
            <p className="text-xs font-medium text-surface-700 line-clamp-2">{r.title}</p>
            <p className="mt-0.5 text-[10px] text-surface-400">{r.platform ? platformLabels[r.platform] || r.platform : r.resource_type} · {r.source} · {trustLabels[r.trust_level] || r.trust_level}</p>
            {r.match_level && <p className="mt-0.5 text-[10px] text-surface-400">{matchLevelLabels[r.match_level] || r.match_level}</p>}
            <p className="mt-1 text-[11px] text-surface-500 line-clamp-2">{r.snippet}</p>
            <p className="mt-1 text-[10px] text-surface-500 line-clamp-2">推荐理由：{r.reason}</p>
            {safeExternalUrl(r.url) && <a href={r.url} target="_blank" rel="noopener noreferrer"
              className="mt-1.5 inline-flex items-center gap-1 text-[10px] font-medium text-surface-500 hover:text-surface-700">
              {r.resource_type === 'video' ? '打开视频' : '打开原文'} <ExternalLink size={10} /></a>}
            <div className="mt-2 flex flex-wrap gap-1"><span className="mr-1 text-[10px] text-surface-400">这条推荐：</span>{[['helpful', '有帮助'], ['not_relevant', '不相关'], ['too_hard', '太难'], ['too_easy', '太简单']].map(([value, label]) => <button key={value} onClick={() => giveFeedback(r, value as 'helpful' | 'not_relevant' | 'too_hard' | 'too_easy')} className={`rounded px-1.5 py-0.5 text-[10px] ${r.feedback === value ? 'bg-blue-100 text-blue-700' : 'bg-white text-surface-500 hover:bg-surface-100'}`}>{label}</button>)}</div>
          </div>
        ))}
      </div>
    )}

  </div>;
}
