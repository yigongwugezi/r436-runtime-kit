import { createBrowserRouter, Navigate } from 'react-router-dom';
import AppLayout from '../components/layout/AppLayout';
import Home from '../pages/Home';
import ChatPage from '../pages/ChatPage';
import ResourceLibrary from '../pages/ResourceLibrary';
import LearningPathPage from '../pages/LearningPathPage';
import ProfilePage from '../pages/ProfilePage';
import LearningAnalyticsPage from '../pages/LearningAnalyticsPage';
import LearningTimelinePage from '../pages/LearningTimelinePage';
import KnowledgeGraphPage from '../pages/KnowledgeGraphPage';
import PracticePage from '../pages/PracticePage';
import ResourceGenerationPage from '../pages/ResourceGenerationPage';
import ConversationHistoryPage from '../pages/ConversationHistoryPage';
import SettingsPage from '../pages/SettingsPage';
import AdminDashboard from '../pages/AdminDashboard';
import ReviewQueuePage from '../pages/ReviewQueuePage';
import TeacherHome from '../pages/TeacherHome';
import TeacherClassDetail from '../pages/TeacherClassDetail';
import LoginPage from '../pages/LoginPage';
import LecturePage from '../pages/LecturePage';
import TextbookViewPage from '../pages/TextbookViewPage';
import NotFound from '../pages/NotFound';
import { useAuthStore } from '../store/authStore';

/** 登录守卫：未登录跳转到 /login，加载中显示等待状态 */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore(s => s.isAuthenticated);
  const loading = useAuthStore(s => s.loading);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-surface-900">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-sm text-gray-400 dark:text-gray-500">正在恢复登录状态…</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

/** 学生/家长守卫：教师/管理员访问学生专属页面时重定向到 /teacher */
function RequireStudent({ children }: { children: React.ReactNode }) {
  const role = useAuthStore(s => s.learner?.role);

  if (role === 'teacher' || role === 'admin') {
    return <Navigate to="/teacher" replace />;
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
      { path: 'chat', element: <RequireStudent><ChatPage /></RequireStudent> },
      { path: 'lecture/:chapterId', element: <RequireStudent><LecturePage /></RequireStudent> },
      { path: 'lecture/section/:sectionId', element: <RequireStudent><LecturePage /></RequireStudent> },
      { path: 'textbook/:subjectId', element: <RequireStudent><TextbookViewPage /></RequireStudent> },
      { path: 'resources', element: <RequireStudent><ResourceLibrary /></RequireStudent> },
      { path: 'resources/:id', element: <RequireStudent><ResourceLibrary /></RequireStudent> },
      { path: 'kg', element: <RequireStudent><KnowledgeGraphPage /></RequireStudent> },
      { path: 'path', element: <RequireStudent><LearningPathPage /></RequireStudent> },
      { path: 'learning-path', element: <RequireStudent><LearningPathPage /></RequireStudent> },
      { path: 'profile', element: <RequireStudent><ProfilePage /></RequireStudent> },
      { path: 'analytics', element: <RequireStudent><LearningAnalyticsPage /></RequireStudent> },
      { path: 'timeline', element: <RequireStudent><LearningTimelinePage /></RequireStudent> },
      { path: 'generate', element: <RequireStudent><ResourceGenerationPage /></RequireStudent> },
      { path: 'practice', element: <RequireStudent><PracticePage /></RequireStudent> },
      { path: 'history', element: <RequireStudent><ConversationHistoryPage /></RequireStudent> },
      { path: 'settings', element: <SettingsPage /> },
      { path: 'admin', element: <AdminDashboard /> },
      { path: 'review-queue', element: <ReviewQueuePage /> },
      { path: 'teacher', element: <TeacherHome /> },
      { path: 'teacher/classes/:id', element: <TeacherClassDetail /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]);

export default router;
