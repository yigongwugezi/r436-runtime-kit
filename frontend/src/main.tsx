import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import './index.css';
import router from './router';
import { setSessionIdProvider } from './api/client';
import { useChatStore } from './store/chatStore';

// 注册 sessionId 提供者，使 API 层可以统一获取当前会话
setSessionIdProvider(() => useChatStore.getState().dataSessionId || '');

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
