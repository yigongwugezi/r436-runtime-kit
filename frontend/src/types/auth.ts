export interface Learner {
  id: string;
  nickname: string;
  /** @deprecated alias for nickname, kept for backward compat */
  name: string;
  phone: string | null;
  role: 'student' | 'parent' | 'teacher' | 'admin';
  grade: string | null;
  target_exam: string | null;
  school: string | null;
  student_no: string | null;
  avatar_url: string | null;
  created_at: string | null;
  updated_at: string | null;
  /** @deprecated epoch ms of last login, kept for backward compat */
  lastLoginAt: number;
}

export interface LoginRequest {
  phone?: string;
  student_no?: string;
  password: string;
}

export interface RegisterRequest {
  phone: string;
  password: string;
  nickname?: string;
  role?: string;
  grade?: string | null;
  target_exam?: string | null;
  student_no?: string | null;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  learner: Learner;
}

export interface UpdateProfileRequest {
  nickname?: string;
  grade?: string | null;
  target_exam?: string | null;
  school?: string | null;
  avatar_url?: string | null;
}

export interface SwitchRoleRequest {
  role: 'student' | 'parent' | 'teacher';
  target_learner_id?: string;
}

export interface LearningHistorySummary {
  total_study_minutes: number;
  completed_tasks: number;
  completed_resources: number;
  message_count: number;
}

export interface LearningHistoryResponse {
  events: Array<{
    id: number;
    event_type: string;
    resource_id: string | null;
    metadata: Record<string, unknown>;
    created_at: string | null;
  }>;
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
  summary: LearningHistorySummary;
}
