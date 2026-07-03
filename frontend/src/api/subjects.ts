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
export async function getSubjectSession(subjectId: string): Promise<string | null> {
  const res = await client.get('/api/subjects/session', { params: { subject_id: subjectId } });
  return res.data?.session_id ?? null;
}
