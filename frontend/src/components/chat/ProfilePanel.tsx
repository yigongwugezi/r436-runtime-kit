import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { createPathGenerationTask } from '../../api/learningPath';
import { readWorkflow } from '../../api/workflows';

const DIMS = [
  { key: 'background', label: '专业/年级' },
  { key: 'target_course', label: '目标课程' },
  { key: 'knowledge_base', label: '已有基础' },
  { key: 'weak_points', label: '薄弱点' },
  { key: 'learning_goal', label: '学习目标' },
  { key: 'time_budget', label: '时间安排' },
  { key: 'preference', label: '学习偏好' },
];

const LEVEL_LABEL: Record<string, string> = {
  none: '未掌握', beginner: '入门', intermediate: '中等', advanced: '精通',
};
const LEVEL_ORDER: Record<string, number> = {
  none: 0, beginner: 1, intermediate: 2, advanced: 3,
};

const EVIDENCE_LABEL: Record<string, string> = {
  probe: '探测验证', self: '学生自述', behavior: '行为观察', inference: '系统推断',
};

function classifyEvidence(ev: string): string {
  if (!ev) return 'inference';
  if (ev.includes('探测')) return 'probe';
  if (ev.includes('行为') || ev.includes('观察')) return 'behavior';
  if (ev.includes('自述')) return 'self';
  return 'inference';
}

function isEmpty(v: string) {
  return !v || v === '未提及' || v === '待补充' || v === '未知' || v === '';
}

function DimSection({ dimKey, label, fact, rich, onProbe }: {
  dimKey: string; label: string; fact: string; rich: any; onProbe: () => void;
}) {
  const filled = !isEmpty(fact);
  const topics: any[] = rich?.topics || [];
  const gaps: any[] = rich?.gaps_found || [];
  const probes: any[] = rich?.probe_history || [];
  const summary: string = rich?.summary || '';

  // 按掌握度排序 topic
  const sortedTopics = [...topics].sort(
    (a, b) => (LEVEL_ORDER[b.level] || 0) - (LEVEL_ORDER[a.level] || 0)
  );

  return (
    <div className="border-b border-surface-100 last:border-0">
      {/* 维度标题行 */}
      <div className="flex items-center gap-2 px-1 py-2.5">
        <div className={`flex-shrink-0 w-2 h-2 rounded-full ${
          filled ? 'bg-primary-500' : 'bg-surface-200'
        }`} />
        <span className={`text-xs font-medium ${filled ? 'text-surface-700' : 'text-surface-400'}`}>
          {label}
        </span>
        {filled && topics.length > 0 && (
          <span className="text-[10px] text-surface-400 ml-auto">
            {topics.filter(t => t.confidence >= 0.7).length}/{topics.length} 高置信
          </span>
        )}
      </div>

      {filled && (
        <div className="pb-3 pl-5 space-y-2">
          {/* 分析摘要 */}
          {summary && summary !== fact && (
            <p className="text-[11px] text-surface-500 leading-relaxed">{summary}</p>
          )}

          {/* 原始事实值 — 当尚无结构化分析时兜底展示 */}
          {sortedTopics.length === 0 && gaps.length === 0 && (
            <p className="text-[11px] text-surface-600 leading-relaxed">{fact}</p>
          )}

          {/* 发现的 topic 及掌握度 */}
          {sortedTopics.length > 0 && (
            <div className="space-y-1.5">
              {sortedTopics.slice(0, 5).map((t: any, i: number) => (
                <div key={i} className="text-[11px]">
                  <div className="flex items-center gap-1.5">
                    <span className={`font-medium ${
                      t.level === 'advanced' ? 'text-green-600' :
                      t.level === 'intermediate' ? 'text-primary-600' :
                      t.level === 'beginner' ? 'text-amber-600' : 'text-red-500'
                    }`}>
                      {LEVEL_LABEL[t.level] || t.level || '未知'}
                    </span>
                    <span className="text-surface-700 truncate">{t.topic}</span>
                  </div>
                  {t.detail && (
                    <p className="text-surface-400 mt-0.5 leading-relaxed">{t.detail}</p>
                  )}
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className={`text-[10px] ${t.confidence >= 0.7 ? 'text-green-500' : 'text-amber-500'}`}>
                      {t.confidence >= 0.7 ? '高置信' : t.confidence >= 0.4 ? '中置信' : '低置信'}
                    </span>
                    <span className="text-[10px] text-surface-400">
                      {EVIDENCE_LABEL[classifyEvidence(t.evidence)] || '系统推断'}
                    </span>
                    {t.verified_by && (
                      <span className="text-[10px] text-surface-400">
                        经 {t.verified_by} 验证
                      </span>
                    )}
                  </div>
                </div>
              ))}
              {sortedTopics.length > 5 && (
                <span className="text-[10px] text-surface-400">
                  +{sortedTopics.length - 5} 项
                </span>
              )}
            </div>
          )}

          {/* 发现的薄弱差距 */}
          {gaps.length > 0 && (
            <div className="space-y-0.5">
              <span className="text-[10px] text-red-500 font-medium">待加强</span>
              {gaps.slice(0, 3).map((g: any, i: number) => (
                <p key={i} className="text-[10px] text-surface-500 leading-relaxed">
                  {typeof g === 'string' ? g : g.topic || g.gap || ''}
                  {g?.reason && <span className="text-surface-400"> — {g.reason}</span>}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 未填充时的状态 */}
      {!filled && (
        <div className="pb-3 pl-5">
          <p className="text-[10px] text-surface-400">尚未收集</p>
        </div>
      )}
    </div>
  );
}

export default function ProfilePanel({ sessionId }: { sessionId: string }) {
  const nav = useNavigate();
  const [facts, setFacts] = useState<Record<string, string>>({});
  const [richFacts, setRichFacts] = useState<Record<string, any>>({});
  const [generating, setGenerating] = useState(false);
  const generateCancelledRef = useRef(false);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await fetch(`/api/conversation-facts?sessionId=${sessionId}`);
        const d = await r.json();
        if (!cancelled) {
          if (d.facts) setFacts(d.facts);
          if (d.rich_facts) setRichFacts(d.rich_facts);
        }
      } catch { /* ignore */ }
    };
    poll();
    const iv = setInterval(poll, 3000);
    return () => { cancelled = true; clearInterval(iv); };
  }, [sessionId]);

  const filledCount = DIMS.filter(d => !isEmpty(facts[d.key] || '')).length;
  const total = DIMS.length;
  const pct = Math.round((filledCount / total) * 100);
  const ready = filledCount >= 6;

  /** 轮询等待 workflow 完成，返回 true=成功 false=失败/超时 */
  const pollTaskUntilDone = useCallback(async (taskId: string): Promise<boolean> => {
    const TIMEOUT = 120_000; // 2 分钟
    const INTERVAL = 1500;
    const deadline = Date.now() + TIMEOUT;
    while (!generateCancelledRef.current && Date.now() < deadline) {
      await new Promise(r => setTimeout(r, INTERVAL));
      if (generateCancelledRef.current) return false;
      try {
        const res = await readWorkflow(taskId, sessionId);
        // readWorkflow 可能返回 { task: { status } } 或直接 { status }
        const status = res?.task?.status || res?.status || '';
        if (status === 'completed') return true;
        if (['failed', 'cancelled', 'expired'].includes(status)) return false;
      } catch { /* 网络错误，重试 */ }
    }
    return false; // 超时或取消
  }, [sessionId]);

  const handleGenerate = useCallback(async () => {
    if (!ready || generating) return;
    setGenerating(true);
    generateCancelledRef.current = false;
    try {
      const { task } = await createPathGenerationTask({
        sessionId,
        subjectId: '',
        planMode: 'textbook',
        pathMode: 'textbook',
        draft: Object.fromEntries(
          DIMS.filter(d => !isEmpty(facts[d.key] || '')).map(d => [d.key, facts[d.key]])
        ),
      });
      if (task?.task_id) {
        const ok = await pollTaskUntilDone(task.task_id);
        if (generateCancelledRef.current) return;
        if (!ok) {
          setGenerating(false); // 失败/超时 → 按钮恢复可点击，用户可重试
          return;
        }
      }
      nav('/learning-path');
    } catch (e) {
      console.error('生成路径失败', e);
      setGenerating(false);
    }
  }, [ready, generating, sessionId, facts, nav, pollTaskUntilDone]);

  // 组件卸载时取消正在进行的轮询
  useEffect(() => () => { generateCancelledRef.current = true; }, []);

  return (
    <div className="flex flex-col h-full">
      {/* 顶部：进度 + 标题 */}
      <div className="flex-shrink-0 pb-3 border-b border-surface-100">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-semibold text-surface-400 uppercase tracking-wider">
            学情分析
          </h3>
          <span className="text-[11px] text-surface-400">{filledCount}/{total} 项</span>
        </div>
        <div className="relative h-1.5 bg-surface-100 rounded-full overflow-hidden">
          <div
            className="absolute inset-y-0 left-0 bg-primary-500 rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* 维度分析列表 — 滚动 */}
      <div className="flex-1 overflow-y-auto min-h-0 -mx-5 px-5">
        {DIMS.map(d => (
          <DimSection
            key={d.key}
            dimKey={d.key}
            label={d.label}
            fact={facts[d.key] || ''}
            rich={richFacts[d.key]}
            onProbe={() => {}}
          />
        ))}
      </div>

      {/* 底部：生成按钮 */}
      <div className="flex-shrink-0 pt-3 border-t border-surface-100">
        <button
          onClick={handleGenerate}
          disabled={!ready || generating}
          className={`w-full py-2.5 rounded-lg text-sm font-medium transition-all ${
            ready && !generating
              ? 'bg-primary-600 text-white hover:bg-primary-700'
              : 'bg-surface-100 text-surface-400 cursor-not-allowed'
          }`}
        >
          {generating ? '正在生成…' : ready ? '生成学习路径' : '继续对话以完善分析…'}
        </button>
      </div>
    </div>
  );
}
