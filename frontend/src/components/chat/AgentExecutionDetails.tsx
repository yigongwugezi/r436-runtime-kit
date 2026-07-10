const labels: Record<string, string> = {
  multimodal_agent: '多模态处理',
  profile_agent: '学习画像',
  knowledge_agent: '知识检索',
  diagnosis_agent: '学习诊断',
  planner_agent: '路径规划',
  resource_agent: '学习资源',
  review_agent: '质量检查',
};

export default function AgentExecutionDetails({ info }: { info: Record<string, unknown> | null }) {
  if (!info) return null;
  const agents = Array.isArray(info.agents_run) ? info.agents_run.map(String) : [];
  const warnings = Array.isArray(info.warnings) ? info.warnings.map(String) : [];
  const fallbackUsed = info.fallback_used === true;
  if (!agents.length && !warnings.length && !fallbackUsed) return null;

  return (
    <details className="max-w-[82%] ml-12 rounded-xl border border-surface-200 bg-surface-50 px-3 py-2 text-xs text-surface-600">
      <summary className="cursor-pointer font-medium text-surface-700">查看本次处理信息</summary>
      <div className="mt-2 space-y-1">
        {agents.length > 0 && <p>已使用：{agents.map((agent) => labels[agent] || agent).join('、')}</p>}
        {fallbackUsed && <p>本次已使用稳定回退处理。</p>}
        {warnings.map((warning) => <p key={warning} className="text-amber-700">提示：{warning}</p>)}
      </div>
    </details>
  );
}
