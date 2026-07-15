/** 系统默认快捷指令 — 通用模板，具体科目由 PromptTemplates 动态替换 */
export const DEFAULT_QUICK_COMMANDS = [
  { id: 'q1', icon: '🎯', label: '了解我的基础', prompt: '我想开始学习，帮我了解一下我的基础' },
  { id: 'q2', icon: '📊', label: '诊断薄弱点', prompt: '帮我诊断一下薄弱点' },
  { id: 'q3', icon: '🗺️', label: '规划学习路径', prompt: '帮我规划学习路径' },
  { id: 'q4', icon: '📝', label: '生成练习题', prompt: '根据我的学习情况，出几道练习题' },
  { id: 'q5', icon: '🧠', label: '生成思维导图', prompt: '帮我生成知识思维导图' },
  { id: 'q6', icon: '📖', label: '讲解知识点', prompt: '帮我详细讲解一个知识点' },
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
  article: '学习文章',
  course: '公开课程',
  document: '学习文档',
  paper: '学术论文',
  summary_card: '总结卡片',
  concept_comparison: '概念对比',
  worked_example: '例题详解',
  mistake_checklist: '易错点清单',
  review_notes: '复习笔记',
  knowledge_map: '知识结构图',
  process_flow: '学习流程图',
  concept_diagram: '概念对比图',
  execution_trace: '执行过程图',
  code_trace: '代码运行轨迹',
};
