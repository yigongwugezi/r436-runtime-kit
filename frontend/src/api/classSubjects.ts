/** API functions for class subject (班级科目) management. */

import client from './client';
import type {
  ClassSubject,
  ClassMember,
  ClassPush,
  PushDetail,
  PushedQuestionGroup,
  ClassStats,
} from '../types/classSubject';

// ── Teacher: Class CRUD ─────────────────────────────────────────────────

export async function createClassSubject(data: {
  name: string;
  description?: string;
  subject: string;
}): Promise<ClassSubject> {
  const res = await client.post('/api/class-subjects', data);
  return res.data.classSubject;
}

export async function getMyClassSubjects(): Promise<ClassSubject[]> {
  const res = await client.get('/api/class-subjects/my');
  return res.data.classSubjects ?? [];
}

export async function getClassSubject(id: string): Promise<ClassSubject> {
  const res = await client.get(`/api/class-subjects/${id}`);
  return res.data.classSubject;
}

// ── Student: Join & list ────────────────────────────────────────────────

export async function joinClassSubject(inviteCode: string): Promise<ClassSubject> {
  const res = await client.post('/api/class-subjects/join', { inviteCode });
  return res.data.classSubject;
}

export async function getJoinedClassSubjects(): Promise<ClassSubject[]> {
  const res = await client.get('/api/class-subjects/joined');
  return res.data.classSubjects ?? [];
}

// ── Teacher: Member management ──────────────────────────────────────────

export async function getClassMembers(
  classId: string,
  limit = 50,
  offset = 0,
): Promise<{ members: ClassMember[]; total: number }> {
  const res = await client.get(`/api/class-subjects/${classId}/members`, {
    params: { limit, offset },
  });
  return res.data;
}

export async function removeClassMember(
  classId: string,
  studentId: string,
): Promise<void> {
  await client.delete(`/api/class-subjects/${classId}/members/${studentId}`);
}

// ── Teacher: Exercise push ──────────────────────────────────────────────

export async function pushExercises(
  classId: string,
  data: { title: string; description?: string; questionIds: string[] },
): Promise<ClassPush> {
  const res = await client.post(`/api/class-subjects/${classId}/push`, data);
  return res.data.push;
}

export async function getPushHistory(classId: string): Promise<ClassPush[]> {
  const res = await client.get(`/api/class-subjects/${classId}/pushes`);
  return res.data.pushes ?? [];
}

export async function getPushDetail(
  classId: string,
  pushId: string,
): Promise<PushDetail> {
  const res = await client.get(`/api/class-subjects/${classId}/pushes/${pushId}`);
  return res.data;
}

// ── Teacher: Stats ──────────────────────────────────────────────────────

export async function getClassStats(classId: string): Promise<ClassStats> {
  const res = await client.get(`/api/class-subjects/${classId}/stats`);
  return res.data;
}

// ── Student: Pushed questions ───────────────────────────────────────────

export async function getPushedQuestions(
  classId: string,
): Promise<PushedQuestionGroup[]> {
  const res = await client.get(`/api/class-subjects/${classId}/pushed-questions`);
  return res.data.pushes ?? [];
}
