import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { BrainCircuit, CheckCircle2, ChevronRight, Clapperboard, Clock, FileQuestion, FileText, Loader2, Presentation, Sparkles, XCircle } from 'lucide-react';
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
  readWorkflowTask,
  saveWorkflowTask,
  workflowStateFromEvent,
  type WorkflowTaskScope,
} from '../utils/workflowTaskRecovery';

type TaskEntry = WorkflowState & { resourceType: GeneralResourceType; reusedExisting?: boolean };

const resourceTypes: Array<{ id: GeneralResourceType; label: string; icon: typeof FileText; description: string }> = [
  { id: 'lecture', label: '课程讲义', icon: FileText, description: '结构化的知识讲解' },
  { id: 'video', label: '教学视频', icon: Clapperboard, description: '可视化教学讲解' },
  { id: 'mindmap', label: '思维导图', icon: BrainCircuit, description: '可渲染的知识结构图' },
  { id: 'practice', label: '实操案例', icon: FileText, description: '含代码示例的实践任务' },
  { id: 'quiz', label: '练习题库', icon: FileQuestion, description: '含答案与解析的自测题' },
  { id: 'ppt', label: 'PPT 演示', icon: Presentation, description: '可下载的本地演示文稿' },
  { id: 'manim', label: 'Manim 动画', icon: Clapperboard, description: '需要本地 Manim 渲染环境' },
];

const labels = Object.fromEntries(resourceTypes.map((item) => [item.id, item.label])) as Record<GeneralResourceType, string>;

function normalizeTypes(value: string | null): GeneralResourceType[] {
  const aliases: Record<string, GeneralResourceType> = { 'mind-map': 'mindmap', mind_map: 'mindmap', case_study: 'practice' };
  const known = new Set<GeneralResourceType>(['lecture', 'mindmap', 'quiz', 'ppt', 'video', 'animation', 'manim', 'reading', 'practice']);
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
  const restoring = useRef(new Set<string>());
  const topicFingerprint = useMemo(() => fingerprint(prompt), [prompt]);

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

  const monitor = useCallback(async (resourceType: GeneralResourceType, taskId: string, reusedExisting = false, initial?: WorkflowState) => {
    const scope = scopeFor(resourceType);
    const controller = new AbortController();
    controllers.current.get(resourceType)?.abort();
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
      if (!(error instanceof DOMException && error.name === 'AbortError')) setGenError('资源任务连接失败，请重试该类型。');
    } finally {
      const latest = await readWorkflow(taskId, sessionId).catch(() => null);
      if (latest) {
        putTask(resourceType, {
          taskId, workflowType: latest.workflow_type, status: latest.status, events: [], preview: '', elapsedMs: latest.elapsed_ms || 0, result: latest.result,
          errorMessage: latest.safe_error_message || '',
        }, reusedExisting);
        if (latest.status === 'completed') bumpDataVersion();
        if (isTerminalWorkflowStatus(latest.status)) clearWorkflowTask(scope);
      } else {
        clearWorkflowTask(scope);
      }
      controllers.current.delete(resourceType);
    }
  }, [bumpDataVersion, putTask, scopeFor, sessionId]);

  useEffect(() => {
    if (!sessionId || !prompt.trim()) return undefined;
    let active = true;
    for (const resourceType of selectedTypes) {
      const scope = scopeFor(resourceType);
      const record = readWorkflowTask(scope);
      if (!record || restoring.current.has(record.taskId)) continue;
      restoring.current.add(record.taskId);
      void (async () => {
        try {
          const task = await readWorkflow(record.taskId, sessionId);
          if (!active || task.workflow_type !== scope.workflowType) { clearWorkflowTask(scope); return; }
          const restored: WorkflowState = {
            taskId: record.taskId, workflowType: task.workflow_type, status: task.status,
            events: [], preview: '', elapsedMs: task.elapsed_ms || 0, result: task.result,
            errorMessage: task.safe_error_message || '',
          };
          putTask(resourceType, restored);
          if (isActiveWorkflowStatus(task.status)) await monitor(resourceType, record.taskId, false, restored);
          else {
            if (task.status === 'completed') bumpDataVersion();
            if (isTerminalWorkflowStatus(task.status)) clearWorkflowTask(scope);
          }
        } catch {
          if (active) clearWorkflowTask(scope);
        } finally { restoring.current.delete(record.taskId); }
      })();
    }
    return () => { active = false; };
  }, [bumpDataVersion, monitor, prompt, putTask, scopeFor, selectedTypes, sessionId]);

  useEffect(() => () => controllers.current.forEach((controller) => controller.abort()), []);

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
          <div className="bg-white rounded-2xl p-5 shadow-soft"><div className="flex justify-between items-center"><h3 className="font-semibold text-surface-700">生成任务</h3>{Object.keys(workflows).length > 0 && <button className="text-xs text-primary-600" onClick={() => setProgressExpanded((value) => !value)}>{progressExpanded ? '收起' : '展开'}</button>}</div>{!Object.keys(workflows).length ? <p className="text-sm text-surface-400 mt-3">提交后显示后端工作流状态。</p> : progressExpanded && <div className="space-y-3 mt-4">{Object.values(workflows).map((task) => <div key={task.resourceType} className="rounded-xl border border-surface-200 p-3"><div className="flex items-center justify-between"><span className="text-sm font-medium">{labels[task.resourceType]}</span><span className="text-xs text-surface-500">{elapsed(task.elapsedMs)}</span></div><div className="mt-2 flex items-center gap-2 text-xs">{isActiveWorkflowStatus(task.status) ? <Loader2 size={14} className="animate-spin text-primary-500" /> : task.status === 'completed' ? <CheckCircle2 size={14} className="text-success-500" /> : <XCircle size={14} className="text-error-500" />}<span>{task.status === 'completed' ? '已完成' : task.status === 'failed' ? '失败' : task.status === 'cancelled' ? '已取消' : task.status === 'queued' ? '排队中' : '生成中'}</span>{task.reusedExisting && <span className="text-surface-400">复用进行中的任务</span>}</div>{task.errorMessage && <p className="mt-2 text-xs text-error-600">{task.errorMessage}</p>}{isActiveWorkflowStatus(task.status) && <button onClick={() => cancel(task)} className="mt-2 text-xs text-error-600">取消</button>}{['failed', 'cancelled', 'expired'].includes(task.status) && <button onClick={() => retry(task)} className="mt-2 text-xs text-primary-600">重试</button>}</div>)}</div>}</div>
          <div className="bg-surface-50 rounded-2xl p-5"><h4 className="text-sm font-medium text-surface-700 mb-3">快捷模板</h4>{['CNN 原理学习', 'Transformer 架构', 'Python 项目实战'].map((template) => <button key={template} onClick={() => updatePrompt(`${template}相关知识点和代码示例`)} className="w-full flex justify-between px-3 py-2 bg-white rounded-lg text-sm text-surface-600 mb-2">{template}<ChevronRight size={14} /></button>)}</div>
          {Object.values(workflows).some((task) => task.status === 'completed') && <button onClick={() => navigate('/resources')} className="w-full px-4 py-3 rounded-xl bg-success-50 text-success-700 text-sm font-medium">查看已生成资源</button>}
          {genError && <p className="p-3 rounded-xl bg-error-50 text-error-600 text-sm">{genError}</p>}
        </div>
      </div>
    </div>
  );
}
