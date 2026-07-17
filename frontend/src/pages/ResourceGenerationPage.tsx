import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { BrainCircuit, CheckCircle2, ChevronRight, Clapperboard, Clock, FileQuestion, FileText, Image as ImageIcon, Loader2, Presentation, Sparkles, XCircle } from 'lucide-react';
import { startGeneralResourceGeneration, type GeneralResourceType } from '../api/resources';
import { cancelWorkflow, consumeWorkflowEvents, readWorkflow, retryWorkflow, type WorkflowState } from '../api/workflows';
import { getCurrentLearner } from '../store/authStore';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';
import { useLearningPath } from '../hooks/useLearningPath';
import {
  clearWorkflowTask,
  isActiveWorkflowStatus,
  isTerminalWorkflowStatus,
  saveWorkflowTask,
  workflowStateFromEvent,
  type WorkflowTaskRecoveryRecord,
  type WorkflowTaskScope,
} from '../utils/workflowTaskRecovery';

type TaskEntry = WorkflowState & { resourceType: GeneralResourceType; reusedExisting?: boolean };

const resourceTypes: Array<{ id: GeneralResourceType; label: string; icon: typeof FileText; description: string }> = [
  { id: 'lecture', label: '课程讲义', icon: FileText, description: '结构化的知识讲解' },
  { id: 'mindmap', label: '思维导图', icon: BrainCircuit, description: '可渲染的知识结构图' },
  { id: 'quiz', label: '练习题库', icon: FileQuestion, description: '含答案与解析的自测题' },
  { id: 'practice', label: '实操案例', icon: FileText, description: '含代码示例的实践任务' },
  { id: 'reading', label: '拓展阅读', icon: FileText, description: '学术风格的延伸阅读' },
  { id: 'image', label: '知识图解', icon: ImageIcon, description: 'AI 生成的教学图解' },
  { id: 'ppt', label: 'PPT 演示', icon: Presentation, description: '可下载的本地演示文稿' },
  { id: 'manim', label: '动画演示', icon: Clapperboard, description: '需要本地 Manim 渲染环境' },
];

const labels = Object.fromEntries(resourceTypes.map((item) => [item.id, item.label])) as Record<GeneralResourceType, string>;

const POLL_INTERVAL_MS = 3000;

function normalizeTypes(value: string | null): GeneralResourceType[] {
  const aliases: Record<string, GeneralResourceType> = { 'mind-map': 'mindmap', mind_map: 'mindmap', case_study: 'practice' };
  const known = new Set<GeneralResourceType>(['lecture', 'mindmap', 'quiz', 'ppt', 'video', 'animation', 'manim', 'reading', 'practice', 'image']);
  const values = (value || '').split(',').map((item) => aliases[item] || item).filter((item): item is GeneralResourceType => known.has(item as GeneralResourceType));
  return [...new Set(values)].slice(0, 3);
}

function fingerprint(topic: string): string {
  let value = 2166136261;
  for (const char of topic.trim()) value = Math.imul(value ^ char.charCodeAt(0), 16777619);
  return (value >>> 0).toString(16);
}

function elapsed(milliseconds = 0): string {
  return `${Math.max(0, Math.floor(milliseconds / 1000))}s`;
}

/** Extract the latest stage label from workflow events for human-readable progress. */
function latestStageLabel(events: WorkflowState['events']): string | null {
  // Walk backwards and find the first event with a meaningful label
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.label && e.event !== 'heartbeat') return e.label;
  }
  return null;
}

export default function ResourceGenerationPage() {
  const navigate = useNavigate();
  const isParent = getCurrentLearner()?.role === 'parent';
  const sessionId = useChatStore((state) => state.currentSessionId);
  const bumpDataVersion = useChatStore((state) => state.bumpDataVersion);
  const subjectId = useSubjectStore((state) => state.activeSubject?.id || '');
  const { path } = useLearningPath();
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedTypes, setSelectedTypes] = useState<GeneralResourceType[]>(() => {
    const parsed = normalizeTypes(searchParams.get('types'));
    return parsed.length ? parsed : ['lecture', 'mindmap', 'quiz'];
  });
  const [prompt, setPrompt] = useState(() => searchParams.get('q') || '');
  const [workflows, setWorkflows] = useState<Record<string, TaskEntry>>({});
  const [genError, setGenError] = useState('');
  const [progressExpanded, setProgressExpanded] = useState(true);
  const controllers = useRef(new Map<string, AbortController>());
  const pollingTimers = useRef(new Map<string, ReturnType<typeof setInterval>>());
  const restoring = useRef(new Set<string>());
  const topicFingerprint = useMemo(() => fingerprint(prompt), [prompt]);

  const completedResources = useMemo(() => {
    return Object.values(workflows)
      .filter((task) => task.status === 'completed' && task.result?.data?.resource)
      .map((task) => ({
        id: task.result.data.resource.id,
        type: task.result.data.resource.type,
        title: task.result.data.resource.title,
        description: task.result.data.resource.description,
        difficulty: task.result.data.resource.difficulty,
      }));
  }, [workflows]);

  const updateUrl = useCallback((nextPrompt: string, nextTypes: GeneralResourceType[]) => {
    const next = new URLSearchParams();
    if (nextPrompt) next.set('q', nextPrompt);
    if (nextTypes.length) next.set('types', nextTypes.join(','));
    setSearchParams(next, { replace: true });
  }, [setSearchParams]);

  const scopeFor = useCallback((resourceType: GeneralResourceType): WorkflowTaskScope => ({
    workflowType: 'general_resource_generation', sessionId, subjectId, pathId: path?.id || '',
    resourceType, operation: 'generate', topicFingerprint, recoveryKey: `${resourceType}:${topicFingerprint}`,
  }), [path?.id, sessionId, subjectId, topicFingerprint]);

  const putTask = useCallback((resourceType: GeneralResourceType, state: WorkflowState, reusedExisting = false) => {
    setWorkflows((current) => ({ ...current, [resourceType]: { ...state, resourceType, reusedExisting } }));
  }, []);

  /** Poll readWorkflow every POLL_INTERVAL_MS until terminal state. */
  const startPolling = useCallback((resourceType: GeneralResourceType, taskId: string, sessionId: string, scope: WorkflowTaskScope, reusedExisting: boolean) => {
    // Clear any existing poll timer for this resource type
    const existing = pollingTimers.current.get(resourceType);
    if (existing !== undefined) clearInterval(existing);

    const timerId = setInterval(async () => {
      try {
        const latest = await readWorkflow(taskId, sessionId);
        if (!latest) return;
        const terminal = isTerminalWorkflowStatus(latest.status);
        putTask(resourceType, {
          taskId, workflowType: latest.workflow_type, status: latest.status,
          events: [], preview: '', elapsedMs: latest.elapsed_ms || 0, result: latest.result,
          errorMessage: latest.safe_error_message || '',
        }, reusedExisting);
        if (latest.status === 'completed') bumpDataVersion();
        if (terminal) {
          clearWorkflowTask(scope);
          clearInterval(timerId);
          pollingTimers.current.delete(resourceType);
        } else {
          // Keep record fresh so it doesn't expire
          saveWorkflowTask({ ...scope, taskId, createdAt: Date.now(), resourceType, mode: 'general_resource_generation' });
        }
      } catch {
        // poll failure is silent — keep trying
      }
    }, POLL_INTERVAL_MS);
    pollingTimers.current.set(resourceType, timerId);
  }, [bumpDataVersion, putTask]);

  /** Monitor workflow via SSE, falling back to polling on disconnect. */
  const monitor = useCallback(async (resourceType: GeneralResourceType, taskId: string, reusedExisting = false, initial?: WorkflowState) => {
    const scope = scopeFor(resourceType);
    // If already monitoring, don't start another
    if (controllers.current.has(resourceType) || pollingTimers.current.has(resourceType)) return;
    const controller = new AbortController();
    controllers.current.set(resourceType, controller);
    try {
      const base = initial || { taskId, workflowType: scope.workflowType, status: 'queued' as const, events: [], preview: '', elapsedMs: 0 };
      putTask(resourceType, base, reusedExisting);
      await consumeWorkflowEvents(taskId, (event) => {
        if (event.safe_error_message) setGenError(event.safe_error_message);
        setWorkflows((current) => {
          const existing = current[resourceType];
          return existing?.taskId === taskId
            ? { ...current, [resourceType]: { ...workflowStateFromEvent(existing, event), resourceType, reusedExisting } }
            : current;
        });
      }, controller.signal);
    } catch (error) {
      // On abort (component unmount), silently stop — don't clear saved task
      if (error instanceof DOMException && error.name === 'AbortError') {
        controllers.current.delete(resourceType);
        return;
      }
      // Non-abort error: SSE disconnected unexpectedly — silently fall to polling
    } finally {
      controllers.current.delete(resourceType);
      // Check final status via REST; if still active, start polling
      try {
        const latest = await readWorkflow(taskId, sessionId);
        if (latest && isActiveWorkflowStatus(latest.status)) {
          putTask(resourceType, {
            taskId, workflowType: latest.workflow_type, status: latest.status,
            events: [], preview: '', elapsedMs: latest.elapsed_ms || 0, result: latest.result,
            errorMessage: latest.safe_error_message || '',
          }, reusedExisting);
          startPolling(resourceType, taskId, sessionId, scope, reusedExisting);
        } else if (latest && isTerminalWorkflowStatus(latest.status)) {
          putTask(resourceType, {
            taskId, workflowType: latest.workflow_type, status: latest.status,
            events: [], preview: '', elapsedMs: latest.elapsed_ms || 0, result: latest.result,
            errorMessage: latest.safe_error_message || '',
          }, reusedExisting);
          if (latest.status === 'completed') {
            bumpDataVersion();
            // Keep completed tasks in sessionStorage for recovery on page refresh
          } else {
            clearWorkflowTask(scope);
          }
        }
        // if latest is null (readWorkflow failed), keep saved task for future recovery
      } catch {
        // readWorkflow failed — keep saved task for future recovery
      }
    }
  }, [bumpDataVersion, putTask, scopeFor, sessionId, startPolling]);

  /** Cleanup polling timers on unmount. */
  useEffect(() => {
    return () => {
      pollingTimers.current.forEach((timerId) => clearInterval(timerId));
      pollingTimers.current.clear();
      controllers.current.forEach((controller) => controller.abort());
      controllers.current.clear();
    };
  }, []);

  /**
   * Recovery: on mount, find ALL saved general_resource_generation workflow tasks
   * in sessionStorage and restore their monitoring, regardless of current prompt/types.
   */
  useEffect(() => {
    if (!sessionId) return;
    let active = true;

    const storage = (() => { try { return window.sessionStorage; } catch { return null; } })();
    if (!storage) return;

    const PREFIX = 'eduagent.workflow-task.v1:general_resource_generation:';
    const now = Date.now();
    const found: WorkflowTaskRecoveryRecord[] = [];

    for (let i = 0; i < storage.length; i++) {
      const key = storage.key(i);
      if (!key || !key.startsWith(PREFIX)) continue;
      try {
        const raw = storage.getItem(key);
        if (!raw) continue;
        const record = JSON.parse(raw) as WorkflowTaskRecoveryRecord;
        if (!record.taskId || !Number.isFinite(record.createdAt) || now - record.createdAt > 30 * 60 * 1000) {
          storage.removeItem(key);
          continue;
        }
        found.push(record);
      } catch {
        storage.removeItem(key);
      }
    }

    for (const record of found) {
      if (restoring.current.has(record.taskId)) continue;
      restoring.current.add(record.taskId);
      void (async () => {
        try {
          const task = await readWorkflow(record.taskId, sessionId);
          if (!active) return;
          const rt = record.resourceType as GeneralResourceType;
          const restored: WorkflowState = {
            taskId: record.taskId, workflowType: task.workflow_type, status: task.status,
            events: [], preview: '', elapsedMs: task.elapsed_ms || 0, result: task.result,
            errorMessage: task.safe_error_message || '',
          };
          putTask(rt, restored);
          if (isActiveWorkflowStatus(task.status)) {
            await monitor(rt, record.taskId, false, restored);
          } else if (isTerminalWorkflowStatus(task.status)) {
            if (task.status === 'completed') bumpDataVersion();
            // Only clean up failed/cancelled tasks; keep completed ones for recovery
            if (task.status !== 'completed') {
              const baseScope: WorkflowTaskScope = {
                workflowType: 'general_resource_generation', sessionId, subjectId, pathId: path?.id || '',
                resourceType: rt, operation: 'generate', topicFingerprint: '', recoveryKey: '',
              };
              clearWorkflowTask(baseScope);
            }
          }
        } catch {
          // recovery failure is silent — task will be picked up again on next visit
        } finally {
          restoring.current.delete(record.taskId);
        }
      })();
    }

    return () => {
      active = false;
      restoring.current.clear();
    };
  }, [sessionId, subjectId]);

  if (isParent) return <div className="h-[calc(100vh-300px)] flex items-center justify-center text-surface-500">家长账户只能查看已生成资源。</div>;

  const activeTasks = Object.values(workflows).filter((task) => isActiveWorkflowStatus(task.status));
  const updatePrompt = (value: string) => { setPrompt(value); updateUrl(value, selectedTypes); };
  const toggleType = (resourceType: GeneralResourceType) => {
    const next = selectedTypes.includes(resourceType)
      ? selectedTypes.filter((item) => item !== resourceType)
      : selectedTypes.length < 3 ? [...selectedTypes, resourceType] : selectedTypes;
    setSelectedTypes(next); updateUrl(prompt, next);
  };

  const handleGenerate = async () => {
    if (!sessionId || !prompt.trim() || !selectedTypes.length || activeTasks.length) return;
    setGenError(''); setProgressExpanded(true);
    try {
      const started = await startGeneralResourceGeneration({
        sessionId, learnerId: getCurrentLearner()?.id, subjectId, pathId: path?.id || '', stageId: '', chapterId: '', sectionId: '', topic: prompt.trim(), resourceTypes: selectedTypes,
        difficulty: 'medium', operation: 'generate', mode: 'general_resource_generation', profileSnapshotVersion: '', generationOptions: {},
      });
      if (started.tasks.length !== selectedTypes.length) throw new Error('任务未完整创建');
      for (const task of started.tasks) {
        const scope = scopeFor(task.resource_type);
        const initial: WorkflowState = { taskId: task.task_id, workflowType: task.workflow_type, status: task.status as WorkflowState['status'], events: [], preview: '', elapsedMs: 0 };
        saveWorkflowTask({ ...scope, taskId: task.task_id, createdAt: Date.now(), resourceType: task.resource_type, mode: 'general_resource_generation' });
        putTask(task.resource_type, initial, Boolean(task.reused_existing));
        void monitor(task.resource_type, task.task_id, Boolean(task.reused_existing), initial);
      }
    } catch (error: any) { setGenError(error?.message || '无法创建资源任务，请检查输入后重试。'); }
  };

  const cancel = async (task: TaskEntry) => {
    if (!sessionId) return;
    await cancelWorkflow(task.taskId, sessionId).catch(() => undefined);
    controllers.current.get(task.resourceType)?.abort();
    clearWorkflowTask(scopeFor(task.resourceType));
    putTask(task.resourceType, { ...task, status: 'cancelled' });
  };

  const retry = async (task: TaskEntry) => {
    setGenError('');
    try {
      const started = await retryWorkflow(task.taskId);
      const scope = scopeFor(task.resourceType);
      const initial: WorkflowState = { taskId: started.task_id, workflowType: started.workflow_type, status: started.status, events: [], preview: '', elapsedMs: 0 };
      saveWorkflowTask({ ...scope, taskId: started.task_id, createdAt: Date.now(), resourceType: task.resourceType, mode: 'general_resource_generation' });
      putTask(task.resourceType, initial, Boolean(started.reused_existing));
      void monitor(task.resourceType, started.task_id, Boolean(started.reused_existing), initial);
    } catch { setGenError('重试任务创建失败，请稍后再试。'); }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between"><div><h2 className="font-display text-2xl font-bold text-surface-800">智能资源生成</h2><p className="text-surface-500 mt-1">每种资源都有独立任务、真实进度和可恢复状态</p></div></div>
      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2 space-y-6">
          <div className="bg-white rounded-2xl p-6 shadow-soft"><label className="block text-sm font-medium text-surface-700 mb-3">描述你的学习需求</label><textarea value={prompt} onChange={(event) => updatePrompt(event.target.value)} maxLength={500} className="w-full h-32 px-4 py-3 bg-surface-50 border border-surface-200 rounded-xl" /><div className="flex justify-between mt-3 text-xs text-surface-400"><span>支持 Markdown 输入</span><span>{prompt.length}/500</span></div></div>
          <div className="bg-white rounded-2xl p-6 shadow-soft"><div className="flex justify-between mb-4"><h3 className="font-semibold text-surface-700">选择资源类型</h3><span className="text-xs text-primary-600">已选择 {selectedTypes.length}/3 种</span></div><div className="grid grid-cols-2 gap-3">{resourceTypes.map((type) => { const Icon = type.icon; const selected = selectedTypes.includes(type.id); return <button key={type.id} onClick={() => toggleType(type.id)} disabled={!selected && selectedTypes.length >= 3} className={`p-4 rounded-xl border-2 text-left ${selected ? 'border-primary-500 bg-primary-50' : 'border-surface-200 bg-surface-50'} disabled:opacity-50`}><Icon size={20} className="mb-2 text-primary-600" /><p className="text-sm font-medium">{type.label}</p><p className="text-xs text-surface-500 mt-1">{type.description}</p></button>; })}</div></div>
          <button onClick={handleGenerate} disabled={!prompt.trim() || !selectedTypes.length || activeTasks.length > 0} className="w-full flex items-center justify-center gap-3 px-6 py-4 rounded-xl font-semibold text-lg bg-gradient-to-r from-primary-600 to-accent-600 text-white disabled:bg-surface-100 disabled:text-surface-400 disabled:cursor-not-allowed"><Sparkles size={22} />{activeTasks.length ? '任务进行中…' : `开始生成（${selectedTypes.length} 种资源）`}</button>
        </div>
        <div className="space-y-4">
          <div className="bg-white rounded-2xl p-5 shadow-soft">
            <div className="flex justify-between items-center">
              <h3 className="font-semibold text-surface-700">生成任务</h3>
              {Object.keys(workflows).length > 0 && <button className="text-xs text-primary-600" onClick={() => setProgressExpanded((value) => !value)}>{progressExpanded ? '收起' : '展开'}</button>}
            </div>
            {!Object.keys(workflows).length ? (
              <p className="text-sm text-surface-400 mt-3">提交后显示后端工作流状态。</p>
            ) : progressExpanded && (
              <div className="space-y-3 mt-4">
                {Object.values(workflows).map((task) => {
                  const stageLabel = latestStageLabel(task.events);
                  return (
                    <div key={task.resourceType} className="rounded-xl border border-surface-200 p-3">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">{labels[task.resourceType]}</span>
                        <span className="text-xs text-surface-500">{elapsed(task.elapsedMs)}</span>
                      </div>
                      <div className="mt-2 flex items-center gap-2 text-xs">
                        {isActiveWorkflowStatus(task.status) ? <Loader2 size={14} className="animate-spin text-primary-500" /> : task.status === 'completed' ? <CheckCircle2 size={14} className="text-success-500" /> : <XCircle size={14} className="text-error-500" />}
                        <span>
                          {task.status === 'completed' ? '已完成' : task.status === 'failed' ? '失败' : task.status === 'cancelled' ? '已取消' : task.status === 'queued' ? '排队中' : stageLabel || '生成中'}
                        </span>
                        {task.reusedExisting && <span className="text-surface-400">复用进行中的任务</span>}
                      </div>
                      {task.errorMessage && <p className="mt-2 text-xs text-error-600">{task.errorMessage}</p>}
                      {isActiveWorkflowStatus(task.status) && <button onClick={() => cancel(task)} className="mt-2 text-xs text-error-600">取消</button>}
                      {['failed', 'cancelled', 'expired'].includes(task.status) && <button onClick={() => retry(task)} className="mt-2 text-xs text-primary-600">重试</button>}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
          <div className="bg-surface-50 rounded-2xl p-5">
            <h4 className="text-sm font-medium text-surface-700 mb-3">生成记录</h4>
            {completedResources.length > 0 ? (
              <div className="grid grid-cols-1 gap-3">
                {completedResources.map((resource) => {
                  const typeMeta = resourceTypes.find((t) => t.id === resource.type);
                  const Icon = typeMeta?.icon || FileText;
                  const diffLabel: Record<string, string> = { easy: '基础', medium: '进阶', hard: '挑战' };
                  const diffBadge: Record<string, string> = { easy: 'bg-success-100 text-success-700', medium: 'bg-warning-100 text-warning-700', hard: 'bg-error-100 text-error-700' };
                  return (
                    <div
                      key={resource.id}
                      onClick={() => navigate(`/resources/${resource.id}`)}
                      className="bg-white rounded-xl p-3 cursor-pointer hover:shadow-md transition-shadow border border-surface-100"
                    >
                      <div className="flex items-start gap-3">
                        <div className="w-10 h-10 rounded-xl bg-primary-50 flex items-center justify-center flex-shrink-0">
                          <Icon size={18} className="text-primary-600" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-surface-800 truncate">{resource.title}</p>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-[11px] text-surface-400">{typeMeta?.label || resource.type}</span>
                            {resource.difficulty && (
                              <span className={`text-[10px] px-1.5 py-0.5 rounded ${diffBadge[resource.difficulty] || 'bg-surface-100 text-surface-500'}`}>
                                {diffLabel[resource.difficulty] || resource.difficulty}
                              </span>
                            )}
                          </div>
                        </div>
                        <ChevronRight size={14} className="text-surface-300 flex-shrink-0 mt-2" />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-surface-400">暂无生成记录，提交后自动展示</p>
            )}
          </div>
          {Object.values(workflows).some((task) => task.status === 'completed') && <button onClick={() => navigate('/resources')} className="w-full px-4 py-3 rounded-xl bg-success-50 text-success-700 text-sm font-medium">查看已生成资源</button>}
          {genError && <p className="p-3 rounded-xl bg-error-50 text-error-600 text-sm">{genError}</p>}
        </div>
      </div>
    </div>
  );
}
