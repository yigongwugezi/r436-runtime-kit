import { useEffect, useRef } from 'react';
import { useToast } from '../components/common/Toast';

const TYPE_ICONS: Record<string, string> = {
  diagnosis_updated: '🧠',
  plan_adjusted: '📋',
  recommendations_ready: '💡',
  review_needed: '⏰',
};

const TYPE_TOAST_SEVERITY: Record<string, 'info' | 'warning' | 'success'> = {
  diagnosis_updated: 'info',
  plan_adjusted: 'warning',
  recommendations_ready: 'success',
  review_needed: 'warning',
};

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

/**
 * Connects to the SSE endpoint for real-time notification push.
 *
 * Falls back to 30s polling when EventSource is unavailable or fails.
 * Displays notifications as toast messages.
 */
export function useNotificationPoller(sessionId: string, enabled: boolean = true) {
  const { toast } = useToast();
  const seenRef = useRef<Set<string>>(new Set());
  const esRef = useRef<EventSource | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    // Cleanup previous connections
    if (esRef.current) { esRef.current.close(); esRef.current = null; }
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (!sessionId || !enabled) return;

    // ── SSE path ──
    try {
      const url = `${BASE_URL}/api/notifications/stream?sessionId=${encodeURIComponent(sessionId)}`;
      const es = new EventSource(url);
      esRef.current = es;

      es.onmessage = (event) => {
        try {
          if (!event.data || event.data.startsWith(':')) return; // keepalive
          const n = JSON.parse(event.data);
          const key = `${n.type}::${n.title}::${n.createdAt}`;
          if (seenRef.current.has(key)) return;
          seenRef.current.add(key);
          const icon = TYPE_ICONS[n.type] || '📌';
          const severity = TYPE_TOAST_SEVERITY[n.type] || 'info';
          toast(severity, `${icon} ${n.message}`);
        } catch { /* ignore parse errors */ }
      };

      es.onerror = () => {
        // SSE failed — close and fall back to polling
        es.close();
        esRef.current = null;
        startPolling();
      };

      return () => { es.close(); };
    } catch {
      startPolling();
    }

    function startPolling() {
      if (pollRef.current) clearInterval(pollRef.current);

      const poll = async () => {
        try {
          const { getNotifications } = await import('../api/notifications');
          const { notifications } = await getNotifications(sessionId);
          if (!notifications?.length) return;
          for (const n of notifications) {
            const key = `${n.type}::${n.title}::${n.createdAt}`;
            if (seenRef.current.has(key)) continue;
            seenRef.current.add(key);
            const icon = TYPE_ICONS[n.type] || '📌';
            const severity = TYPE_TOAST_SEVERITY[n.type] || 'info';
            toast(severity, `${icon} ${n.message}`);
          }
          if (seenRef.current.size > 200) {
            const entries = Array.from(seenRef.current);
            seenRef.current = new Set(entries.slice(-100));
          }
        } catch { /* silent */ }
      };

      poll();
      pollRef.current = setInterval(poll, 30_000);
    }

    return () => {
      if (esRef.current) esRef.current.close();
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [sessionId, enabled, toast]);
}
