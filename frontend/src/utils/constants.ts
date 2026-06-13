/** 系统默认快捷指令 */
export const DEFAULT_QUICK_COMMANDS = [
  { id: 'q1', icon: '🎯', label: '构建学习画像', prompt: '我想开始学习，帮我构建学习画像' },
  { id: 'q2', icon: '📊', label: '诊断知识短板', prompt: '帮我诊断一下我在人工智能方面的知识短板' },
  { id: 'q3', icon: '🗺️', label: '规划学习路径', prompt: '为我规划一个两周的机器学习学习路径' },
  { id: 'q4', icon: '📝', label: '生成练习题', prompt: '根据我的画像生成一套神经网络基础练习题' },
  { id: 'q5', icon: '🧠', label: '生成思维导图', prompt: '帮我生成人工智能导论的知识思维导图' },
  { id: 'q6', icon: '💻', label: '实操案例', prompt: '给我一个Python实现神经网络的实操案例' },
];

export const DEFAULT_SESSION_TITLE = '新对话';

export const MAX_MESSAGE_LENGTH = 4000;

/** 画像维度颜色映射 */
export const DIMENSION_COLORS = [
  '#6366f1', '#8b5cf6', '#a855f7', '#ec4899',
  '#f43f5e', '#f97316', '#eab308', '#22c55e',
  '#06b6d4', '#3b82f6',
];

/** 资源类型中文标签 */
export const RESOURCE_TYPE_LABELS: Record<string, string> = {
  lecture: '课程讲义',
  mindmap: '思维导图',
  quiz: '练习题',
  reading: '拓展阅读',
  case_study: '实操案例',
  video: '教学视频',
  ppt: 'PPT 大纲',
};
