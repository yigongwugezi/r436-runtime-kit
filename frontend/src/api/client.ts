import axios, { type AxiosInstance } from 'axios';
import { createLogger } from '../utils/logger';
import { runtimeStorageKeys } from '../utils/storageKeys';

const log = createLogger('API');

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

// ── Token 读取 ─────────────────────────────────────────────────────
function getToken(): string {
  try { return localStorage.getItem(runtimeStorageKeys.authToken.primary) || ''; }
  catch { return ''; }
}

function getRefreshToken(): string {
  try { return localStorage.getItem(runtimeStorageKeys.refreshToken.primary) || ''; }
  catch { return ''; }
}

function saveToken(token: string, refreshToken?: string) {
  try {
    localStorage.setItem(runtimeStorageKeys.authToken.primary, token);
    if (refreshToken) localStorage.setItem(runtimeStorageKeys.refreshToken.primary, refreshToken);
  } catch { /* noop */ }
}

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;

  if (!refreshPromise) {
    refreshPromise = fetch(`${BASE_URL}/api/auth/refresh`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${refreshToken}` },
    })
      .then(async (response) => {
        if (!response.ok) return null;
        const body = await response.json();
        const data = body?.data ?? body;
        if (!data?.access_token) return null;
        saveToken(data.access_token, data.refresh_token);
        return data.access_token as string;
      })
      .catch(() => null)
      .finally(() => { refreshPromise = null; });
  }
  return refreshPromise;
}

const client: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 120_000,
  headers: { 'Content-Type': 'application/json' },
});

// ── 请求拦截 ─────────────────────────────────────────────────────────
// 1. 自动注入 token
// 2. 自动注入 sessionId（可从外部覆盖）
client.interceptors.request.use((config) => {
  const token = String(config.url || '').includes('/api/auth/refresh')
    ? getRefreshToken()
    : getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── 状态码 → 中文描述映射 ─────────────────────────────────────────
const STATUS_MESSAGES: Record<number, string> = {
  400: '请求参数有误，请检查输入',
  401: '登录已过期，请重新登录',
  403: '没有权限执行此操作',
  404: '请求的资源不存在',
  409: '数据冲突，请刷新后重试',
  422: '提交的数据格式不正确',
  429: '请求过于频繁，请稍后重试',
  500: '服务器内部错误，请稍后重试',
  502: '网关错误，请稍后重试',
  503: '服务暂不可用，请稍后重试',
};

// ── ProductApiResponse 信封解包 ────────────────────────────────────
// 透明解包：将后端统一信封 {status, data, message, ...} 还原为 data 内容。
// 前端无需任何代码变更即可继续使用 res.profile / res.path 等字段。
client.interceptors.response.use((res) => {
  const body = res.data;
  if (body && typeof body === 'object' && 'status' in body && 'data' in body) {
    if (body.status === 'error') {
      log.warn(`← ${res.config.method?.toUpperCase()} ${res.config.url} biz err: ${body.message}`);
    }
    // 透明解包：用信封内的 data 替换整个响应体
    res.data = body.data;
  }
  return res;
});

// ── 结构化 API 错误类型 ──────────────────────────────────────────
export interface ApiError {
  message: string;
  code?: string;
  isUserError: boolean;
  statusCode?: number;
}

function extractApiError(err: any): ApiError {
  let message = '请求失败，请稍后重试';
  let code: string | undefined;
  let isUserError = false;

  if (err.response) {
    const status = err.response.status;
    const body = err.response.data;

    log.warn(`← ${err.config?.method?.toUpperCase()} ${err.config?.url} ${status}`, body);

    // 提取后端结构化错误字段
    isUserError = body?.is_user_error === true;
    code = body?.code;

    // 优先使用后端返回的安全消息（detail/message/error）
    const detail = body?.detail || body?.message || body?.error || null;
    if (detail && typeof detail === 'object') code = detail.code || code;

    if (code === 'CURRENT_PATH_UNRESOLVED') {
      message = code;
    } else if (detail && typeof detail === 'string') {
      message = detail;
    } else if (STATUS_MESSAGES[status]) {
      message = STATUS_MESSAGES[status];
    } else if (status >= 500) {
      message = '服务器出了点问题，请稍后重试';
    } else if (status >= 400) {
      message = '请求出了点问题，请检查后重试';
    }

    // 对 404 补充具体资源信息
    if (status === 404 && body?.resource) {
      message = `${body.resource} ${body.resource_id || ''} 不存在`.trim();
    }

    return { message, code, isUserError, statusCode: status };
  }

  // 网络错误：未收到响应
  if (err.request) {
    if ((err.message || '').includes('timeout')) {
      message = '请求超时，服务器响应较慢，请稍后重试';
      log.warn(`请求超时: ${err.config?.url}`);
    } else {
      message = '无法连接到服务器，请确认后端服务已启动';
      log.error(`网络错误: ${err.config?.url}`, err.message);
    }
    isUserError = false;
  }

  return { message, code, isUserError };
}

// ── 响应拦截：统一错误处理 ──────────────────────────────────────────
client.interceptors.response.use(
  (res) => {
    log.debug(`→ ${res.config.method?.toUpperCase()} ${res.config.url} ${res.status}`);
    return res;
  },
  async (err) => {
    const request = err.config as (typeof err.config & { _retry?: boolean }) | undefined;
    if (err.response?.status === 401 && request && !request._retry && !String(request.url || '').includes('/api/auth/refresh')) {
      request._retry = true;
      const token = await refreshAccessToken();
      if (token) {
        request.headers = request.headers || {};
        request.headers.Authorization = `Bearer ${token}`;
        return client(request);
      }
    }
    const apiError = extractApiError(err);
    return Promise.reject(new Error(apiError.message));
  },
);

// ── 工具函数 ──────────────────────────────────────────────────────────

/** 获取当前 sessionId — 通过外部注入，避免循环依赖 */
let _sessionIdProvider: (() => string) | null = null;
export function setSessionIdProvider(fn: () => string) {
  _sessionIdProvider = fn;
}
export function getCurrentSessionId(): string {
  return _sessionIdProvider?.() ?? '';
}

/** Authorization header for raw fetch() calls that bypass the axios client.

    任何绕过 axios 实例的裸 fetch 都必须带上它——后端按 Bearer token 绑定
    每用户 AI 凭据上下文，缺头会让已配置的用户被当成匿名（AI/搜索报未配置）。 */
export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** 流式请求 — 返回 ReadableStream reader，支持 AbortSignal */
export async function streamRequest(
  path: string,
  body: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  log.debug(`STREAM POST ${path}`);

  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok || !response.body) {
    log.error(`STREAM 失败 ${path} → ${response.status}`);
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const message = typeof detail === 'object' ? detail.code : detail;
    throw new Error(`Stream error: ${response.status}${message ? ` ${message}` : ''}`);
  }

  log.debug(`STREAM 已连接 ${path}`);
  return response.body.getReader();
}

/** Authenticated SSE GET used by resumable workflow tasks. */
export async function streamGet(
  path: string,
  signal?: AbortSignal,
  lastEventId = 0,
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: {
      Authorization: `Bearer ${getToken()}`,
      ...(lastEventId ? { 'Last-Event-ID': String(lastEventId) } : {}),
    },
    signal,
  });
  if (!response.ok || !response.body) throw new Error(`Stream error: ${response.status}`);
  return response.body.getReader();
}

export default client;
