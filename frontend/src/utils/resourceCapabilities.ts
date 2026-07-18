import type { GeneralResourceType, ProviderCapabilityStatus } from '../api/resources';

type CapabilityKey = 'llm' | 'search' | 'mindmap' | 'ppt' | 'video' | 'image' | 'manim';

const capabilityByResource: Record<GeneralResourceType, CapabilityKey> = {
  lecture: 'llm', quiz: 'llm', reading: 'llm', practice: 'llm',
  mindmap: 'mindmap', ppt: 'ppt', video: 'video', animation: 'video', manim: 'manim', image: 'image',
};

export interface ResourceCapability {
  enabled: boolean;
  status: ProviderCapabilityStatus | 'unavailable';
  reason?: string;
  fallbackAvailable: boolean;
  retryable: boolean;
}

const unavailable: ResourceCapability = {
  enabled: false, status: 'unavailable', reason: '无法确认生成服务状态，暂不可用。', fallbackAvailable: false, retryable: true,
};

const reasons: Partial<Record<ProviderCapabilityStatus, string>> = {
  not_configured: '当前未配置对应生成服务。',
  dependency_missing: '当前运行环境缺少必要依赖。',
  unsupported: '当前版本不支持该资源类型。',
  disabled: '当前版本不支持该资源类型。',
  network_unavailable: '生成服务暂时不可用，请重试。',
  provider_error: '生成服务暂时不可用，请重试。',
};

export function resourceCapability(resourceType: GeneralResourceType, providerStatus?: Record<string, ProviderCapabilityStatus>): ResourceCapability {
  const fallbackAvailable = resourceType === 'mindmap';
  const status = providerStatus?.[capabilityByResource[resourceType]];
  if (!status) return fallbackAvailable
    ? { enabled: true, status: 'unavailable', reason: '可使用本地模式生成 Mermaid 思维导图。', fallbackAvailable: true, retryable: false }
    : unavailable;
  if (status === 'available' || fallbackAvailable) return {
    enabled: true, status, fallbackAvailable, retryable: false,
    reason: fallbackAvailable && status !== 'available' ? '可使用本地模式生成 Mermaid 思维导图。' : undefined,
  };
  return { enabled: false, status, reason: reasons[status] || '生成服务暂不可用，请重试。', fallbackAvailable: false, retryable: status === 'network_unavailable' || status === 'provider_error' };
}

export function resourceErrorMessage(code?: string): { message: string; retryable: boolean } {
  const messages: Record<string, { message: string; retryable: boolean }> = {
    network_unavailable: { message: '网络或生成服务暂不可用，请重试。', retryable: true }, provider_timeout: { message: '生成服务响应超时，请重试。', retryable: true },
    provider_rate_limited: { message: '生成服务繁忙，请稍后重试。', retryable: true }, provider_auth_failed: { message: '生成服务认证失败，请联系管理员。', retryable: false },
    provider_invalid_response: { message: '生成服务返回无效结果，请重试。', retryable: true }, generation_failed: { message: '生成失败，请重试。', retryable: true },
  };
  return messages[code || ''] || { message: '无法创建资源任务，请检查输入后重试。', retryable: true };
}
