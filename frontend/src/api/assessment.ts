import client from './client';
import type {
  Quiz,
  ExamSet,
  Attempt,
  QuizResult,
  QuizSubmitResponse,
  LinkedQuestion,
  SectionQuizGenerateRequest,
  QuizSubmitRequest,
} from '../types/assessment';

// ═════════════════════════════════════════════════════════════════════
// Quiz
// ═════════════════════════════════════════════════════════════════════

/** Create a new instant quiz. */
export async function createQuiz(body: {
  sessionId: string;
  title?: string;
  scopeType?: string;
  scopeId?: string;
  pathId?: string;
  stageId?: string;
  chapterId?: string;
  sectionId?: string;
  knowledgePointIds?: string[];
  difficulty?: string;
  questions?: Record<string, unknown>[];
  source?: string;
}) {
  const { data } = await client.post('/api/quizzes', body);
  return data as { status: string; data: { quiz: Quiz } };
}

/** List quizzes for a session. */
export async function listQuizzes(params: {
  sessionId?: string;
  scopeType?: string;
}) {
  const { data } = await client.get('/api/quizzes', { params });
  return data as { status: string; data: { quizzes: Quiz[] } };
}

/** Get a single quiz with its linked questions. */
export async function getQuiz(quizId: string) {
  const { data } = await client.get(`/api/quizzes/${quizId}`);
  return data as { status: string; data: { quiz: Quiz } };
}

/** Start a new attempt on a quiz. */
export async function startQuizAttempt(
  quizId: string,
  body: { sessionId: string; maxScore?: number }
) {
  const { data } = await client.post(`/api/quizzes/${quizId}/attempts`, body);
  return data as { status: string; data: { attempt: Attempt } };
}

/** List all attempts for a quiz. */
export async function listQuizAttempts(quizId: string) {
  const { data } = await client.get(`/api/quizzes/${quizId}/attempts`);
  return data as { status: string; data: { attempts: Attempt[] } };
}

// ═════════════════════════════════════════════════════════════════════
// Attempt
// ═════════════════════════════════════════════════════════════════════

/** Get an attempt with its linked answer records. */
export async function getAttempt(attemptId: string) {
  const { data } = await client.get(`/api/attempts/${attemptId}`);
  return data as { status: string; data: { attempt: Attempt } };
}

/** Update an attempt — save progress or change status. */
export async function updateAttempt(
  attemptId: string,
  body: { answers?: Record<string, unknown>[]; status?: string }
) {
  const { data } = await client.patch(`/api/attempts/${attemptId}`, body);
  return data as { status: string; data: { attempt: Attempt } };
}

/** Submit an attempt for grading. */
export async function submitAttempt(
  attemptId: string,
  body: {
    answers: { questionId: string; studentAnswer: string }[];
    totalScore?: number;
  }
) {
  const { data } = await client.post(`/api/attempts/${attemptId}/submit`, body);
  return data as { status: string; data: { attempt: Attempt } };
}

// ═════════════════════════════════════════════════════════════════════
// Exam Set
// ═════════════════════════════════════════════════════════════════════

/** Create a new exam set. */
export async function createExamSet(body: {
  sessionId: string;
  title?: string;
  scopeType?: string;
  scopeId?: string;
  pathId?: string;
  stageId?: string;
  chapterId?: string;
  knowledgePointIds?: string[];
  difficulty?: string;
  difficultyDistribution?: Record<string, number>;
  questionCount?: number;
  questions?: Record<string, unknown>[];
  estimatedMinutes?: number;
  totalScore?: number;
  source?: string;
  archivePolicy?: string;
}) {
  const { data } = await client.post('/api/exam-sets', body);
  return data as { status: string; data: { examSet: ExamSet } };
}

/** List exam sets with optional filters. */
export async function listExamSets(params: {
  sessionId?: string;
  scopeType?: string;
  status?: string;
}) {
  const { data } = await client.get('/api/exam-sets', { params });
  return data as { status: string; data: { examSets: ExamSet[] } };
}

/** Get a single exam set with its linked questions. */
export async function getExamSet(examSetId: string) {
  const { data } = await client.get(`/api/exam-sets/${examSetId}`);
  return data as { status: string; data: { examSet: ExamSet } };
}

/** Partial-update an exam set. */
export async function updateExamSet(
  examSetId: string,
  body: {
    title?: string;
    status?: string;
    questionCount?: number;
    questions?: Record<string, unknown>[];
    difficultyDistribution?: Record<string, number>;
    estimatedMinutes?: number;
    totalScore?: number;
  }
) {
  const { data } = await client.patch(`/api/exam-sets/${examSetId}`, body);
  return data as { status: string; data: { examSet: ExamSet } };
}

/** Start a new attempt on an exam set. */
export async function startExamSetAttempt(
  examSetId: string,
  body: { sessionId: string; maxScore?: number }
) {
  const { data } = await client.post(
    `/api/exam-sets/${examSetId}/attempts`,
    body
  );
  return data as { status: string; data: { attempt: Attempt } };
}

/** Create an attempt directly (standalone endpoint). */
export async function createAttempt(body: {
  sessionId: string;
  quizId?: string;
  examSetId?: string;
  maxScore?: number;
}) {
  const { data } = await client.post('/api/attempts', body);
  return data as { status: string; data: { attempt: Attempt } };
}

// ═════════════════════════════════════════════════════════════════════
// Section Quiz Generation & Submission (Part 2)
// ═════════════════════════════════════════════════════════════════════

/** Generate a quiz from section context via LLM. */
export async function generateSectionQuiz(
  sectionId: string,
  body: SectionQuizGenerateRequest
) {
  const { data } = await client.post(
    `/api/sections/${sectionId}/quiz/generate`,
    body
  );
  return data as {
    status: string;
    data: { quiz: Quiz; questions: LinkedQuestion[] };
  };
}

/** Submit all answers for a quiz — grade and return results. */
export async function submitQuizAttempt(
  quizId: string,
  body: QuizSubmitRequest
) {
  const { data } = await client.post(`/api/quizzes/${quizId}/submit`, body);
  return data as { status: string; data: QuizSubmitResponse };
}

/** Get quiz results with answers and grading after submission. */
export async function getQuizResults(
  quizId: string,
  attemptId?: string
) {
  const params: Record<string, string> = {};
  if (attemptId) params.attemptId = attemptId;
  const { data } = await client.get(`/api/quizzes/${quizId}/results`, { params });
  return data as { status: string; data: { quiz: Quiz & { attempt?: Attempt; gradingResults?: QuizResult[] } } };
}

// ═════════════════════════════════════════════════════════════════════
// Exam Set Generation & Submission (Part 4)
// ═════════════════════════════════════════════════════════════════════

import type { ExamSetGenerateRequest } from '../types/assessment';

/** Generate an archived exam set via LLM. */
export async function generateExamSet(body: ExamSetGenerateRequest) {
  const { data } = await client.post('/api/exam-sets/generate', body);
  return data as {
    status: string;
    data: { examSet: ExamSet; questions: LinkedQuestion[] };
  };
}

/** Submit all answers for an exam set — grade and return results. */
export async function submitExamSet(
  examSetId: string,
  body: QuizSubmitRequest
) {
  const { data } = await client.post(
    `/api/exam-sets/${examSetId}/submit`,
    body
  );
  return data as { status: string; data: QuizSubmitResponse };
}

/** Get exam set results with answers and grading. */
export async function getExamSetResults(
  examSetId: string,
  attemptId?: string
) {
  const params: Record<string, string> = {};
  if (attemptId) params.attemptId = attemptId;
  const { data } = await client.get(
    `/api/exam-sets/${examSetId}/results`,
    { params }
  );
  return data as {
    status: string;
    data: { examSet: ExamSet & { attempt?: Attempt; gradingResults?: QuizResult[] } };
  };
}

/** List all attempts for an exam set. */
export async function listExamSetAttempts(examSetId: string) {
  const { data } = await client.get(
    `/api/exam-sets/${examSetId}/attempts`
  );
  return data as { status: string; data: { attempts: Attempt[] } };
}
