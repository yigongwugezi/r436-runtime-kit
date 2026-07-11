import client from './client';

export interface AssessmentNotification {
  type: 'diagnosis_updated' | 'plan_adjusted' | 'recommendations_ready' | 'review_needed';
  title: string;
  message: string;
  sessionId: string;
  createdAt: number;
}

export interface NotificationsResponse {
  notifications: AssessmentNotification[];
  hasMore: boolean;
}

export interface PendingResponse {
  hasPending: boolean;
}

/** Fetch and consume pending notifications for a session. */
export async function getNotifications(sessionId: string): Promise<NotificationsResponse> {
  const { data } = await client.get('/api/notifications', { params: { sessionId } });
  return data as NotificationsResponse;
}

/** Check if there are pending notifications without consuming them. */
export async function hasPendingNotifications(sessionId: string): Promise<boolean> {
  const { data } = await client.get('/api/notifications/pending', { params: { sessionId } });
  return (data as PendingResponse)?.hasPending === true;
}

/** Acknowledge/clear all notifications for a session. */
export async function ackNotifications(sessionId: string): Promise<void> {
  await client.post('/api/notifications/ack', { sessionId });
}
