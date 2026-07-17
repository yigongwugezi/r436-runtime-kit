/**
 * Hook for monitoring the assessment_processing workflow task.
 *
 * Called after quiz/exam submission when `processingTaskId` is returned.
 * Connects to the SSE event stream and returns real-time status updates.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { consumeWorkflowEvents, readWorkflow } from '../api/workflows';

export type AssessmentProcessingStatus =
  | 'idle'
  | 'verifying'
  | 'analyzing'
  | 'diagnosing'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface AssessmentProcessingState {
  status: AssessmentProcessingStatus;
  label: string;
  taskId: string | null;
  errorMessage: string | null;
}

export function useAssessmentProcessing(
  processingTaskId: string | null | undefined,
  sessionId: string,
) {
  const [state, setState] = useState<AssessmentProcessingState>({
    status: 'idle',
    label: '',
    taskId: processingTaskId || null,
    errorMessage: null,
  });
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  const reset = useCallback(() => {
    setState({ status: 'idle', label: '', taskId: null, errorMessage: null });
  }, []);

  const retry = useCallback(async () => {
    if (!state.taskId) return;
    try {
      const { retryWorkflow } = await import('../api/workflows');
      const result = await retryWorkflow(state.taskId);
      if (result?.task_id) {
        setState(prev => ({
          ...prev,
          status: 'analyzing',
          label: '正在重新处理...',
          taskId: result.task_id,
          errorMessage: null,
        }));
      }
    } catch {
      setState(prev => ({ ...prev, errorMessage: '重试失败' }));
    }
  }, [state.taskId]);

  useEffect(() => {
    if (!processingTaskId) return;
    mountedRef.current = true;

    const controller = new AbortController();
    abortRef.current = controller;

    setState(prev => ({
      ...prev,
      status: 'analyzing',
      label: '正在分析知识点表现...',
      taskId: processingTaskId,
    }));

    const stageToStatus = (stageId: string, label: string): AssessmentProcessingStatus => {
      if (stageId === 'verification') return 'verifying';
      if (stageId === 'kp_analysis') return 'analyzing';
      if (stageId === 'diagnosis') return 'diagnosing';
      // Use label keywords as fallback
      if (label.includes('验证')) return 'verifying';
      if (label.includes('分析') || label.includes('知识点')) return 'analyzing';
      if (label.includes('诊断')) return 'diagnosing';
      return 'analyzing';
    };

    (async () => {
      try {
        await consumeWorkflowEvents(
          processingTaskId,
          (event) => {
            if (!mountedRef.current) return;
            const eventStatus = event.status;
            const stageId = event.stage_id || '';
            const label = event.label || '';

            if (eventStatus === 'completed' || event.event === 'workflow_completed') {
              setState(prev => ({ ...prev, status: 'completed', label: '诊断已更新 ✓' }));
            } else if (eventStatus === 'failed' || event.event === 'workflow_failed') {
              setState(prev => ({
                ...prev,
                status: 'failed',
                label: '更新失败，可重试',
                errorMessage: event.safe_error_message || '处理失败',
              }));
            } else if (eventStatus === 'cancelled' || event.event === 'workflow_cancelled') {
              setState(prev => ({ ...prev, status: 'cancelled', label: '已取消' }));
            } else {
              setState(prev => ({
                ...prev,
                status: stageToStatus(stageId, label),
                label: label || prev.label,
              }));
            }
          },
          controller.signal,
        );
      } catch {
        // Stream disconnected — poll for final state
      }

      if (!mountedRef.current) return;
      try {
        const final = await readWorkflow(processingTaskId, sessionId);
        if (!mountedRef.current) return;
        if (final.status === 'completed') {
          setState(prev => ({ ...prev, status: 'completed', label: '诊断已更新 ✓' }));
        } else if (final.status === 'failed') {
          setState(prev => ({
            ...prev,
            status: 'failed',
            label: '更新失败，可重试',
            errorMessage: final.errorMessage || '处理失败',
          }));
        }
      } catch {
        // Task may have expired — assume completed
        setState(prev => ({ ...prev, status: 'completed', label: '' }));
      }
    })();

    return () => {
      mountedRef.current = false;
      controller.abort();
      abortRef.current = null;
    };
  }, [processingTaskId, sessionId]);

  return { ...state, reset, retry };
}
