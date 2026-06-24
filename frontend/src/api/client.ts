import axios, { type AxiosInstance } from 'axios';
import { createLogger } from '../utils/logger';
import { runtimeStorageKeys } from '../utils/storageKeys';

const log = createLogger('API');

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001').replace(/\/$/, '');

// ── Token 读取 ─────────────────────────────────────────────────────
function getToken(): string {
  try { return localStorage.getItem(runtimeStorageKeys.authToken.primary) || ''; }
  catch { return ''; }
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
  const token = getToken();
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

    if (detail && typeof detail === 'string') {
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
  (err) => {
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

/** 流式请求 — 返回 ReadableStream reader */
export async function streamRequest(
  path: string,
  body: Record<string, unknown>,
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  log.debug(`STREAM POST ${path}`);

  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify(body),
  });

  if (!response.ok || !response.body) {
    log.error(`STREAM 失败 ${path} → ${response.status}`);
    throw new Error(`Stream error: ${response.status}`);
  }

  log.debug(`STREAM 已连接 ${path}`);
  return response.body.getReader();
}

export default client;
