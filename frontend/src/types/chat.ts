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

export type ResourceType =
  | 'lecture'     // 课程讲义
  | 'mindmap'     // 思维导图
  | 'quiz'        // 练习题
  | 'reading'     // 拓展阅读
  | 'case_study'  // 实操案例
  | 'video'       // 教学视频/动画
  | 'ppt';        // PPT大纲

export interface GenerationProgress {
  stage: string;
  progress: number; // 0-100
  agentName?: string;
  detail?: string;
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
