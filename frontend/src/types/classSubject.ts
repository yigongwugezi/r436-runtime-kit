/** Types for the class subject (班级科目) mechanism. */

export interface ClassSubject {
  id: string;
  name: string;
  description?: string;
  subject: string;
  teacher_id: string;
  teacher_name: string;
  invite_code: string;
  student_count: number;
  created_at: string;
  updated_at: string;
}

export interface ClassMember {
  student_id: string;
  student_name: string;
  grade?: string;
  school?: string;
  joined_at: string;
}

export interface ClassPush {
  id: string;
  class_id: string;
  teacher_id: string;
  title: string;
  description?: string;
  question_ids: string[];
  question_count: number;
  answered_count: number;
  created_at: string;
}

export interface PushQuestionStat {
  question_id: string;
  stem: string;
  answered_count: number;
  avg_score: number;
}

export interface PushStudentResult {
  student_id: string;
  student_name: string;
  answered: number;
  total: number;
  avg_score: number;
}

export interface PushDetail extends ClassPush {
  questionStats: PushQuestionStat[];
  studentResults: PushStudentResult[];
}

export interface PushedQuestion {
  question_id: string;
  type: string;
  stem: string;
  options?: string[];
  difficulty?: string;
  knowledge_points?: string[];
  tags?: string[];
  source: string;
  answered: boolean;
  score?: number;
  created_at?: string;
}

export interface PushedQuestionGroup {
  pushId: string;
  title: string;
  description?: string;
  questions: PushedQuestion[];
}

export interface ClassStats {
  totalStudents: number;
  totalPushes: number;
  totalQuestions: number;
  totalAnswered: number;
  avgScore: number | null;
}
