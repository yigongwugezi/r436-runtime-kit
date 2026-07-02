import { createBrowserRouter, Navigate } from 'react-router-dom';
import AppLayout from '../components/layout/AppLayout';
import Home from '../pages/Home';
import ChatPage from '../pages/ChatPage';
import ResourceLibrary from '../pages/ResourceLibrary';
import LearningPathPage from '../pages/LearningPathPage';
import ProfilePage from '../pages/ProfilePage';
import LearningAnalyticsPage from '../pages/LearningAnalyticsPage';
import LearningTimelinePage from '../pages/LearningTimelinePage';
import PracticePage from '../pages/PracticePage';
import ResourceGenerationPage from '../pages/ResourceGenerationPage';
import ConversationHistoryPage from '../pages/ConversationHistoryPage';
import SettingsPage from '../pages/SettingsPage';
import AdminDashboard from '../pages/AdminDashboard';
import LoginPage from '../pages/LoginPage';
import NotFound from '../pages/NotFound';
import { useAuthStore } from '../store/authStore';

/** 登录守卫：未登录跳转到 /login */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore(s => s.isAuthenticated);
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/',
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Home /> },
      { path: 'chat', element: <ChatPage /> },
      { path: 'resources', element: <ResourceLibrary /> },
      { path: 'resources/:id', element: <ResourceLibrary /> },
      { path: 'path', element: <LearningPathPage /> },
      { path: 'profile', element: <ProfilePage /> },
      { path: 'analytics', element: <LearningAnalyticsPage /> },
      { path: 'timeline', element: <LearningTimelinePage /> },
      { path: 'generate', element: <ResourceGenerationPage /> },
      { path: 'practice', element: <PracticePage /> },
      { path: 'history', element: <ConversationHistoryPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: 'admin', element: <AdminDashboard /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]);

export default router;
