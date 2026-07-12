/* ===================================================================
 * 个人科目（Subject）类型定义
 *
 * 前端 store 使用 camelCase；后端 API 返回 snake_case。
 * subjectFromResponse 负责转换。
 * =================================================================== */

/** 前端 store / localStorage 中使用的科目类型 */
export interface Subject {
  id: string;
  name: string;
  description?: string;
  textbookId?: string | null;
  createdAt: number;
  updatedAt: number;
}

/** 后端 GET/POST /api/subjects 返回的原始形状 */
export interface SubjectResponse {
  id: string;
  name: string;
  description: string | null;
  textbook_id?: string | null;
  created_at: number;
  updated_at: number;
}

/** POST /api/subjects 请求体 */
export interface CreateSubjectRequest {
  name: string;
  description?: string;
}

/** POST /api/subjects/migrate 请求体 */
export interface MigrateSubjectsRequest {
  subjects: Array<{ name: string; description?: string }>;
}

/** 将后端 snake_case 响应转换为前端 camelCase 类型 */
export function subjectFromResponse(raw: SubjectResponse): Subject {
  return {
    id: raw.id,
    name: raw.name,
    description: raw.description ?? undefined,
    textbookId: raw.textbook_id ?? null,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}
