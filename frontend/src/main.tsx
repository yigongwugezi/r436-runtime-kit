import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import './index.css';
import router from './router';
import { setSessionIdProvider } from './api/client';
import { useChatStore } from './store/chatStore';
import { useAuthStore } from './store/authStore';

// 注册 sessionId 提供者，使 API 层可以统一获取当前会话
setSessionIdProvider(() => useChatStore.getState().dataSessionId || '');

// 恢复认证状态（从 localStorage 读取 token 并验证）
useAuthStore.getState().restore();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
