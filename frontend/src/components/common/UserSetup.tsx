import { useState, useEffect } from 'react';
import { User, Edit2, Check, X, Save, LogOut } from 'lucide-react';
import { readStorageItem, writeStorageItem, runtimeStorageKeys } from '../../utils/storageKeys';

/* ===================================================================
 * 用户信息管理
 * localStorage 存储：
 *   r436_runtime_learner_name  - 学习者昵称
 *   r436_runtime_current_session_id - 当前 sessionId
 * =================================================================== */

function loadLearner(): string {
  return readStorageItem(runtimeStorageKeys.learnerName) || '';
}

function saveLearner(name: string) {
  writeStorageItem(runtimeStorageKeys.learnerName, name);
}

/* ===================================================================
 * 创建/切换学习者组件
 * =================================================================== */
export default function UserSetup() {
  const [name, setName] = useState(loadLearner);
  const [editing, setEditing] = useState(!name);
  const [input, setInput] = useState(name);

  const handleSave = () => {
    const trimmed = input.trim();
    if (trimmed) {
      setName(trimmed);
      saveLearner(trimmed);
      setEditing(false);
    }
  };

  if (!editing) {
    return (
      <div className="flex items-center gap-2.5 px-3 py-2 bg-white/80 backdrop-blur-sm border border-gray-100 rounded-xl shadow-sm">
        <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white text-xs font-bold shadow-sm">
          {name?.[0] || '?'}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-gray-800 truncate">{name || '未命名学习者'}</p>
          <p className="text-[9px] text-gray-400">学习者</p>
        </div>
        <button
          onClick={() => { setInput(name); setEditing(true); }}
          className="p-1.5 rounded-lg hover:bg-gray-50 text-gray-400 hover:text-gray-600 transition-colors"
          title="修改昵称"
        >
          <Edit2 className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div className="px-3 py-2 bg-white/80 backdrop-blur-sm border border-gray-100 rounded-xl shadow-sm">
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-brand-100 to-brand-200 flex items-center justify-center flex-shrink-0">
          <User className="w-4 h-4 text-brand-500" />
        </div>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSave()}
          placeholder="输入你的昵称…"
          className="flex-1 text-xs bg-transparent border-none outline-none text-gray-700 placeholder-gray-300 min-w-0"
          autoFocus
          maxLength={20}
        />
        <button
          onClick={handleSave}
          disabled={!input.trim()}
          className="p-1.5 rounded-lg hover:bg-brand-50 text-brand-500 hover:text-brand-600 disabled:opacity-30 transition-colors"
        >
          <Check className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

/* ===================================================================
 * 显示当前用户信息
 * =================================================================== */
export function useLearner() {
  const [learner, setLearner] = useState(loadLearner);

  useEffect(() => {
    const handler = () => setLearner(loadLearner());
    window.addEventListener('storage', handler);
    return () => window.removeEventListener('storage', handler);
  }, []);

  return {
    name: learner || '学习者',
    isSet: !!learner,
  };
}
