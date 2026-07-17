// @ts-nocheck
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckCircle2, Circle, Loader2, AlertCircle, RefreshCw, XCircle, ArrowRight, ChevronLeft, Target } from 'lucide-react';
import { upsertPlanningDraft, getPlanningDraft, listPlanningDrafts, type PlanningDraft, type DraftCompleteness } from '../../api/learningPath';
import { createPathGenerationTask, getWorkflowTask, cancelWorkflowTask, type WorkflowTask } from '../../api/learningPath';
import { useChatStore } from '../../store/chatStore';

interface Props {
  sessionId: string;
  subjectId: string;
  subjectName: string;
  profileV2: any;
  onPathGenerated: (pathId: string) => void;
  planMode?: string;
  pathMode?: string;
  totalDays?: number;
  weekends?: boolean;
  dynamicAdjust?: boolean;
  reviewEnabled?: boolean;
}

const PLANNING_FIELDS = [
  { key: 'topic', label: '学习主题', placeholder: '例如：数据结构', maxLen: 256 },
  { key: 'goal', label: '学习目标', placeholder: '例如：课程考试、系统掌握、项目实践、快速入门', maxLen: 64 },
  { key: 'currentLevel', label: '当前基础', placeholder: '例如：零基础、了解部分概念、有编程基础、系统学过', maxLen: 64 },
  { key: 'dailyTime', label: '每日时间', placeholder: '例如：90分钟、2小时', maxLen: 64 },
  { key: 'targetDuration', label: '计划周期', placeholder: '例如：8周、2个月', maxLen: 64 },
  { key: 'resourcePreferences', label: '资源偏好', placeholder: '视频、讲义、练习、项目、思维导图', maxLen: 256 },
] as const;

const SOURCE_LABELS: Record<string, string> = {
  profile: '来自长期画像',
  subject: '来自当前学科',
  conversation: '来自当前对话',
  user: '用户本次填写',
};

const FIELD_SOURCES: Record<string, string> = {
  topic: 'conversation',
  goal: 'profile',
  currentLevel: 'profile',
  dailyTime: 'profile',
  targetDuration: 'conversation',
  resourcePreferences: 'profile',
};

function generateDraftId(sessionId: string, subjectId: string): string {
  const base = `${sessionId}_${subjectId || 'default'}`;
  let hash = 0;
  for (let i = 0; i < base.length; i++) {
    hash = ((hash << 5) - hash) + base.charCodeAt(i);
    hash |= 0;
  }
  return `draft_${Math.abs(hash).toString(36)}`;
}

export default function PlanningWizard({ sessionId, subjectId, subjectName, profileV2, onPathGenerated, planMode, pathMode, totalDays, weekends, dynamicAdjust, reviewEnabled }: Props) {
  const nav = useNavigate();
  const [draftId] = useState(() => generateDraftId(sessionId, subjectId));
  const [draft, setDraft] = useState<PlanningDraft | null>(null);
  const [completeness, setCompleteness] = useState<DraftCompleteness | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [showConfirm, setShowConfirm] = useState(false);

  // Workflow state
  const [task, setTask] = useState<WorkflowTask | null>(null);
  const [taskError, setTaskError] = useState('');
  const sseRef = useRef<EventSource | null>(null);

  // Load existing draft or create new one
  useEffect(() => {
    if (!sessionId) return;
    (async () => {
      setLoading(true);
      try {
        const res = await listPlanningDrafts({ sessionId, subjectId });
        if (res.ok && res.draft) {
          setDraft(res.draft);
          setCompleteness(await getCompleteness(res.draft));
        } else {
          // Create new draft with pre-filled values from profile/context
          await createNewDraft();
        }
      } catch (e: any) {
        setError(e?.message || '加载失败');
      } finally {
        setLoading(false);
      }
    })();
  }, [sessionId, subjectId]);

  const createNewDraft = async () => {
    const prefill = getPrefillValues();
    const res = await upsertPlanningDraft({
      draftId,
      sessionId,
      subjectId,
      ...prefill,
    });
    if (res.ok) {
      setDraft(res.draft);
      setCompleteness(res.completeness);
    }
  };

  const getPrefillValues = () => {
    const vals: Record<string, any> = {};
    const subj = profileV2?.subject_context || {};
    const general = profileV2?.general_states || [];

    // Goal from profile
    if (subj.learning_goal) { vals.goal = subj.learning_goal; FIELD_SOURCES.goal = 'profile'; }

    // Current level
    const levelState = general.find((s: any) => s?.key === 'current_level' || s?.key === 'mastery_level');
    if (levelState?.label) { vals.currentLevel = levelState.label; FIELD_SOURCES.currentLevel = 'profile'; }

    // Daily time
    if (subj.daily_minutes) { vals.dailyTime = `${subj.daily_minutes}分钟`; FIELD_SOURCES.dailyTime = 'profile'; }
    else if (subj.time_budget) { vals.dailyTime = subj.time_budget; FIELD_SOURCES.dailyTime = 'profile'; }

    // Resource preferences
    const prefs = subj.resource_preferences || subj.content_preferences || [];
    if (prefs.length) { vals.resourcePreferences = prefs; FIELD_SOURCES.resourcePreferences = 'profile'; }

    // Topic from subject name
    if (subjectName) { vals.topic = subjectName; FIELD_SOURCES.topic = 'subject'; }

    return vals;
  };

  const getCompleteness = async (d: PlanningDraft) => {
    const res = await upsertPlanningDraft({
      draftId: d.draftId,
      sessionId,
      subjectId,
      topic: d.topic,
      goal: d.goal,
      currentLevel: d.currentLevel,
      dailyTime: d.dailyTime,
      targetDuration: d.targetDuration,
      resourcePreferences: d.resourcePreferences,
    });
    return res.completeness;
  };

  const handleFieldChange = async (key: string, value: string | string[]) => {
    setSaving(true);
    try {
      const patch: Record<string, any> = { draftId, sessionId, subjectId, [key]: value };
      const res = await upsertPlanningDraft(patch);
      if (res.ok) {
        setDraft(res.draft);
        setCompleteness(res.completeness);
        FIELD_SOURCES[key] = 'user';
      }
    } catch (e: any) {
      setError(e?.message || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleResourcePrefChange = (pref: string) => {
    const current = draft?.resourcePreferences || [];
    const next = current.includes(pref) ? current.filter(p => p !== pref) : [...current, pref];
    handleFieldChange('resourcePreferences', next);
  };

  const handleConfirm = async () => {
    if (!draft || !completeness || completeness.percent < 100) return;
    setShowConfirm(false);
    setTaskError('');
    try {
      // Mark draft as confirmed
      await upsertPlanningDraft({ draftId, sessionId, subjectId, confirmed: true });

      // Create workflow task
      const res = await createPathGenerationTask({
        sessionId,
        subjectId,
        planMode: planMode || '',
        pathMode: pathMode || '',
        totalDays: totalDays || 30,
        weekends: weekends !== false,
        dynamicAdjust: dynamicAdjust !== false,
        reviewEnabled: reviewEnabled !== false,
        draft: {
          topic: draft.topic,
          goal: draft.goal,
          currentLevel: draft.currentLevel,
          dailyTime: draft.dailyTime,
          targetDuration: draft.targetDuration,
          resourcePreferences: draft.resourcePreferences,
        },
      });
      if (res.ok && res.task) {
        setTask(res.task);
        startSSE(res.task.task_id);
      } else {
        setTaskError('创建任务失败');
      }
    } catch (e: any) {
      setTaskError(e?.message || '确认失败');
    }
  };

  const startSSE = (taskId: string) => {
    if (sseRef.current) sseRef.current.close();
    const es = new EventSource(`/api/workflows/${taskId}/events`);
    sseRef.current = es;
    const handleEvent = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (data.status) {
          setTask((prev) => prev ? { ...prev, status: data.status, current_stage: data.label || prev.current_stage } : prev);
        }
      } catch {}
    };
    es.onmessage = handleEvent;
    es.addEventListener('stage_started', handleEvent as any);
    es.addEventListener('stage_completed', handleEvent as any);
    es.onerror = () => {
      es.close();
      // Fallback: poll for status
      pollTaskStatus(taskId);
    };
  };

  const pollTaskStatus = async (taskId: string) => {
    try {
      const res = await getWorkflowTask(taskId);
      if (res.ok && res.task) {
        setTask(res.task);
        if (res.task.status === 'completed' && res.task.result?.data?.path?.id) {
          onPathGenerated(res.result.data.path.id);
        } else if (res.task.status === 'failed' || res.task.status === 'cancelled') {
          // stop polling
          return;
        } else {
          setTimeout(() => pollTaskStatus(taskId), 2000);
        }
      }
    } catch {}
  };

  const handleCancel = async () => {
    if (!task?.task_id) return;
    try {
      await cancelWorkflowTask(task.task_id);
      setTask((prev) => prev ? { ...prev, status: 'cancelled' } : prev);
    } catch {}
  };

  const handleRetry = () => {
    setTask(null);
    setTaskError('');
    handleConfirm();
  };

  const handleReset = () => {
    setTask(null);
    setTaskError('');
    setShowConfirm(false);
    setDraft(null);
    createNewDraft();
  };

  // ── Render: Loading ──
  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-primary-500" />
      </div>
    );
  }

  // ── Render: Task in progress ──
  if (task) {
    const statusConfig: Record<string, { icon: any; color: string; label: string }> = {
      queued: { icon: Circle, color: 'text-surface-400', label: '排队中' },
      running: { icon: Loader2, color: 'text-primary-500 animate-spin', label: '生成中' },
      completed: { icon: CheckCircle2, color: 'text-green-500', label: '已完成' },
      failed: { icon: XCircle, color: 'text-red-500', label: '失败' },
      cancelled: { icon: XCircle, color: 'text-surface-400', label: '已取消' },
      expired: { icon: AlertCircle, color: 'text-amber-500', label: '已过期' },
    };
    const cfg = statusConfig[task.status] || statusConfig.queued;
    const Icon = cfg.icon;
    const isTerminal = ['completed', 'failed', 'cancelled', 'expired'].includes(task.status);

    return (
      <div className="max-w-lg mx-auto flex-1 flex flex-col items-center justify-center space-y-6 py-12">
        <div className={`p-6 rounded-full ${task.status === 'running' ? 'bg-primary-50' : task.status === 'completed' ? 'bg-green-50' : 'bg-surface-100'}`}>
          <Icon size={48} className={cfg.color} />
        </div>
        <div className="text-center">
          <h3 className="text-lg font-semibold text-surface-800">{cfg.label}</h3>
          {task.current_stage && <p className="text-sm text-surface-500 mt-1">{task.current_stage}</p>}
          {task.metadata?.reused_existing && <p className="text-xs text-surface-400 mt-1">复用已有任务</p>}
        </div>
        {task.safe_error_message && (
          <div className="px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600">{task.safe_error_message}</div>
        )}
        {isTerminal && task.status === 'completed' && (
          <button onClick={() => task.result?.data?.path?.id && onPathGenerated(task.result.data.path.id)}
            className="px-6 py-2.5 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 transition-colors">
            查看学习路径
          </button>
        )}
        {isTerminal && task.status === 'failed' && (
          <div className="flex gap-3">
            <button onClick={handleRetry} className="px-5 py-2 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700">重试</button>
            <button onClick={handleReset} className="px-5 py-2 border border-surface-300 rounded-xl text-surface-600 hover:bg-surface-50">返回修改</button>
          </div>
        )}
        {isTerminal && task.status === 'cancelled' && (
          <button onClick={handleReset} className="px-5 py-2 border border-surface-300 rounded-xl text-surface-600 hover:bg-surface-50">重新开始</button>
        )}
        {!isTerminal && (
          <button onClick={handleCancel} className="px-5 py-2 border border-red-200 text-red-600 rounded-xl hover:bg-red-50 text-sm">取消生成</button>
        )}
      </div>
    );
  }

  // ── Render: Confirmation card ──
  if (showConfirm && draft && completeness) {
    return (
      <div className="max-w-xl mx-auto flex-1 flex flex-col space-y-6 py-6">
        <div className="flex items-center gap-3">
          <button onClick={() => setShowConfirm(false)} className="p-1.5 hover:bg-surface-100 rounded-lg"><ChevronLeft size={20} /></button>
          <h2 className="font-display text-xl font-bold text-surface-800">确认学习路径规划</h2>
        </div>

        <div className="bg-white rounded-2xl p-6 shadow-soft space-y-4">
          <h3 className="font-medium text-surface-700">请确认以下信息后生成路径</h3>
          {PLANNING_FIELDS.map(({ key, label }) => {
            const val = key === 'resourcePreferences'
              ? (draft.resourcePreferences || []).join('、') || '未选择'
              : (draft as any)[key] || '未填写';
            return (
              <div key={key} className="flex justify-between items-center py-2 border-b border-surface-100 last:border-0">
                <span className="text-sm text-surface-500">{label}</span>
                <span className="text-sm font-medium text-surface-800 text-right max-w-[60%]">{val}</span>
              </div>
            );
          })}
          <div className="flex items-center gap-2 pt-2">
            <span className="text-xs text-surface-400">信息完整度</span>
            <span className="text-xs font-medium text-green-600">{completeness.filled}/{completeness.total} 项</span>
          </div>
        </div>

        {taskError && (
          <div className="px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600">{taskError}</div>
        )}

        <div className="flex gap-3">
          <button onClick={() => setShowConfirm(false)} className="flex-1 py-3 border border-surface-300 rounded-xl text-surface-600 font-medium hover:bg-surface-50">返回修改</button>
          <button onClick={handleConfirm} className="flex-1 py-3 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 flex items-center justify-center gap-2">
            确认并生成 <ArrowRight size={16} />
          </button>
        </div>
      </div>
    );
  }

  // ── Render: Field collection form ──
  const filled = completeness?.filled || 0;
  const total = completeness?.total || 6;
  const isComplete = completeness?.percent === 100;

  return (
    <div className="max-w-2xl mx-auto flex-1 flex flex-col space-y-6 py-6">
      <div>
        <h2 className="font-display text-2xl font-bold text-surface-800">学习路径规划</h2>
        <p className="text-surface-500 mt-1">填写以下信息，系统将为你生成个性化学习路径</p>
      </div>

      {/* Completeness bar */}
      <div className="flex items-center gap-3">
        <div className="flex-1 h-2 bg-surface-100 rounded-full overflow-hidden">
          <div className="h-full bg-primary-500 rounded-full transition-all" style={{ width: `${completeness?.percent || 0}%` }} />
        </div>
        <span className="text-xs font-medium text-surface-500">{filled}/{total} 项</span>
      </div>

      {/* Fields */}
      <div className="bg-white rounded-2xl p-6 shadow-soft space-y-5">
        {PLANNING_FIELDS.map(({ key, label, placeholder }) => {
          const source = FIELD_SOURCES[key] || 'user';
          const sourceLabel = SOURCE_LABELS[source] || '';

          if (key === 'resourcePreferences') {
            const prefs = ['视频', '讲义', '练习', '项目', '思维导图'];
            const selected = draft?.resourcePreferences || [];
            return (
              <div key={key}>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-surface-700">{label}</label>
                  {sourceLabel && <span className="text-[10px] px-2 py-0.5 bg-surface-100 text-surface-400 rounded-full">{sourceLabel}</span>}
                </div>
                <div className="flex flex-wrap gap-2">
                  {prefs.map((pref) => (
                    <button key={pref} onClick={() => handleResourcePrefChange(pref)}
                      className={`text-xs px-3 py-1.5 rounded-full border transition-all ${selected.includes(pref) ? 'border-primary-300 bg-primary-50 text-primary-700' : 'border-surface-200 text-surface-500 hover:border-surface-300'}`}
                    >{pref}</button>
                  ))}
                </div>
              </div>
            );
          }

          return (
            <div key={key}>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-sm font-medium text-surface-700">{label}</label>
                {sourceLabel && <span className="text-[10px] px-2 py-0.5 bg-surface-100 text-surface-400 rounded-full">{sourceLabel}</span>}
              </div>
              <input
                value={(draft as any)?.[key] || ''}
                onChange={e => handleFieldChange(key, e.target.value)}
                placeholder={placeholder}
                className="w-full px-4 py-2.5 rounded-xl border border-surface-200 text-sm text-surface-800 placeholder-surface-400 focus:outline-none focus:ring-2 focus:ring-primary-400"
              />
            </div>
          );
        })}
      </div>

      {error && (
        <div className="px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600 flex items-center gap-2">
          <AlertCircle size={16} /> {error}
        </div>
      )}

      <button onClick={() => setShowConfirm(true)} disabled={!isComplete}
        className="w-full py-3.5 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
      >
        {saving ? <><Loader2 size={16} className="animate-spin" />保存中…</> : isComplete ? '预览并确认' : `还差 ${total - filled} 项信息`}
      </button>
    </div>
  );
}
