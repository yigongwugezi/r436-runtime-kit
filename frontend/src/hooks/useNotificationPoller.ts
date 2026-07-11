import { useEffect, useRef } from 'react';
import { useToast } from '../components/common/Toast';
import { getNotifications, type AssessmentNotification } from '../api/notifications';

const POLL_INTERVAL_MS = 30_000; // 30 seconds
const TYPE_ICONS: Record<AssessmentNotification['type'], string> = {
  diagnosis_updated: '🧠',
  plan_adjusted: '📋',
  recommendations_ready: '💡',
  review_needed: '⏰',
};

const TYPE_TOAST_SEVERITY: Record<AssessmentNotification['type'], 'info' | 'warning' | 'success'> = {
  diagnosis_updated: 'info',
  plan_adjusted: 'warning',
  recommendations_ready: 'success',
  review_needed: 'warning',
};

function hashNotification(n: AssessmentNotification): string {
  return `${n.type}::${n.title}::${n.createdAt}`;
}

/**
 * Polls the backend for closed-loop assessment notifications every 30 seconds.
 *
 * Displays them as toast messages so the student is aware of:
 * - Updated diagnoses after quizzes
 * - Suggested plan adjustments when mastery changes
 * - New learning recommendations
 * - Knowledge decay / review reminders
 *
 * Usage: call once at the app/page level with a valid sessionId.
 *
 * @param sessionId — current learning session ID.  Polling is paused when empty.
 * @param enabled  — set to false to pause polling (e.g. when streaming).
 */
export function useNotificationPoller(sessionId: string, enabled: boolean = true) {
  const { toast } = useToast();
  const seenRef = useRef<Set<string>>(new Set());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    // Clear interval on session change or disable
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    if (!sessionId || !enabled) return;

    const poll = async () => {
      try {
        const { notifications } = await getNotifications(sessionId);
        if (!notifications?.length) return;

        for (const n of notifications) {
          const key = hashNotification(n);
          if (seenRef.current.has(key)) continue;
          seenRef.current.add(key);

          const icon = TYPE_ICONS[n.type] || '📌';
          const severity = TYPE_TOAST_SEVERITY[n.type] || 'info';
          toast(severity, `${icon} ${n.message}`);
        }

        // Prune seen set if it grows too large
        if (seenRef.current.size > 200) {
          const entries = Array.from(seenRef.current);
          seenRef.current = new Set(entries.slice(-100));
        }
      } catch {
        // Silently ignore — notifications are best-effort
      }
    };

    // Poll immediately on mount / session change
    poll();

    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [sessionId, enabled, toast]);
}
