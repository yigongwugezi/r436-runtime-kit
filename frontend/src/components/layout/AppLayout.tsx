import { Outlet } from 'react-router-dom';
import Header from './Header';
import BottomNav from './BottomNav';
import { ToastProvider } from '../common/Toast';

export default function AppLayout() {
  return (
    <ToastProvider>
      <div className="min-h-screen bg-white flex flex-col">
        <Header />
        <main className="flex-1">
          <Outlet />
        </main>
        <BottomNav />
      </div>
    </ToastProvider>
  );
}
