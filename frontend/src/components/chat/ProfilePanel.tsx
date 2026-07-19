import { useState, useEffect, useCallback } from 'react';
import { authHeaders } from '../../api/client';
import { useNavigate } from 'react-router-dom';
import { disableProfileExtraction } from '../../api/learningPath';
import { startWorkflow } from '../../api/workflows';
import { useSubjectStore } from '../../store/subjectStore';
import { isSpecificLearningGoal, isUsableProfileValue, profileCompleteness } from '../../utils/profileCompleteness';
import { Sparkles, ChevronRight, CheckCircle2, Circle, AlertCircle } from 'lucide-react';

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

const LEVEL_STYLE: Record<string, string> = {
  advanced: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  intermediate: 'bg-neutral-100 text-neutral-700 border-neutral-200',
  beginner: 'bg-amber-50 text-amber-700 border-amber-200',
  none: 'bg-red-50 text-red-600 border-red-200',
};

function classifyEvidence(ev: string): string {
  if (!ev) return 'inference';
  if (ev.includes('探测')) return 'probe';
  if (ev.includes('行为') || ev.includes('观察')) return 'behavior';
  if (ev.includes('自述')) return 'self';
  return 'inference';
}

function DimSection({ dimKey, label, fact, rich, onProbe }: {
  dimKey: string; label: string; fact: string; rich: any; onProbe: () => void;
}) {
  const filled = dimKey === 'learning_goal' ? isSpecificLearningGoal(fact) : isUsableProfileValue(fact);
  const topics: any[] = rich?.topics || [];
  const gaps: any[] = rich?.gaps_found || [];
  const probes: any[] = rich?.probe_history || [];
  const summary: string = rich?.summary || '';

  const sortedTopics = [...topics].sort(
    (a, b) => (LEVEL_ORDER[b.level] || 0) - (LEVEL_ORDER[a.level] || 0)
  );

  return (
    <div className={`rounded-xl transition-all duration-300 ${
      filled 
        ? 'bg-white border border-neutral-100 hover:border-neutral-200 hover:shadow-sm p-3.5' 
        : 'p-3.5'
    }`}>
      {/* 维度标题行 */}
      <div className="flex items-center gap-3">
        {filled ? (
          <CheckCircle2 size={15} className="text-neutral-700 flex-shrink-0" />
        ) : (
          <Circle size={15} className="text-neutral-200 flex-shrink-0" />
        )}
        <span className={`text-[13px] font-semibold ${filled ? 'text-neutral-800' : 'text-neutral-400'}`}>
          {label}
        </span>
        {filled && topics.length > 0 && (
          <span className="text-[10px] font-medium text-neutral-400 ml-auto tabular-nums bg-neutral-50 px-2 py-0.5 rounded-full">
            {topics.filter((t: any) => t.confidence >= 0.7).length}/{topics.length} 高置信
          </span>
        )}
      </div>

      {filled && (
        <div className="mt-3 ml-[27px] space-y-3">
          {/* 分析摘要 */}
          {summary && summary !== fact && (
            <p className="text-[12px] text-neutral-500 leading-relaxed">{summary}</p>
          )}

          {/* 原始事实值 */}
          {sortedTopics.length === 0 && gaps.length === 0 && (
            <p className="text-[12px] text-neutral-600 leading-relaxed">{fact}</p>
          )}

          {/* Topic 列表 */}
          {sortedTopics.length > 0 && (
            <div className="space-y-2">
              {sortedTopics.slice(0, 5).map((t: any, i: number) => (
                <div key={i} className="bg-neutral-50/50 rounded-lg p-2.5">
                  <div className="flex items-center gap-2">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold border ${LEVEL_STYLE[t.level] || LEVEL_STYLE.none}`}>
                      {LEVEL_LABEL[t.level] || t.level || '未知'}
                    </span>
                    <span className="text-[12px] font-medium text-neutral-800 truncate">{t.topic}</span>
                  </div>
                  {t.detail && (
                    <p className="text-[11px] text-neutral-500 mt-1.5 leading-relaxed">{t.detail}</p>
                  )}
                  <div className="flex items-center gap-2 mt-1.5">
                    <span className={`text-[10px] font-medium ${t.confidence >= 0.7 ? 'text-emerald-600' : t.confidence >= 0.4 ? 'text-amber-600' : 'text-red-500'}`}>
                      {t.confidence >= 0.7 ? '高置信' : t.confidence >= 0.4 ? '中置信' : '低置信'}
                    </span>
                    <span className="text-neutral-300">·</span>
                    <span className="text-[10px] text-neutral-400">
                      {EVIDENCE_LABEL[classifyEvidence(t.evidence)] || '系统推断'}
                    </span>
                    {t.verified_by && (
                      <>
                        <span className="text-neutral-300">·</span>
                        <span className="text-[10px] text-neutral-400">经 {t.verified_by} 验证</span>
                      </>
                    )}
                  </div>
                </div>
              ))}
              {sortedTopics.length > 5 && (
                <span className="text-[11px] text-neutral-400">+{sortedTopics.length - 5} 项</span>
              )}
            </div>
          )}

          {/* 薄弱差距 */}
          {gaps.length > 0 && (
            <div className="space-y-1.5">
              <span className="text-[11px] font-semibold text-red-500 flex items-center gap-1.5">
                <AlertCircle size={12} />待加强
              </span>
              {gaps.slice(0, 3).map((g: any, i: number) => (
                <p key={i} className="text-[11px] text-neutral-500 leading-relaxed pl-5">
                  {typeof g === 'string' ? g : g.topic || g.gap || ''}
                  {g?.reason && <span className="text-neutral-400"> — {g.reason}</span>}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 未填充 */}
      {!filled && (
        <div className="mt-1.5 ml-[27px]">
          <p className="text-[11px] text-neutral-300">尚未收集</p>
        </div>
      )}
    </div>
  );
}

export default function ProfilePanel({ sessionId }: { sessionId: string }) {
  const nav = useNavigate();
  const subjectId = useSubjectStore((s) => s.activeSubject?.id ?? s.activeClassSubject?.subject);
  const [facts, setFacts] = useState<Record<string, string>>({});
  const [richFacts, setRichFacts] = useState<Record<string, any>>({});
  const [factsSessionId, setFactsSessionId] = useState('');
  const [loading, setLoading] = useState(Boolean(sessionId));
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    setFacts({});
    setRichFacts({});
    setFactsSessionId('');
    setLoading(Boolean(sessionId));
    if (!sessionId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await fetch(`/api/conversation-facts?sessionId=${sessionId}`, { headers: authHeaders() });
        const d = await r.json();
        if (!cancelled) {
          if (d.facts) setFacts(d.facts);
          if (d.rich_facts) setRichFacts(d.rich_facts);
          setFactsSessionId(sessionId);
        }
      } catch { /* ignore */ }
      finally { if (!cancelled) setLoading(false); }
    };
    poll();
    const iv = setInterval(poll, 3000);
    return () => { cancelled = true; clearInterval(iv); };
  }, [sessionId]);

  const currentFacts = factsSessionId === sessionId ? facts : {};
  const currentRichFacts = factsSessionId === sessionId ? richFacts : {};
  const filledCount = profileCompleteness(currentFacts, DIMS.map(d => d.key));
  const total = DIMS.length;
  const pct = Math.round((filledCount / total) * 100);
  const pathGenerationReady = isUsableProfileValue(currentFacts.target_course);

  const handleGenerate = useCallback(async () => {
    if (!pathGenerationReady || generating) return;
    setGenerating(true);
    try {
      await disableProfileExtraction(sessionId);
      const started = await startWorkflow('learning_path_generation', {
        sessionId,
        subjectId: subjectId || '',
        planMode: 'textbook',
        pathMode: 'textbook',
        draft: Object.fromEntries(
          DIMS.filter(d => d.key === 'learning_goal'
            ? isSpecificLearningGoal(currentFacts[d.key])
            : isUsableProfileValue(currentFacts[d.key])).map(d => [d.key, currentFacts[d.key]])
        ),
      });
      const taskId = started?.task_id || '';
      if (taskId) {
        sessionStorage.setItem('_pending_gen_task_id', taskId);
        sessionStorage.setItem('_pending_gen_session_id', sessionId || '');
      }
      console.log('[ProfilePanel] 导航到学习路径页, taskId:', taskId, 'sessionId:', sessionId);
      nav('/learning-path');
    } catch (e) {
      console.error('创建路径生成任务失败', e);
      setGenerating(false);
    }
  }, [pathGenerationReady, generating, sessionId, currentFacts, nav, subjectId]);

  return (
    <div className="flex flex-col h-full">
      {/* 顶部：进度 + 标题 */}
      <div className="flex-shrink-0 pb-5 border-b border-neutral-100">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[11px] font-semibold uppercase tracking-[0.2em] text-neutral-400">
            学情分析
          </h3>
          <span className="text-[12px] font-semibold text-neutral-700 tabular-nums">
            {loading ? '--' : filledCount}<span className="text-neutral-300 font-normal">/{total}</span>
          </span>
        </div>
        
        {/* 进度环 + 文字 */}
        <div className="flex items-center gap-5">
          {/* 环形进度 */}
          <div className="relative flex-shrink-0">
            <svg className="w-14 h-14 -rotate-90" viewBox="0 0 56 56">
              <circle cx="28" cy="28" r="24" fill="none" stroke="#f1f1f1" strokeWidth="4" />
              <circle cx="28" cy="28" r="24" fill="none" stroke="#1a1a1a" strokeWidth="4" strokeLinecap="round"
                strokeDasharray={`${(pct / 100) * 150.8} 150.8`}
                className="transition-all duration-1000 ease-out" />
            </svg>
            <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-neutral-800 tabular-nums">
              {loading ? '--' : pct}
            </span>
          </div>
          
          {/* 状态文字 */}
          <div className="flex-1 min-w-0">
            <p className="text-[13px] font-semibold text-neutral-800">
              {pathGenerationReady ? '已具备基础生成条件' : pct >= 50 ? '收集中' : '开始了解'}
            </p>
            <p className="text-[11px] text-neutral-500 mt-1 leading-relaxed">
              {pathGenerationReady
                ? filledCount === total ? '信息已完善，可以生成专属学习路径' : '继续补充信息可获得更精准的学习路径；缺失信息将采用默认安排'
                : `继续对话，还需完善 ${total - filledCount} 项信息`
              }
            </p>
          </div>
        </div>
      </div>

      {/* 维度分析列表 */}
      <div className="flex-1 overflow-y-auto min-h-0 -mx-5 px-5 py-3 space-y-1">
        {DIMS.map(d => (
          <DimSection
            key={d.key}
            dimKey={d.key}
            label={d.label}
            fact={currentFacts[d.key] || ''}
            rich={currentRichFacts[d.key]}
            onProbe={() => {}}
          />
        ))}
      </div>

      {/* 底部：生成按钮 */}
      <div className="flex-shrink-0 pt-4 border-t border-neutral-100">
        <button
          onClick={handleGenerate}
          disabled={!pathGenerationReady || generating || loading}
          className={`w-full h-12 rounded-xl text-[13px] font-semibold transition-all duration-300 flex items-center justify-center gap-2 ${
            pathGenerationReady && !generating && !loading
              ? 'bg-neutral-900 text-white hover:bg-neutral-800 shadow-lg shadow-neutral-200'
              : 'bg-neutral-100 text-neutral-400 cursor-not-allowed'
          }`}
        >
          {generating ? (
            <>
              <div className="w-4 h-4 border-2 border-neutral-400 border-t-transparent rounded-full animate-spin" />
              正在生成…
            </>
          ) : pathGenerationReady ? (
            <>
              <Sparkles size={15} />
              生成学习路径
              <ChevronRight size={15} />
            </>
          ) : (
            '继续对话以完善分析…'
          )}
        </button>
      </div>
    </div>
  );
}
