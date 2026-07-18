import client from './client';

// ── Per-user AI model credentials (系统设置 → AI 模型配置) ───────────
// 后端永远只返回脱敏后的密钥（如 sk-26****1d4f）+ configured 标志；
// 保存时只需提交用户改动过的字段（含 **** 的脱敏占位值会被后端忽略）。

/** 单个服务的脱敏配置：凭据字段为脱敏字符串，configured 表示该服务是否配置齐全 */
export interface AIServiceConfig {
  provider?: string;
  apiKey?: string;
  appId?: string;
  apiSecret?: string;
  configured: boolean;
}

export type AIConfigMap = Record<string, AIServiceConfig>;

export interface AICapabilities {
  llmProvider: string;
  llmConfigured: boolean;
  searchProvider: string;
  searchConfigured: boolean;
  pptConfigured: boolean;
  videoConfigured: boolean;
  imageConfigured: boolean;
}

export async function getAIConfig(): Promise<AIConfigMap> {
  const { data } = await client.get('/api/learner/me/ai-config');
  return ((data as any)?.config ?? {}) as AIConfigMap;
}

/** 部分合并保存：只传改动的服务/字段；空字符串表示清除该字段 */
export async function saveAIConfig(config: Record<string, Record<string, string>>): Promise<AIConfigMap> {
  const { data } = await client.put('/api/learner/me/ai-config', { config });
  return ((data as any)?.config ?? {}) as AIConfigMap;
}

export async function getAICapabilities(): Promise<AICapabilities> {
  const { data } = await client.get('/api/learner/me/ai-config/capabilities');
  return data as AICapabilities;
}
