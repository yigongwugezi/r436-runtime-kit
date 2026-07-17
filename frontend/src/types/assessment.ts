/** Scope types for quizzes and exam sets. */
export type QuizScopeType = 'knowledge_point' | 'section' | 'chapter' | 'stage' | 'path';
export type ExamScopeType = 'chapter' | 'stage' | 'path';

export type AttemptStatus = 'started' | 'in_progress' | 'submitted' | 'graded' | 'processing' | 'completed' | 'failed' | 'cancelled';
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
  subjectId?: string | null;
  quizId?: string | null;
  examSetId?: string | null;
  learnerId?: string | null;
  answers?: AttemptAnswer[];
  linkedAnswers?: AttemptAnswer[];
  totalScore?: number | null;
  maxScore: number;
  status: AttemptStatus;
  attemptNumber?: number;
  idempotencyKey?: string;
  assessmentEligible?: boolean;
  startedAt: string | null;
  submittedAt: string | null;
  gradedAt?: string | null;
  answersRevealedAt?: string | null;
  processingTaskId?: string | null;
  diagnosisTaskId?: string | null;
  createdAt: string | null;
}

/** Per-question grading result after quiz submission. */
export interface QuizResult {
  questionId: string;
  studentAnswer: string;
  isCorrect: boolean;
  score: number;
  maxScore: number;
  correctAnswer?: string;
  explanation?: string;
  feedback?: string;
  errorType?: string | null;
  errorLabel?: string | null;
  knowledgePoint?: string;
}

/** Request body for section quiz generation. */
export interface SectionQuizGenerateRequest {
  sessionId: string;
  title: string;
  knowledgePoints: string[];
  lectureSummary?: string;
  difficulty?: string;
  requirements?: string;
  pathId?: string;
  stageId?: string;
  chapterId?: string;
  sectionId?: string;
}

/** Request body for quiz submission. */
export interface QuizSubmitRequest {
  sessionId: string;
  answers: { questionId: string; answer: string }[];
  /** Client-generated unique key for idempotent submission. Required. */
  idempotencyKey: string;
  /** Whether the learner viewed correct answers before submitting. */
  answersRevealed?: boolean;
  /** Client-side timestamp of submission intent. */
  clientSubmittedAt?: string;
}

/** Response from quiz submission. */
export interface QuizSubmitResponse {
  attempt: Attempt;
  results: QuizResult[];
  totalScore: number;
  maxScore: number;
  sectionStatusSuggestion: 'mastered' | 'in_progress' | 'needs_review';
  weakPoints?: WeakPoint[];
  /** True when this response is a replay of a previously-submitted attempt. */
  idempotentReplay?: boolean;
  /** Per-knowledge-point results, one per mapping per question. */
  knowledgePointResults?: KnowledgePointResult[];
  /** Workflow task ID for post-submit assessment processing (SSE-pollable). */
  processingTaskId?: string | null;
}

/** Per-knowledge-point result computed from a graded answer. */
export interface KnowledgePointResult {
  knowledgePointKey: string;
  knowledgePointLabel: string;
  questionId: string;
  attemptId: string;
  rawScore: number;
  maxScore: number;
  normalizedScore: number;
  weight: number;
  weightedScore: number;
  mappingConfidence: number;
  gradingConfidence: number;
  isCorrect: boolean;
  errorType: string | null;
  assessmentEligible: boolean;
}

/** A knowledge-point-level weakness summary. */
export interface WeakPoint {
  name: string;
  errorCount: number;
  totalAttempts: number;
  errorRate: number;
  latestError?: string;
  errorTypes?: string[];
  masteryEstimate?: number;
  suggestedAction?: string;
  source?: string;
}

/** Request body for exam set generation. */
export interface ExamSetGenerateRequest {
  sessionId: string;
  title: string;
  scopeType: 'chapter' | 'stage' | 'path';
  scopeId?: string;
  pathId?: string;
  stageId?: string;
  chapterId?: string;
  knowledgePointIds?: string[];
  knowledgePoints?: string[];
  difficulty?: string;
  questionCount?: number;
}

/** Aggregated weakness summary response. */
export interface WeaknessSummary {
  weakPoints: WeakPoint[];
  total: number;
}
