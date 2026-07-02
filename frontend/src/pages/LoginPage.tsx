import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Brain, Eye, EyeOff, User, ChevronDown, GraduationCap, FileText } from 'lucide-react';
import { useAuthStore, getLegacyLearner } from '../store/authStore';
import { getMetaOptions } from '../api/auth';

export { getLegacyLearner };

const ROLES = [
  { value: 'student', label: '🎓 学生' },
  { value: 'parent', label: '👨‍👩‍👧 家长' },
  { value: 'teacher', label: '📚 教师' },
] as const;

export default function LoginPage() {
  const nav = useNavigate();
  const auth = useAuthStore();

  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [nickname, setNickname] = useState('');
  const [role, setRole] = useState('student');
  const [grade, setGrade] = useState('');
  const [targetExam, setTargetExam] = useState('');
  const [studentNo, setStudentNo] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Meta options for dropdowns
  const [gradeOptions, setGradeOptions] = useState<string[]>([]);
  const [examOptions, setExamOptions] = useState<string[]>([]);

  useEffect(() => {
    getMetaOptions().then(opts => {
      setGradeOptions(opts.grades);
      setExamOptions(opts.exams);
    }).catch(() => {});
  }, []);

  const trimId = identifier.replace(/\s/g, '');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (mode === 'login') {
      if (!trimId) { setError('请输入手机号或学号'); return; }
    } else {
      if (!trimId || trimId.length < 11) { setError('请输入正确手机号'); return; }
    }
    if (!password || password.length < 6) { setError('密码至少6位'); return; }
    if (mode === 'register' && !nickname.trim()) { setError('请输入昵称'); return; }

    setLoading(true);
    try {
      if (mode === 'login') {
        await auth.login(trimId, password);
      } else {
        await auth.register({
          phone: trimId,
          password,
          nickname: nickname.trim() || '学习者',
          role,
          grade: grade || null,
          target_exam: targetExam || null,
          student_no: studentNo.trim() || null,
        });
      }
      nav('/');
    } catch (err: any) {
      setError(err?.message || (mode === 'login' ? '登录失败' : '注册失败'));
    } finally {
      setLoading(false);
    }
  };

  const switchMode = () => {
    setMode(m => m === 'login' ? 'register' : 'login');
    setError('');
  };

  const legacy = getLegacyLearner();

  return (
    <div className="min-h-screen bg-surface-50 dark:bg-surface-900 flex items-center justify-center p-6">
      <div className={mode === 'register' ? 'w-full max-w-md animate-fade-in' : 'w-full max-w-sm animate-fade-in'}>
        {/* ── Logo ── */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-r from-primary-600 to-accent-600 flex items-center justify-center mx-auto mb-4 shadow-soft">
            <Brain className="w-8 h-8 text-white" />
          </div>
          <h1 className="font-display text-2xl font-bold text-surface-800 dark:text-gray-100">EduAgent</h1>
          <p className="text-surface-400 dark:text-gray-500 text-sm mt-1">AI 个性化学习平台</p>
        </div>

        {/* ── Card ── */}
        <div className="bg-white dark:bg-surface-800 rounded-2xl p-6 shadow-soft">
          <h2 className="font-display text-lg font-bold text-surface-800 dark:text-gray-100 mb-5">
            {mode === 'login' ? '登录' : '注册'}
          </h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Identifier */}
            <div>
              <label className="text-xs font-medium text-surface-500 dark:text-gray-400 mb-1 block">
                {mode === 'login' ? '手机号 / 学号' : '手机号'}
              </label>
              <input
                type={mode === 'login' ? 'text' : 'tel'}
                value={identifier}
                maxLength={mode === 'login' ? 32 : 13}
                onChange={e => {
                  if (mode === 'register') {
                    setIdentifier(e.target.value.replace(/\D/g, '').replace(/(\d{3})(\d{4})(\d{0,4})/, (_, a, b, c) => c ? `${a} ${b} ${c}` : b ? `${a} ${b}` : a));
                  } else {
                    setIdentifier(e.target.value);
                  }
                }}
                placeholder={mode === 'login' ? '手机号或学号' : '138 0000 0000'}
                className="w-full px-4 py-3 bg-surface-50 dark:bg-surface-700 border border-surface-200 dark:border-surface-600 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary-200 dark:focus:ring-primary-500/30 dark:text-gray-100 transition-all"
              />
            </div>

            {/* Password */}
            <div>
              <label className="text-xs font-medium text-surface-500 dark:text-gray-400 mb-1 block">密码</label>
              <div className="relative">
                <input
                  type={showPwd ? 'text' : 'password'} value={password} maxLength={128}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="至少6位"
                  className="w-full px-4 py-3 pr-10 bg-surface-50 dark:bg-surface-700 border border-surface-200 dark:border-surface-600 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary-200 dark:focus:ring-primary-500/30 dark:text-gray-100 transition-all"
                />
                <button type="button" onClick={() => setShowPwd(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-surface-400 hover:text-surface-600 dark:hover:text-gray-300">
                  {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {/* Nickname (register only) */}
            {mode === 'register' && (
              <div>
                <label className="text-xs font-medium text-surface-500 dark:text-gray-400 mb-1 block">昵称</label>
                <div className="relative">
                  <User size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" />
                  <input
                    type="text" value={nickname} maxLength={20}
                    onChange={e => setNickname(e.target.value)}
                    placeholder="你的称呼"
                    className="w-full pl-10 pr-4 py-3 bg-surface-50 dark:bg-surface-700 border border-surface-200 dark:border-surface-600 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary-200 dark:focus:ring-primary-500/30 dark:text-gray-100 transition-all"
                  />
                </div>
              </div>
            )}

            {/* Register-only fields */}
            {mode === 'register' && (
              <>
                {/* Role selector */}
                <div>
                  <label className="text-xs font-medium text-surface-500 dark:text-gray-400 mb-1 block">角色</label>
                  <div className="grid grid-cols-3 gap-2">
                    {ROLES.map(r => (
                      <button key={r.value} type="button" onClick={() => setRole(r.value)}
                        className={`py-2.5 px-2 rounded-xl text-xs font-medium border transition-all ${
                          role === r.value
                            ? 'bg-primary-50 dark:bg-primary-500/20 border-primary-300 dark:border-primary-500/40 text-primary-700 dark:text-primary-300'
                            : 'bg-surface-50 dark:bg-surface-700 border-surface-200 dark:border-surface-600 text-surface-500 dark:text-gray-400 hover:border-surface-300'
                        }`}>
                        {r.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Grade + Target Exam row */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-medium text-surface-500 dark:text-gray-400 mb-1 block">
                      <GraduationCap size={12} className="inline mr-1" />年级
                    </label>
                    <select value={grade} onChange={e => setGrade(e.target.value)}
                      className="w-full px-3 py-3 bg-surface-50 dark:bg-surface-700 border border-surface-200 dark:border-surface-600 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary-200 dark:focus:ring-primary-500/30 dark:text-gray-100 transition-all appearance-none cursor-pointer">
                      <option value="">不选择</option>
                      {gradeOptions.map(g => <option key={g} value={g}>{g}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-surface-500 dark:text-gray-400 mb-1 block">
                      <FileText size={12} className="inline mr-1" />目标考试
                    </label>
                    <select value={targetExam} onChange={e => setTargetExam(e.target.value)}
                      className="w-full px-3 py-3 bg-surface-50 dark:bg-surface-700 border border-surface-200 dark:border-surface-600 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary-200 dark:focus:ring-primary-500/30 dark:text-gray-100 transition-all appearance-none cursor-pointer">
                      <option value="">不选择</option>
                      {examOptions.map(ex => <option key={ex} value={ex}>{ex}</option>)}
                    </select>
                  </div>
                </div>

                {/* Student No */}
                <div>
                  <label className="text-xs font-medium text-surface-500 dark:text-gray-400 mb-1 block">学号（可选）</label>
                  <input
                    type="text" value={studentNo} maxLength={32}
                    onChange={e => setStudentNo(e.target.value)}
                    placeholder="如：2024001"
                    className="w-full px-4 py-3 bg-surface-50 dark:bg-surface-700 border border-surface-200 dark:border-surface-600 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary-200 dark:focus:ring-primary-500/30 dark:text-gray-100 transition-all"
                  />
                </div>
              </>
            )}

            {/* Error */}
            {error && (
              <p className="text-sm text-error-500 bg-error-50 dark:bg-error-500/10 rounded-lg px-3 py-2">{error}</p>
            )}

            {/* Submit */}
            <button type="submit" disabled={loading}
              className="w-full py-3 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white rounded-xl text-sm font-semibold transition-colors">
              {loading ? '处理中...' : mode === 'login' ? '登录' : '注册并开始'}
            </button>
          </form>

          {/* Switch mode */}
          <p className="text-center text-sm text-surface-400 dark:text-gray-500 mt-4">
            {mode === 'login' ? '还没有账号？' : '已有账号？'}
            <button onClick={switchMode} className="ml-1 text-primary-600 hover:text-primary-700 font-medium">
              {mode === 'login' ? '立即注册' : '去登录'}
            </button>
          </p>

          {/* Legacy migration hint */}
          {legacy && mode === 'login' && (
            <div className="mt-4 p-3 bg-warning-50 dark:bg-warning-500/10 rounded-xl border border-warning-200 dark:border-warning-500/20">
              <p className="text-xs text-warning-700 dark:text-warning-400">
                检测到本地学习数据（{legacy.name}）。登录后可在设置中迁移到新账号。
              </p>
            </div>
          )}
        </div>

        <p className="text-center text-xs text-surface-300 dark:text-gray-600 mt-5">
          首次使用请先注册
        </p>
      </div>
    </div>
  );
}
