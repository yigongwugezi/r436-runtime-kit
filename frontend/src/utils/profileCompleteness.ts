const placeholders = new Set([
  'unknown', '未知', '未明确', '未明确说明', '暂无', '暂无诊断', '暂无诊断信息',
  '未提及', '待补充', '默认值', '默认', 'n/a', 'null', 'undefined',
]);

export const PROFILE_DISPLAY_DIMENSIONS = [
  { key: 'learning_goal', label: '学习目标' },
  { key: 'daily_minutes', label: '时间安排' },
  { key: 'background', label: '专业背景' },
  { key: 'learning_history', label: '学习历史' },
  { key: 'prior_experience', label: '已有经验' },
  { key: 'content_preferences', label: '内容偏好' },
  { key: 'resource_preferences', label: '资源偏好' },
] as const;

export function isUsableProfileValue(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(isUsableProfileValue);
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    return ['value', 'content', 'name', 'label'].some((key) => isUsableProfileValue(record[key]));
  }
  const normalized = String(value ?? '').trim();
  return Boolean(normalized) && !placeholders.has(normalized.toLowerCase());
}

export function isSpecificLearningGoal(value: unknown): boolean {
  const normalized = String(value ?? '').trim();
  return isUsableProfileValue(normalized)
    && !/(规划|生成).{0,20}(学习|路径)/.test(normalized);
}

export function profileCompleteness(facts: Record<string, unknown>, keys: readonly string[]): number {
  return keys.filter((key) => key === 'learning_goal'
    ? isSpecificLearningGoal(facts[key])
    : isUsableProfileValue(facts[key])).length;
}

export function profileDisplayCompleteness(context: Record<string, unknown> = {}) {
  const filled = PROFILE_DISPLAY_DIMENSIONS.filter(({ key }) => isUsableProfileValue(context[key])).length;
  const total = PROFILE_DISPLAY_DIMENSIONS.length;
  return { filled, total, percent: Math.round(filled / total * 100) };
}
