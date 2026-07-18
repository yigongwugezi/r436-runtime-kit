import { useEffect, useState } from 'react';
import { acceptPendingRevision, getPendingRevision, rejectPendingRevision } from '../../api/learningPath';
import { useChatStore } from '../../store/chatStore';

export default function RevisionProposalCard({ sessionId, subjectId, pathId }: { sessionId: string; subjectId: string; pathId: string }) {
  const [proposal, setProposal] = useState<any>(null);
  const [status, setStatus] = useState<'pending'|'confirming'|'confirmed'|'rejecting'|'rejected'|'error'>('pending');
  const [error, setError] = useState('');
  const bump = useChatStore(s => s.bumpDataVersion);
  useEffect(() => { if (sessionId && subjectId && pathId) getPendingRevision(sessionId, subjectId, pathId).then(r => setProposal(r.pending_revision)).catch(() => {}); }, [sessionId, subjectId, pathId]);
  if (!proposal || proposal.status !== 'ready_for_review') return null;
  const run = async (kind: 'confirm'|'reject') => {
    setError(''); setStatus(kind === 'confirm' ? 'confirming' : 'rejecting');
    try {
      if (kind === 'confirm') await acceptPendingRevision(sessionId, subjectId, pathId, proposal.revision_id);
      else await rejectPendingRevision(sessionId, subjectId, pathId, proposal.revision_id);
      setStatus(kind === 'confirm' ? 'confirmed' : 'rejected');
      if (kind === 'confirm') bump();
    } catch { setStatus('error'); setError('操作失败，请重试。'); }
  };
  const busy = status === 'confirming' || status === 'rejecting';
  const stages = proposal.diff?.changed_stages || [];
  const tasks = proposal.diff?.changed_tasks || [];
  return <section className="rounded-2xl border border-primary-200 bg-primary-50/40 p-4 space-y-3">
    <div><h3 className="font-semibold text-surface-800">学习路径调整建议</h3><p className="text-sm text-surface-600">{proposal.reason || '根据近期学习情况生成'}</p></div>
    <p className="text-xs text-surface-500">版本：{proposal.currentRevision ?? '当前'} → {proposal.proposedRevision ?? '建议'} · {proposal.trigger_source === 'assessment' ? '学习评估触发' : '你的请求触发'}</p>
    <p className="text-xs text-surface-600">阶段变化：{stages.length ? stages.join('、') : '暂无阶段变化'}；任务变化：{tasks.length ? tasks.join('、') : '暂无任务变化'}</p>
    {status === 'confirmed' || status === 'rejected' ? <p className="text-sm font-medium text-success-600">{status === 'confirmed' ? '已确认调整' : '已拒绝调整'}</p> : <div className="flex gap-2"><button disabled={busy} onClick={() => run('confirm')} className="rounded-lg bg-primary-500 px-3 py-2 text-sm text-white disabled:opacity-50">确认调整</button><button disabled={busy} onClick={() => run('reject')} className="rounded-lg border px-3 py-2 text-sm disabled:opacity-50">拒绝调整</button></div>}
    {error && <p className="text-xs text-error-600">{error}</p>}
  </section>;
}
