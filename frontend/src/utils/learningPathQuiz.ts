import type { LinkedQuestion } from '../types/assessment';

export type LearningPathQuiz = { quizId: string; questions: LinkedQuestion[]; questionCount: number; taskId: string; semanticFingerprint: string; taskSemanticSnapshot: Record<string, unknown>; [key: string]: unknown };

const quizEnsures = new Map<string, Promise<LearningPathQuiz>>();

export function learningPathQuizScope(body: Record<string, unknown>): string {
  const values = ['sessionId', 'subjectId', 'pathId', 'stageId', 'dayId', 'globalDayIndex', 'taskId'].map((key) => body[key]);
  if (!values.every((value) => value !== undefined && value !== null && value !== '')) return '';
  const semantic = ['taskType', 'taskTitle', 'taskDescription', 'learningObjectives', 'knowledgePoints', 'pathVersion'].map((key) => body[key]);
  return `${values.join('|')}|${JSON.stringify(semantic)}|quiz`;
}

export function normalizeLearningPathQuiz(response: any): LearningPathQuiz {
  const quiz = [response?.data?.quiz, response?.quiz, response?.data, response].find((value) => value && typeof value === 'object') || {};
  const questions = Array.isArray(quiz.questions) ? quiz.questions.map((question: any) => ({ ...question, questionId: question.questionId || question.question_id || question.id || '' })).filter((question: any) => question.questionId) : [];
  return { ...quiz, quizId: String(quiz.quizId || quiz.quiz_id || quiz.id || ''), questions, questionCount: Number(quiz.questionCount || quiz.question_count || questions.length), taskId: String(quiz.taskId || quiz.task_id || ''), semanticFingerprint: String(quiz.semanticFingerprint || ''), taskSemanticSnapshot: quiz.taskSemanticSnapshot || {} };
}

export function matchesLearningPathQuiz(quiz: LearningPathQuiz, scope: Record<string, unknown>): boolean {
  const snapshot = quiz.taskSemanticSnapshot || {};
  return ['taskId', 'sessionId', 'subjectId', 'pathId', 'stageId', 'dayId', 'globalDayIndex'].every((key) => String((quiz as any)[key] ?? snapshot[key] ?? '') === String(scope[key] ?? ''))
    && ['taskType', 'taskTitle', 'taskDescription', 'learningObjectives', 'knowledgePoints'].every((key) => JSON.stringify(snapshot[key] ?? '') === JSON.stringify(scope[key] ?? ''));
}

export function ensureScopedLearningPathQuiz(taskId: string, body: Record<string, unknown>, loader: (taskId: string, body: Record<string, unknown>) => Promise<any>): Promise<LearningPathQuiz> {
  const key = learningPathQuizScope(body);
  if (!key) return Promise.reject(new Error('quiz canonical scope required'));
  let request = quizEnsures.get(key);
  if (!request) {
    request = loader(taskId, body).then(normalizeLearningPathQuiz);
    quizEnsures.set(key, request);
    request.catch(() => quizEnsures.delete(key));
  }
  return request;
}

export function retryScopedLearningPathQuiz(body: Record<string, unknown>): void {
  quizEnsures.delete(learningPathQuizScope(body));
}
