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
  const explain = proposal.explainability || {};
  const evidence = explain.evidence || {};
  const added = explain.addedTasks || proposal.diff?.addedTasks || [];
  const zeroDiff = !added.length && !(proposal.diff?.changed_tasks || []).length;
  const run = async (kind: 'confirm'|'reject') => {
    setError(''); setStatus(kind === 'confirm' ? 'confirming' : 'rejecting');
    try {
      if (kind === 'confirm') await acceptPendingRevision(sessionId, subjectId, pathId, proposal.revision_id);
      else await rejectPendingRevision(sessionId, subjectId, pathId, proposal.revision_id);
      setStatus(kind === 'confirm' ? 'confirmed' : 'rejected');
      if (kind === 'confirm') bump();
    } catch { setStatus('error'); setError('Could not save the revision decision.'); }
  };
  const busy = status === 'confirming' || status === 'rejecting';
  return <section data-testid="adaptive-revision-card" className="rounded-2xl border border-primary-200 bg-primary-50/40 p-4 space-y-3">
    <div><h3 className="font-semibold text-surface-800">Learning path adjustment</h3><p className="text-sm text-surface-600">{explain.summary || proposal.summary || 'A review task is proposed from your recent quiz result.'}</p></div>
    <p data-testid="adaptive-revision-status" className="text-xs text-surface-500">Status: {status === 'pending' ? 'pending review' : status}</p>
    <div data-testid="adaptive-revision-evidence" className="text-xs text-surface-600">Reason: {explain.reason || proposal.reason || 'assessment'} · Score: {evidence.score ?? '—'} / pass {evidence.passThreshold ?? '—'} · Weak points: {(evidence.weakKPs || []).join(', ') || '—'}</div>
    <div data-testid="adaptive-revision-diff" className="text-xs text-surface-600">{zeroDiff ? 'No actual adjustment needed.' : <>Added: {added.map((task: any) => task.title || task.task_id).join(', ')} · Stage: {(explain.affectedStageIds || []).join(', ')} · Duration: +{explain.durationDelta ?? proposal.diff?.total_duration_change ?? 0} min</>}</div>
    {!zeroDiff && (status === 'confirmed' || status === 'rejected' ? <p className="text-sm font-medium text-success-600">{status === 'confirmed' ? 'Adjustment accepted.' : 'Adjustment rejected.'}</p> : <div className="flex gap-2"><button data-testid="adaptive-revision-accept" disabled={busy} onClick={() => run('confirm')} className="rounded-lg bg-primary-500 px-3 py-2 text-sm text-white disabled:opacity-50">Accept adjustment</button><button data-testid="adaptive-revision-reject" disabled={busy} onClick={() => run('reject')} className="rounded-lg border px-3 py-2 text-sm disabled:opacity-50">Reject adjustment</button></div>)}
    {error && <p className="text-xs text-error-600">{error}</p>}
  </section>;
}
