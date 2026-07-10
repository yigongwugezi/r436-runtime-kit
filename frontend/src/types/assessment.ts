/** Scope types for quizzes and exam sets. */
export type QuizScopeType = 'knowledge_point' | 'section' | 'chapter' | 'stage' | 'path';
export type ExamScopeType = 'chapter' | 'stage' | 'path';

export type AttemptStatus = 'in_progress' | 'submitted' | 'graded';
export type ExamSetStatus = 'not_started' | 'in_progress' | 'completed';

/** A question reference inside a quiz or exam set. */
export interface QuestionRef {
  questionId: string;
  type: string;
  stemAbbr?: string;
  difficulty?: string;
  score?: number;
}

/** Lightweight instant quiz — generated on the fly, not archived. */
export interface Quiz {
  id: string;
  title: string;
  sessionId: string;
  scopeType: QuizScopeType;
  scopeId?: string | null;
  pathId?: string | null;
  stageId?: string | null;
  chapterId?: string | null;
  sectionId?: string | null;
  knowledgePointIds?: string[];
  difficulty: string;
  questionCount: number;
  questions?: QuestionRef[];
  linkedQuestions?: LinkedQuestion[];
  source: string;
  archivePolicy: string;
  createdAt: string | null;
}

/** A question resolved from PracticeQuestionModel, linked to a quiz/exam set. */
export interface LinkedQuestion {
  questionId: string;
  type: string;
  stem: string;
  options?: string[] | null;
  difficulty: string;
  knowledgePoints?: string[];
}

/** Heavyweight exam set — persistent, archivable, multi-attempt. */
export interface ExamSet {
  id: string;
  title: string;
  sessionId: string;
  scopeType: ExamScopeType;
  scopeId?: string | null;
  pathId?: string | null;
  stageId?: string | null;
  chapterId?: string | null;
  knowledgePointIds?: string[];
  difficulty: string;
  difficultyDistribution?: Record<string, number> | null;
  questionCount: number;
  questions?: QuestionRef[];
  linkedQuestions?: LinkedQuestion[];
  estimatedMinutes: number;
  totalScore: number;
  status: ExamSetStatus;
  source: string;
  archivePolicy: string;
  createdAt: string | null;
  updatedAt: string | null;
}

/** A single answer record linked to an attempt. */
export interface AttemptAnswer {
  id: number;
  questionId: string;
  studentAnswer: string;
  totalScore: number | null;
  errorType: string | null;
  errorLabel: string | null;
  errorExplanation: string | null;
  suggestions: string[];
  createdAt: string | null;
}

/** One attempt at a quiz or exam set, grouping multiple answer records. */
export interface Attempt {
  id: number;
  attemptId: string;
  sessionId: string;
  quizId?: string | null;
  examSetId?: string | null;
  learnerId?: string | null;
  answers?: AttemptAnswer[];
  linkedAnswers?: AttemptAnswer[];
  totalScore?: number | null;
  maxScore: number;
  status: AttemptStatus;
  startedAt: string | null;
  submittedAt: string | null;
  createdAt: string | null;
}
