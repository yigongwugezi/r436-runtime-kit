import client from './client';
import { getStableLearnerId } from '../store/authStore';

// ── Types ──────────────────────────────────────────────────────────

export interface StudentQuestion {
  id: number;
  question_id: string;
  question_set_id: string;
  session_id: string;
  source_question_id: string | null;
  type: string;
  stem: string;
  options: string[] | null;
  difficulty: string;
  knowledge_points: string[];
  tags: string[];
  source: string;
  quality_status: string;
  created_at: string | null;
  // Answer fields — only present when reveal=true
  correct?: string | null;
  explanation?: string | null;
  scoring_rubric?: Record<string, unknown> | null;
  reference_answer?: string | null;
}

export interface GradingResult {
  question_id: string;
  student_answer: string;
  total_score: number;
  dimension_scores: Record<string, number>;
  dimension_feedback: Record<string, string>;
  error_type: string;
  error_label: string;
  error_explanation: string;
  error_action: string;
  suggestions: string[];
  strengths: string[];
}

export interface WeakQuestionRecord {
  question: StudentQuestion | null;
  last_answer: string;
  grading_result: GradingResult;
  attempted_at: number;
}

export interface HistoryRecord {
  question_id: string;
  question: StudentQuestion | null;
  answer: string;
  grading_result: GradingResult;
  created_at: number;
}

// ── API Functions ──────────────────────────────────────────────────

/** Generate questions via AI for a session. */
export async function generateQuestions(body: { sessionId: string; message: string; knowledgePoints?: string[] }) {
  const { data } = await client.post('/api/questions/generate', body);
  return data as {
    status: string;
    data: { questionSetId: string; questions: StudentQuestion[]; count: number };
  };
}

/** List questions for a session (no answers returned). */
export async function listQuestions(params: Record<string, string>) {
  const { data } = await client.get('/api/questions', { params: { ...params, learnerId: getStableLearnerId() } });
  return data as {
    status: string;
    data: { questionSetId: string; questions: StudentQuestion[]; count: number };
  };
}

/** Get a single question. Set reveal=true to include answers. */
export async function getQuestion(questionId: string, sessionId: string, reveal: boolean = false) {
  const { data } = await client.get(`/api/questions/${questionId}`, {
    params: { sessionId, learnerId: getStableLearnerId(), reveal },
  });
  return data as { status: string; data: { question: StudentQuestion } };
}

/** Submit an answer and get grading results. */
export async function gradeAnswer(
  questionId: string,
  body: { sessionId: string; answer: string }
) {
  const { data } = await client.post(`/api/questions/${questionId}/grade`, { ...body, learnerId: getStableLearnerId() });
  return data as { status: string; data: { gradingResult: GradingResult } };
}

/** Get the student's wrong-answer book. */
export async function getWeakQuestions(params: Record<string, string | number>) {
  const { data } = await client.get('/api/questions/weak', { params: { ...params, learnerId: getStableLearnerId() } });
  return data as { status: string; data: { records: WeakQuestionRecord[]; total: number } };
}

/** Get answer history for a session. */
export async function getAnswerHistory(params: Record<string, string | number>) {
  const { data } = await client.get('/api/questions/history', { params: { ...params, learnerId: getStableLearnerId() } });
  return data as {
    status: string;
    data: { records: HistoryRecord[]; totalCorrect: number; totalAttempted: number };
  };
}
