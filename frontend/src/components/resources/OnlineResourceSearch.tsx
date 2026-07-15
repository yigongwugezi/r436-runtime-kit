// @ts-nocheck
import { useEffect, useMemo, useRef, useState } from 'react';
import { ExternalLink, Loader2, Save, Search } from 'lucide-react';
import WorkflowProgress from '../common/WorkflowProgress';
import { cancelWorkflow, consumeWorkflowEvents, readWorkflow, retryWorkflow, startWorkflow, type WorkflowState } from '../../api/workflows';
import { saveOnlineSearchResult } from '../../api/resources';
import {
  clearWorkflowTask,
  isActiveWorkflowStatus,
  isTerminalWorkflowStatus,
  readWorkflowTask,
  saveWorkflowTask,
  workflowStateFromEvent,
  type WorkflowTaskScope,
} from '../../utils/workflowTaskRecovery';

const RESOURCE_TYPES = ['article', 'video', 'course', 'document', 'paper'];
const TYPE_LABELS = { article: '文章', video: '视频', course: '课程', document: '文档', paper: '论文' };
const STAGE_LABELS = {
  topic_analysis: '分析搜索主题', cache: '检查缓存', primary_search: '搜索公开来源',
  fallback_search: '补充备用来源', stale_cache: '读取近期缓存', quality_filter: '检查结果相关性',
  personalized_ranking: '排序学习资源', completed: '搜索完成',
};

function cleanQuery(value: string) {
  return String(value || '').replace(/\s+/g, ' ').replace(/^[\s，,。；;]+|[\s，,。；;]+$/g, '').trim();
}

function safeUrl(url: string) {
  try { return ['http:', 'https:'].includes(new URL(url).protocol); } catch { return false; }
}

export default function OnlineResourceSearch({ sessionId, subjectId, query, onQueryChange }: {
  sessionId: string | null;
  subjectId?: string;
  query: string;
  onQueryChange: (query: string) => void;
}) {
  const [draft, setDraft] = useState(query);
  const [result, setResult] = useState<any>(null);
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [typeFilter, setTypeFilter] = useState('all');
  const [notice, setNotice] = useState('');
  const streamAbort = useRef<AbortController | null>(null);
  const activeTask = useRef('');
  const canonical = cleanQuery(query);
  const scope: WorkflowTaskScope = useMemo(() => ({
    workflowType: 'resource_search', sessionId: sessionId || '', subjectId: subjectId || '',
    operation: 'online_resource_search', topicFingerprint: canonical,
  }), [sessionId, subjectId, canonical]);

  useEffect(() => { setDraft(query); }, [query]);
  useEffect(() => {
    const abortForNavigation = () => streamAbort.current?.abort();
    window.addEventListener('pagehide', abortForNavigation);
    return () => {
      window.removeEventListener('pagehide', abortForNavigation);
      abortForNavigation();
    };
  }, []);

  const consume = async (taskId: string, taskScope: WorkflowTaskScope = scope) => {
    if (!sessionId) return;
    streamAbort.current?.abort();
    const controller = new AbortController();
    streamAbort.current = controller;
    activeTask.current = taskId;
    try {
      const current = await readWorkflow(taskId, sessionId);
      if (current.workflow_type !== 'resource_search') { clearWorkflowTask(taskScope); return; }
      setWorkflow({ taskId, workflowType: current.workflow_type, status: current.status, events: [], preview: '', elapsedMs: current.elapsed_ms || 0, result: current.result });
      if (current.status === 'completed') {
        setResult(current.result?.data?.recommendations || null);
        clearWorkflowTask(taskScope);
        return;
      }
      if (isActiveWorkflowStatus(current.status)) {
        await consumeWorkflowEvents(taskId, (event) => {
          if (activeTask.current !== taskId) return;
          setWorkflow((state) => state?.taskId === taskId ? workflowStateFromEvent(state, event) : state);
        }, controller.signal);
      }
      const latest = await readWorkflow(taskId, sessionId);
      if (activeTask.current !== taskId) return;
      setWorkflow((state) => state?.taskId === taskId ? { ...state, status: latest.status, elapsedMs: latest.elapsed_ms || state.elapsedMs, result: latest.result } : state);
      if (latest.status === 'completed') setResult(latest.result?.data?.recommendations || null);
      if (isTerminalWorkflowStatus(latest.status)) clearWorkflowTask(taskScope);
    } catch (error) {
      if (!controller.signal.aborted && !(error instanceof DOMException && error.name === 'AbortError')) {
        setNotice('无法恢复联网搜索任务，请重新搜索。');
        clearWorkflowTask(taskScope);
      }
    }
  };

  useEffect(() => {
    if (!sessionId || !canonical) return;
    const record = readWorkflowTask(scope);
    if (record) void consume(record.taskId);
  }, [sessionId, canonical, scope]);

  const search = async () => {
    const next = cleanQuery(draft);
    if (!sessionId || !next) { setNotice('请输入要搜索的学习主题。'); return; }
    setNotice(''); setResult(null); onQueryChange(next);
    try {
      const started = await startWorkflow('resource_search', {
        sessionId, subjectId, query: next, resourceTypes: RESOURCE_TYPES,
        operation: 'online_resource_search', language: 'zh-CN', refresh: false,
      });
      const nextScope = { ...scope, topicFingerprint: next };
      saveWorkflowTask({ ...nextScope, taskId: started.task_id, createdAt: Date.now(), mode: 'online_resource_search' });
      await consume(started.task_id, nextScope);
    } catch { setNotice('联网搜索暂时无法开始，请稍后重试。'); }
  };

  const cancel = async () => {
    if (!workflow || !sessionId) return;
    await cancelWorkflow(workflow.taskId, sessionId).catch(() => undefined);
    streamAbort.current?.abort();
    setWorkflow((state) => state ? { ...state, status: 'cancelled' } : state);
    clearWorkflowTask(scope);
  };

  const retry = async () => {
    if (!workflow || !sessionId) return;
    setNotice('');
    try {
      const restarted = await retryWorkflow(workflow.taskId);
      saveWorkflowTask({ ...scope, taskId: restarted.task_id, createdAt: Date.now(), mode: 'online_resource_search' });
      await consume(restarted.task_id);
    } catch { setNotice('重试未能开始，请稍后再试。'); }
  };

  const save = async (resource: any) => {
    if (!sessionId || !result?.canonical_query) return;
    try {
      const saved = await saveOnlineSearchResult({ sessionId, subjectId, query: result.canonical_query, taskId: workflow?.taskId, resource });
      setResult((current: any) => current ? {
        ...current,
        resources: current.resources.map((item: any) => item.url === resource.url ? { ...item, saved: true, reused: saved.reused } : item),
      } : current);
    } catch { setNotice('保存失败：该链接不可用或不属于当前会话。'); }
  };

  const visible = (result?.resources || []).filter((item: any) => typeFilter === 'all' || item.resource_type === typeFilter);
  return <section className="space-y-4" aria-label="联网搜索学习资源">
    <div className="rounded-2xl border border-primary-100 bg-primary-50/50 p-5">
      <div className="flex items-start gap-3">
        <div className="rounded-xl bg-primary-600 p-2 text-white"><Search size={18} /></div>
        <div className="flex-1"><h2 className="font-display text-xl font-bold text-surface-800">联网搜索学习资源</h2><p className="mt-1 text-sm text-surface-500">检索公开文章、视频、课程、文档和论文；搜索过程不会改变“我的资源”。</p></div>
      </div>
      <div className="mt-4 flex gap-2">
        <input value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void search(); }} placeholder="例如：递归调用栈" className="min-w-0 flex-1 rounded-xl border border-surface-200 bg-white px-4 py-3 text-sm outline-none focus:border-primary-400 focus:ring-2 focus:ring-primary-100" />
        <button onClick={() => void search()} disabled={!sessionId || !cleanQuery(draft) || Boolean(workflow && isActiveWorkflowStatus(workflow.status))} className="inline-flex items-center gap-2 rounded-xl bg-primary-600 px-4 py-3 text-sm font-semibold text-white hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"><Search size={16} />联网搜索</button>
      </div>
      {!sessionId && <p className="mt-2 text-xs text-amber-700">请先进入一个学习会话后再搜索，以便安全保存结果。</p>}
    </div>

    {notice && <p className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-700">{notice}</p>}
    {workflow && <WorkflowProgress state={workflow} onCancel={cancel} onRetry={retry} />}

    {result && <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-surface-50 px-4 py-3 text-sm text-surface-600"><span>主题：<strong className="text-surface-800">{result.canonical_query}</strong></span><span>{result.status === 'search_unavailable' ? '外部搜索暂不可用' : `找到 ${result.resources?.length || 0} 条公开资源`}</span></div>
      {result.warnings?.map((warning: string) => <p key={warning} className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">{warning}</p>)}
      <div className="flex flex-wrap gap-2"><button onClick={() => setTypeFilter('all')} className={`rounded-full px-3 py-1 text-xs ${typeFilter === 'all' ? 'bg-surface-800 text-white' : 'bg-surface-100 text-surface-600'}`}>全部</button>{RESOURCE_TYPES.map((type) => <button key={type} onClick={() => setTypeFilter(type)} className={`rounded-full px-3 py-1 text-xs ${typeFilter === type ? 'bg-primary-600 text-white' : 'bg-surface-100 text-surface-600'}`}>{TYPE_LABELS[type]}</button>)}</div>
      <p className="text-xs text-surface-400">类型筛选只过滤当前结果，不会重新创建搜索任务。</p>
      {!visible.length && <p className="rounded-xl bg-surface-50 px-4 py-5 text-sm text-surface-500">{result.status === 'search_unavailable' ? '搜索服务暂不可用，请稍后重试。' : '没有符合该类型的公开资源。'}</p>}
      <div className="space-y-3">{visible.map((resource: any) => <article key={resource.url} className="rounded-2xl border border-surface-100 bg-white p-4 shadow-soft"><div className="flex gap-3"><div className="min-w-0 flex-1"><div className="flex flex-wrap gap-2 text-xs text-surface-400"><span className="rounded bg-primary-50 px-2 py-0.5 text-primary-700">{TYPE_LABELS[resource.resource_type] || '未知类型'}</span><span>{resource.source || 'unknown source'}</span><span>{resource.quality_status || 'unknown'}</span></div><h3 className="mt-2 font-semibold text-surface-800">{resource.title}</h3><p className="mt-1 text-sm text-surface-500">{resource.snippet}</p><p className="mt-2 text-xs text-surface-500">推荐理由：{resource.reason}</p><p className="mt-1 text-xs text-surface-400">关联主题：{result.canonical_query}</p></div><div className="flex shrink-0 flex-col gap-2">{safeUrl(resource.url) && <a href={resource.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 rounded-lg border border-surface-200 px-2.5 py-1.5 text-xs text-surface-600 hover:bg-surface-50">打开<ExternalLink size={12} /></a>}<button onClick={() => void save(resource)} disabled={resource.saved} className="inline-flex items-center gap-1 rounded-lg bg-primary-50 px-2.5 py-1.5 text-xs font-medium text-primary-700 hover:bg-primary-100 disabled:opacity-60"><Save size={12} />{resource.saved ? (resource.reused ? '已保存' : '已加入') : '保存'}</button></div></div></article>)}</div>
    </div>}
  </section>;
}
