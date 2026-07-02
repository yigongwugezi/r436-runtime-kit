import { useState, useEffect, useRef } from 'react';
import { ChevronDown, Users, RefreshCw } from 'lucide-react';
import { getCurrentLearner, useAuthStore } from '../../store/authStore';
import client from '../../api/client';

interface ChildInfo {
  id: string;
  nickname: string;
  grade: string | null;
}

const ROLE_LABELS: Record<string, { label: string; icon: string }> = {
  student: { label: '学生视图', icon: '🎓' },
  parent: { label: '家长视图', icon: '👨‍👩‍👧' },
  teacher: { label: '教师视图', icon: '📚' },
  admin: { label: '管理员视图', icon: '⚙️' },
};

export default function RoleSwitcher() {
  const learner = getCurrentLearner();
  const [open, setOpen] = useState(false);
  const [children, setChildren] = useState<ChildInfo[]>([]);
  const [activeChild, setActiveChild] = useState<ChildInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const role = learner?.role || 'student';
  const roleInfo = ROLE_LABELS[role] || ROLE_LABELS.student;

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // Load children on mount for parent role
  useEffect(() => {
    if (role === 'parent') {
      loadRoleData();
    }
  }, [role]);

  const loadRoleData = async () => {
    setLoading(true);
    try {
      const res = await client.post('/api/learner/switch-role', { role });
      const data = res.data as any;
      if (data.children) {
        setChildren(data.children.map((c: any) => ({
          id: c.id,
          nickname: c.nickname || c.name || '未命名',
          grade: c.grade || null,
        })));
        if (data.active_child) {
          setActiveChild({
            id: data.active_child.id,
            nickname: data.active_child.nickname || data.active_child.name || '未命名',
            grade: data.active_child.grade || null,
          });
        }
      }
    } catch {
      // Silently fail — just show current role
    } finally {
      setLoading(false);
    }
  };

  const handleSwitch = async (targetRole: string, targetLearnerId?: string) => {
    setLoading(true);
    try {
      await client.post('/api/learner/switch-role', {
        role: targetRole,
        target_learner_id: targetLearnerId || null,
      });
      if (targetRole === 'parent' && targetLearnerId) {
        const child = children.find(c => c.id === targetLearnerId);
        if (child) setActiveChild(child);
      }
    } catch {
      // Silently fail
    } finally {
      setLoading(false);
      setOpen(false);
    }
  };

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => { if (role === 'parent') { loadRoleData(); } setOpen(v => !v); }}
        disabled={loading}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
          bg-surface-50 dark:bg-surface-700 border border-surface-200 dark:border-surface-600
          text-surface-600 dark:text-gray-300 hover:bg-surface-100 dark:hover:bg-surface-600
          transition-colors disabled:opacity-50"
      >
        <span>{roleInfo.icon}</span>
        <span className="hidden sm:inline">{roleInfo.label}</span>
        {activeChild && (
          <span className="text-primary-500 dark:text-primary-400">
            · {activeChild.nickname}
          </span>
        )}
        <ChevronDown size={12} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-56 bg-white dark:bg-surface-800
          rounded-xl shadow-elevated border border-surface-200 dark:border-surface-600
          py-1.5 z-50 animate-fade-in">
          <div className="px-3 py-2 border-b border-surface-100 dark:border-surface-600">
            <p className="text-xs font-semibold text-surface-800 dark:text-gray-100">当前角色</p>
            <p className="text-[10px] text-surface-400 dark:text-gray-500">
              {roleInfo.icon} {roleInfo.label}
            </p>
          </div>

          {/* Role options */}
          {(['student', 'parent', 'teacher'] as const).map(r => (
            <button
              key={r}
              type="button"
              onClick={() => handleSwitch(r)}
              className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm transition-colors ${
                r === role
                  ? 'bg-primary-50 dark:bg-primary-500/10 text-primary-600 dark:text-primary-400 font-medium'
                  : 'text-surface-600 dark:text-gray-300 hover:bg-surface-50 dark:hover:bg-surface-700'
              }`}
            >
              <span>{ROLE_LABELS[r]?.icon}</span>
              <span>{ROLE_LABELS[r]?.label}</span>
              {r === role && <span className="ml-auto text-[10px] text-primary-400">当前</span>}
            </button>
          ))}

          {/* Parent: child selector */}
          {role === 'parent' && children.length > 0 && (
            <>
              <div className="border-t border-surface-100 dark:border-surface-600 my-1" />
              <div className="px-3 py-1.5">
                <p className="text-[10px] text-surface-400 dark:text-gray-500 uppercase tracking-wider flex items-center gap-1">
                  <Users size={10} /> 查看孩子
                </p>
              </div>
              {children.map(child => (
                <button
                  key={child.id}
                  type="button"
                  onClick={() => handleSwitch('parent', child.id)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm transition-colors ${
                    activeChild?.id === child.id
                      ? 'bg-accent-50 dark:bg-accent-500/10 text-accent-600 dark:text-accent-400 font-medium'
                      : 'text-surface-600 dark:text-gray-300 hover:bg-surface-50 dark:hover:bg-surface-700'
                  }`}
                >
                  <span>👤</span>
                  <span>{child.nickname}</span>
                  {child.grade && (
                    <span className="text-[10px] text-surface-400 dark:text-gray-500">{child.grade}</span>
                  )}
                </button>
              ))}
            </>
          )}

          {/* Teacher info */}
          {role === 'teacher' && (
            <div className="px-3 py-2 border-t border-surface-100 dark:border-surface-600">
              <p className="text-[10px] text-surface-400 dark:text-gray-500">
                教师视图已激活 — 可查看学生学情
              </p>
            </div>
          )}

          {/* Refresh button */}
          <div className="border-t border-surface-100 dark:border-surface-600 mt-1 pt-1">
            <button
              type="button"
              onClick={loadRoleData}
              disabled={loading}
              className="w-full flex items-center gap-2 px-3 py-2 text-xs text-surface-400 dark:text-gray-500
                hover:text-surface-600 dark:hover:text-gray-300 hover:bg-surface-50 dark:hover:bg-surface-700
                transition-colors"
            >
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
              刷新角色数据
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
