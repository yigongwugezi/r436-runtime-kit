import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

const client: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 120_000,
  headers: { 'Content-Type': 'application/json' },
});

// 请求拦截：注入 token
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('edu_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截：统一错误处理
client.interceptors.response.use(
  (res) => res,
  (err) => {
    const message = err.response?.data?.detail || err.message || '请求失败';
    return Promise.reject(new Error(message));
  },
);

/** 流式请求 — 返回 ReadableStream reader */
export async function streamRequest(
  path: string,
  body: Record<string, unknown>,
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${localStorage.getItem('edu_token') || ''}`,
    },
    body: JSON.stringify(body),
  });

  if (!response.ok || !response.body) {
    throw new Error(`Stream error: ${response.status}`);
  }

  return response.body.getReader();
}

export default client;
