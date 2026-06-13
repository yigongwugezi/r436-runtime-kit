import { createBrowserRouter } from 'react-router-dom';
import AppLayout from '../components/layout/AppLayout';
import Home from '../pages/Home';
import ChatPage from '../pages/ChatPage';
import ResourceLibrary from '../pages/ResourceLibrary';
import LearningPathPage from '../pages/LearningPathPage';
import ProfilePage from '../pages/ProfilePage';
import NotFound from '../pages/NotFound';

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Home /> },
      { path: 'chat', element: <ChatPage /> },
      { path: 'resources', element: <ResourceLibrary /> },
      { path: 'resources/:id', element: <ResourceLibrary /> },
      { path: 'path', element: <LearningPathPage /> },
      { path: 'profile', element: <ProfilePage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]);

export default router;
