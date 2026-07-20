import type { ChatSession } from '../types/chat';
import type { ClassSubject } from '../types/classSubject';
import type { Subject } from '../types/subject';

export function canonicalRequestKey(learnerId?: string, subjectId?: string): string;
export function canLoadCanonicalData(status: string, sessionId?: string): boolean;
export function acceptsCanonicalResult(activeKey: string, resultKey: string): boolean;
export function resolveActiveSubjectContext(
  activeSubject?: Subject | null,
  activeClassSubject?: ClassSubject | null,
): { subjectId?: string; subjectName?: string; textbookId?: string };
export function hydrateChatSessions(
  remoteSessions?: Array<Pick<ChatSession, 'id'> & Partial<ChatSession>>,
  cachedSessions?: ChatSession[],
): ChatSession[];
