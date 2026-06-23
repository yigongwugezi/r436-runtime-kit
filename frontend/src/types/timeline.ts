/** 时间线事件 — 后端 /learning-events/timeline 返回 */
export interface TimelineEvent {
  id: number;
  event: string;
  label: string;
  icon: string;
  color: string;
  resourceId: string;
  resourceTitle: string;
  resourceType: string;
  relatedStageId: string;
  relatedChapter: string;
  metadata: Record<string, unknown>;
  timestamp: number;
}

export interface TimelineResponse {
  events: TimelineEvent[];
  total: number;
}

/** 事件类型中文标签 */
export const EVENT_TYPE_LABELS: Record<string, string> = {
  resource_view: '查看了资源',
  resource_complete: '完成了资源',
  quiz_result: '提交了练习',
  practice_result: '提交了实操',
  feedback: '提交了反馈',
  stage_complete: '完成了阶段',
  node_progress: '学习节点更新',
};

/** 事件类型图标颜色配置 */
export const EVENT_TYPE_CONFIG: Record<string, { icon: string; color: string }> = {
  resource_view:     { icon: '👁️', color: 'blue' },
  resource_complete: { icon: '✅', color: 'green' },
  quiz_result:       { icon: '📝', color: 'amber' },
  practice_result:   { icon: '💻', color: 'cyan' },
  feedback:          { icon: '💬', color: 'purple' },
  stage_complete:    { icon: '🎯', color: 'rose' },
  node_progress:     { icon: '📌', color: 'gray' },
};
