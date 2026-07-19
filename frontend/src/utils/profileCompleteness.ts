const placeholders = new Set([
  'unknown', '未知', '未明确', '未明确说明', '暂无', '暂无诊断', '暂无诊断信息',
  '未提及', '待补充', '默认值', '默认', 'n/a', 'null', 'undefined',
]);

export function isUsableProfileValue(value: unknown): boolean {
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
