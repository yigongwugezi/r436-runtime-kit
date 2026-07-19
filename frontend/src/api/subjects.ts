import client from './client';
import type { Subject, SubjectResponse, CreateSubjectRequest, MigrateSubjectsRequest } from '../types/subject';
import { subjectFromResponse } from '../types/subject';

/** GET /api/subjects — list personal subjects for the authenticated learner */
export async function getPersonalSubjects(): Promise<Subject[]> {
  const res = await client.get('/api/subjects');
  const raw: SubjectResponse[] = res.data.subjects ?? [];
  return raw.map(subjectFromResponse);
}

/** POST /api/subjects — create a new personal subject */
export async function createPersonalSubject(data: CreateSubjectRequest): Promise<Subject> {
  const res = await client.post('/api/subjects', data);
  return subjectFromResponse(res.data.subject);
}

/** DELETE /api/subjects/{id} — delete a personal subject */
export async function deletePersonalSubject(id: string): Promise<void> {
  await client.delete(`/api/subjects/${id}`);
}

/** POST /api/subjects/migrate — bulk-import localStorage subjects to server */
export async function migratePersonalSubjects(
  subjects: MigrateSubjectsRequest['subjects'],
): Promise<Subject[]> {
  const res = await client.post('/api/subjects/migrate', { subjects });
  const raw: SubjectResponse[] = res.data.subjects ?? [];
  return raw.map(subjectFromResponse);
}

/** GET /api/subjects/session — resolve the session linked to a subject.
 *  For parent accounts, returns the child's session. */
export interface CanonicalSubjectSession {
  sessionId: string;
  subjectId: string;
  pathId: string | null;
  source: string;
  resolvedAt: string | null;
}

export async function getCanonicalSubjectSession(subjectId: string, signal?: AbortSignal): Promise<CanonicalSubjectSession | null> {
  const res = await client.get('/api/subjects/session', { params: { subject_id: subjectId }, signal });
  const data = res.data;
  if (!data?.session_id) return null;
  return {
    sessionId: data.session_id,
    subjectId: data.subject_id || subjectId,
    pathId: data.path_id || null,
    source: data.source || '',
    resolvedAt: data.resolved_at || null,
  };
}

export async function ensureCanonicalSubjectSession(subjectId: string): Promise<CanonicalSubjectSession> {
  const res = await client.post(`/api/subjects/${subjectId}/session/ensure`);
  const data = res.data;
  return { sessionId: data.session_id, subjectId: data.subject_id, pathId: data.path_id || null, source: data.source || '', resolvedAt: data.resolved_at || null };
}

/** Compatibility for chat-only callers that only need the ID. */
export async function getSubjectSession(subjectId: string): Promise<string | null> {
  return (await getCanonicalSubjectSession(subjectId))?.sessionId ?? null;
}
