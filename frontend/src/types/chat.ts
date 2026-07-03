// ================================================================
// Chat / Message types
// ================================================================

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  /** 流式生成中标记 */
  streaming?: boolean;
  /** 关联的资源卡片 */
  resourceCards?: ResourceCardData[];
  /** 消息类型 */
  type?: MessageType;
  /** 进度信息 */
  progress?: GenerationProgress;
  /** 错误信息 */
  error?: string;
  /** 低置信度意图标记 — 前端需展示 clarification 交互面板 */
  isClarification?: boolean;
  attachments?: ChatAttachment[];
  multimodalResult?: {
    status?: string;
    task_type?: string;
    provider?: string;
    warnings?: string[];
    trace?: Record<string, unknown>;
    workflow_trace?: Record<string, unknown>;
    result?: any;
  };
}

export interface ChatAttachment {
  file_id?: string;
  name?: string;
  url?: string;
  image_url?: string;
  preview_url?: string;
  local_path?: string;
  mime_type?: string;
  size?: number;
  reused_from_last?: boolean;
}

export type MessageType =
  | 'text'
  | 'profile_card'
  | 'diagnosis_report'
  | 'learning_path'
  | 'resource_cards'
  | 'quiz'
  | 'feedback';

export interface ResourceCardData {
  id: string;
  type: ResourceType;
  title: string;
  description: string;
  tags: string[];
  /** 资源内容摘要 */
  preview?: string;
  /** 关联的知识点 */
  knowledgePoints: string[];
}

import type { ResourceType } from './resource';

export interface GenerationProgress {
  stage: string;
  progress: number; // 0-100
  agentName?: string;
  detail?: string;
  error?: string;
  done?: boolean;
}

/** 进度条中单个步骤的定义 */
export interface ProgressStep {
  key: string;
  label: string;
}

export interface QuickCommand {
  id: string;
  label: string;
  icon: string;
  prompt: string;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}
