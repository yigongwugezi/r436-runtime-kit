import { lazy, Suspense, type ComponentType } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import AppLayout from '../components/layout/AppLayout';
import ErrorBoundary from '../components/common/ErrorBoundary';
import { useAuthStore } from '../store/authStore';

const Home = lazy(() => import('../pages/Home'));
const ChatPage = lazy(() => import('../pages/ChatPage'));
const ResourceLibrary = lazy(() => import('../pages/ResourceLibrary'));
const LearningPathPage = lazy(() => import('../pages/LearningPathPage'));
const ProfilePage = lazy(() => import('../pages/ProfilePage'));
const LearningAnalyticsPage = lazy(() => import('../pages/LearningAnalyticsPage'));
const LearningTimelinePage = lazy(() => import('../pages/LearningTimelinePage'));
const KnowledgeGraphPage = lazy(() => import('../pages/KnowledgeGraphPage'));
const PracticePage = lazy(() => import('../pages/PracticePage'));
const ResourceGenerationPage = lazy(() => import('../pages/ResourceGenerationPage'));
const ConversationHistoryPage = lazy(() => import('../pages/ConversationHistoryPage'));
const SettingsPage = lazy(() => import('../pages/SettingsPage'));
const AdminDashboard = lazy(() => import('../pages/AdminDashboard'));
const ReviewQueuePage = lazy(() => import('../pages/ReviewQueuePage'));
const TeacherHome = lazy(() => import('../pages/TeacherHome'));
const TeacherClassDetail = lazy(() => import('../pages/TeacherClassDetail'));
const LoginPage = lazy(() => import('../pages/LoginPage'));
const LecturePage = lazy(() => import('../pages/LecturePage'));
const TextbookViewPage = lazy(() => import('../pages/TextbookViewPage'));
const TaskPage = lazy(() => import('../pages/TaskPage'));
const NotFound = lazy(() => import('../pages/NotFound'));

function RouteLoading() {
  return <div role="status" className="flex min-h-[40vh] items-center justify-center text-sm text-surface-400">Loading page…</div>;
}

function lazyRoute(Page: ComponentType) {
  return <ErrorBoundary><Suspense fallback={<RouteLoading />}><Page /></Suspense></ErrorBoundary>;
}

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
    element: lazyRoute(LoginPage),
  },
  {
    path: '/',
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: lazyRoute(Home) },
      { path: 'chat', element: <RequireStudent>{lazyRoute(ChatPage)}</RequireStudent> },
      { path: 'lecture/:chapterId', element: <RequireStudent>{lazyRoute(LecturePage)}</RequireStudent> },
      { path: 'lecture/section/:sectionId', element: <RequireStudent>{lazyRoute(LecturePage)}</RequireStudent> },
      { path: 'textbook/:subjectId', element: <RequireStudent>{lazyRoute(TextbookViewPage)}</RequireStudent> },
      { path: 'resources', element: <RequireStudent>{lazyRoute(ResourceLibrary)}</RequireStudent> },
      { path: 'resources/:id', element: <RequireStudent>{lazyRoute(ResourceLibrary)}</RequireStudent> },
      { path: 'task/:taskId', element: <RequireStudent>{lazyRoute(TaskPage)}</RequireStudent> },
      { path: 'kg', element: <RequireStudent>{lazyRoute(KnowledgeGraphPage)}</RequireStudent> },
      { path: 'path', element: <RequireStudent>{lazyRoute(LearningPathPage)}</RequireStudent> },
      { path: 'learning-path', element: <RequireStudent>{lazyRoute(LearningPathPage)}</RequireStudent> },
      { path: 'profile', element: <RequireStudent>{lazyRoute(ProfilePage)}</RequireStudent> },
      { path: 'analytics', element: <RequireStudent>{lazyRoute(LearningAnalyticsPage)}</RequireStudent> },
      { path: 'timeline', element: <RequireStudent>{lazyRoute(LearningTimelinePage)}</RequireStudent> },
      { path: 'generate', element: <RequireStudent>{lazyRoute(ResourceGenerationPage)}</RequireStudent> },
      { path: 'practice', element: <RequireStudent>{lazyRoute(PracticePage)}</RequireStudent> },
      { path: 'history', element: <RequireStudent>{lazyRoute(ConversationHistoryPage)}</RequireStudent> },
      { path: 'settings', element: lazyRoute(SettingsPage) },
      { path: 'admin', element: lazyRoute(AdminDashboard) },
      { path: 'review-queue', element: lazyRoute(ReviewQueuePage) },
      { path: 'teacher', element: lazyRoute(TeacherHome) },
      { path: 'teacher/classes/:id', element: lazyRoute(TeacherClassDetail) },
      { path: '*', element: lazyRoute(NotFound) },
    ],
  },
]);

export default router;
