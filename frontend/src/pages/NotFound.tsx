import { useNavigate } from 'react-router-dom';
import { Home, ArrowLeft } from 'lucide-react';

export default function NotFound() {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-6">
      <div className="text-8xl font-extrabold text-gray-100 mb-4">404</div>
      <h2 className="text-xl font-bold text-gray-800 mb-2">页面未找到</h2>
      <p className="text-sm text-gray-400 max-w-xs mb-8">
        你访问的页面不存在，可能已被移动或删除。
      </p>
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          className="px-5 py-2.5 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 transition-all inline-flex items-center gap-2"
        >
          <ArrowLeft className="w-4 h-4" />
          返回
        </button>
        <button
          onClick={() => navigate('/')}
          className="px-5 py-2.5 bg-gray-900 text-white rounded-xl text-sm font-medium hover:bg-gray-800 transition-all inline-flex items-center gap-2"
        >
          <Home className="w-4 h-4" />
          回到首页
        </button>
      </div>
    </div>
  );
}
