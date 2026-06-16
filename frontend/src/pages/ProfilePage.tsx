import { useNavigate } from 'react-router-dom';
import { useProfile } from '../hooks/useProfile';
import { useChatStore } from '../store/chatStore';
import { DIMENSION_LABELS, type ProfileDimension, type DimensionKey } from '../types/profile';
import { DIMENSION_COLORS } from '../utils/constants';
import { formatDuration, timeAgo } from '../utils/format';
import {
  User, Clock, Target, TrendingUp, Zap, BookOpen, Brain, Shield,
  Sparkles, AlertCircle, CheckCircle2, ArrowRight, Info, AlertTriangle, RefreshCw,
} from 'lucide-react';
import Loading from '../components/common/Loading';
import EmptyState from '../components/common/EmptyState';
import SourceBadge, { UpdateTimeRow, type DataSource } from '../components/common/SourceBadge';

/* ===================================================================
 * 画像完整度常量
 * =================================================================== */
const ALL_DIMENSION_KEYS: DimensionKey[] = [
  'major_background', 'knowledge_base', 'learning_goal', 'cognitive_style',
  'error_patterns', 'coding_ability', 'learning_progress', 'interest_direction',
  'learning_rhythm', 'self_efficacy',
];

const MISSING_DIMENSION_TIPS: Record<DimensionKey, string> = {
  major_background: '你可以说："我是软件工程大三学生" 或 "我工作是前端开发"',
  knowledge_base: '你可以说："我学过 Python 基础，会一点 React"',
  learning_goal: '你可以说："我想两周内通过数据结构考试" 或 "我想入门机器学习"',
  cognitive_style: '你可以说："我更喜欢先看整体框架再深入细节"',
  error_patterns: '你可以说："我递归和动态规划总是出错"',
  coding_ability: '你可以说："我能写 LeetCode 中等题" 或 "我基本不会编程"',
  learning_progress: '你可以说："Tree 和 Graph 章节已学完"',
  interest_direction: '你可以说："我想做 NLP 方向" 或 "我感兴趣的是后端开发"',
  learning_rhythm: '你可以说："我每天能学 2 小时" 或 "我只有周末有空"',
  self_efficacy: '你可以说："我觉得自己学得还行" 或 "我有点没信心"',
};

/* ===================================================================
 * 雷达图
 * =================================================================== */
function DimensionRadar({ dimensions }: { dimensions: ProfileDimension[] }) {
  const size = 300;
  const center = size / 2;
  const radius = 115;
  const levels = 5;
  const angleSlice = (2 * Math.PI) / dimensions.length;

  const getPoint = (i: number, value: number) => {
    const angle = angleSlice * i - Math.PI / 2;
    const r = (value / 100) * radius;
    return {
      x: center + r * Math.cos(angle),
      y: center + r * Math.sin(angle),
    };
  };

  const rings = Array.from({ length: levels }, (_, i) => ((i + 1) / levels) * radius);

  const dataPoints = dimensions.map((d, i) => getPoint(i, d.value));
  const polygonPath = dataPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ') + ' Z';

  return (
    <div className="flex justify-center">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="overflow-visible">
        {/* 同心网格 */}
        {rings.map((r, ri) => (
          <circle
            key={ri} cx={center} cy={center} r={r}
            fill="none" stroke={ri === levels - 1 ? '#cbd5e1' : '#e2e8f0'}
            strokeWidth={ri === levels - 1 ? 1.5 : 0.5}
            strokeDasharray={ri === 0 ? 'none' : '3 3'}
          />
        ))}
        {/* 轴线 */}
        {dimensions.map((_, i) => {
          const end = getPoint(i, 100);
          return <line key={i} x1={center} y1={center} x2={end.x} y2={end.y} stroke="#e2e8f0" strokeWidth={0.5} />;
        })}
        {/* 数据多边形 */}
        <path d={polygonPath} fill="rgba(99,102,241,0.12)" stroke="url(#radarGradient)" strokeWidth={2} />
        {/* 数据点 */}
        {dataPoints.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={5} fill="#6366f1" stroke="white" strokeWidth={2.5} className="drop-shadow-sm" />
        ))}
        {/* 标签 */}
        {dimensions.map((d, i) => {
          const labelPoint = getPoint(i, 138);
          return (
            <text
              key={i} x={labelPoint.x} y={labelPoint.y}
              textAnchor="middle" dominantBaseline="middle"
              className="text-[10px] font-semibold"
              fill="#475569"
            >
              {d.label.length > 4 ? d.label.slice(0, 4) : d.label}
            </text>
          );
        })}
        {/* 渐变定义 */}
        <defs>
          <linearGradient id="radarGradient" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#6366f1" />
            <stop offset="100%" stopColor="#8b5cf6" />
          </linearGradient>
        </defs>
      </svg>
    </div>
  );
}

/* ===================================================================
 * 维度进度条
 * =================================================================== */
function DimensionBar({ dim, index }: { dim: ProfileDimension; index: number }) {
  const color = DIMENSION_COLORS[index % DIMENSION_COLORS.length];
  return (
    <div className="flex items-center gap-3">
      <div className="w-20 text-xs text-gray-500 text-right flex-shrink-0">{dim.label}</div>
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${dim.value}%`, backgroundColor: color }} />
      </div>
      <div className="w-10 text-xs font-semibold text-right" style={{ color }}>{dim.value}</div>
    </div>
  );
}

/* ===================================================================
 * 维度卡片 — 带来源标记
 * =================================================================== */
function DimensionCard({ dim, index }: { dim: ProfileDimension; index: number }) {
  const color = DIMENSION_COLORS[index % DIMENSION_COLORS.length];
  const source = (dim.source || (dim.confidence >= 0.85 ? 'user_input' : dim.confidence >= 0.6 ? 'system_inferred' : 'system_inferred')) as DataSource;

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-4 hover:shadow-md transition-all duration-200">
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
          <h4 className="text-sm font-semibold text-gray-800">{dim.label}</h4>
        </div>
        {/* 来源标记 */}
        <SourceBadge source={source} size="sm" />
      </div>

      {/* 掌握度 */}
      <div className="flex items-center gap-3 mb-2">
        <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-full rounded-full transition-all duration-700" style={{ width: `${dim.value}%`, backgroundColor: color }} />
        </div>
        <span className="text-sm font-bold" style={{ color }}>{dim.value}%</span>
      </div>

      {/* 描述 */}
      <p className="text-xs text-gray-500 leading-relaxed">{dim.description || '待补充'}</p>

      {/* 置信度 */}
      <div className="flex items-center gap-1.5 mt-2 text-[10px] text-gray-400">
        <Info className="w-3 h-3" />
        置信度 {(dim.confidence * 100).toFixed(0)}%
      </div>
    </div>
  );
}

/* ===================================================================
 * 主页面
 * =================================================================== */
export default function ProfilePage() {
  const navigate = useNavigate();
  const { profile, loading, error } = useProfile();
  const dataVersion = useChatStore((state) => state.dataVersion);

  if (loading && !profile) return <Loading fullScreen text="加载画像..." />;

  if (error && !profile) {
    return (
      <EmptyState
        icon={<AlertTriangle className="w-8 h-8" />}
        title="画像加载失败"
        description={error}
      />
    );
  }

  if (!profile) {
    return (
      <EmptyState
        icon={<User className="w-8 h-8" />}
        title="暂无学习画像"
        description="在 AI 对话中描述你的专业、基础和目标，系统会自动构建你的专属学习画像"
        action={
          <button
            onClick={() => navigate('/chat')}
            className="mt-3 px-5 py-2.5 bg-gray-900 text-white rounded-xl text-sm font-semibold hover:bg-gray-800 transition-all inline-flex items-center gap-2"
          >
            <Sparkles className="w-4 h-4" />
            去对话页生成画像
          </button>
        }
      />
    );
  }

  // 计算完整度
  const existingKeys = new Set(profile.dimensions.map((d) => d.key));
  const completedCount = ALL_DIMENSION_KEYS.filter((k) => existingKeys.has(k)).length;
  const completeness = Math.round((completedCount / ALL_DIMENSION_KEYS.length) * 100);
  const missingDimensions = ALL_DIMENSION_KEYS.filter((k) => !existingKeys.has(k));

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 md:py-8">
      {/* ========== 错误提示 ========== */}
      {error && (
        <div className="mb-6 p-3 bg-red-50 border border-red-100 rounded-xl flex items-center gap-2 text-xs text-red-600">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* ========== 顶部信息卡 — 含完整度 ========== */}
      <div className="bg-white border border-gray-100 rounded-2xl p-6 md:p-8 mb-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center gap-6">
          {/* 头像 + 完整度环 */}
          <div className="relative flex-shrink-0">
            <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white text-2xl font-bold shadow-lg shadow-brand-200">
              {profile.nickname?.[0] || '学'}
            </div>
            {/* 完整度环 */}
            <svg className="absolute -bottom-1 -right-1 w-10 h-10" viewBox="0 0 36 36">
              <circle cx="18" cy="18" r="15" fill="none" stroke="#e2e8f0" strokeWidth="3" />
              <circle
                cx="18" cy="18" r="15" fill="none"
                stroke={completeness >= 80 ? '#22c55e' : completeness >= 50 ? '#f59e0b' : '#ef4444'}
                strokeWidth="3" strokeLinecap="round"
                strokeDasharray={`${completeness * 0.942} 94.2`}
                transform="rotate(-90 18 18)"
                className="transition-all duration-1000"
              />
            </svg>
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 mb-1">
              <h1 className="text-2xl font-extrabold text-gray-900">{profile.nickname || '学习者'}</h1>
              <span
                className={`px-2.5 py-0.5 rounded-lg text-[11px] font-semibold border ${
                  completeness >= 80
                    ? 'bg-green-50 text-green-600 border-green-200'
                    : completeness >= 50
                      ? 'bg-amber-50 text-amber-600 border-amber-200'
                      : 'bg-red-50 text-red-500 border-red-200'
                }`}
              >
                画像完整度 {completeness}%
              </span>
            </div>
            <p className="text-sm text-gray-500 mb-3">
              {profile.dimensions.find((d) => d.key === 'major_background')?.description || '等待画像分析…'}
            </p>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" />
                累计 {formatDuration(profile.history.totalStudyMinutes)}
              </span>
              <span className="flex items-center gap-1">
                <TrendingUp className="w-3.5 h-3.5" />
                正确率 {profile.history.quizAccuracy}%
              </span>
              <span className="flex items-center gap-1">
                <Zap className="w-3.5 h-3.5" />
                连续 {profile.history.streak} 天
              </span>
              <span className="flex items-center gap-1 text-brand-600">
                <RefreshCw className="w-3 h-3" />
                画像更新：{timeAgo(profile.updatedAt)}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 flex-shrink-0">
            <div className="text-center px-3 py-2 bg-brand-50 rounded-xl">
              <div className="text-base font-bold text-brand-600">{profile.dimensions.length}</div>
              <div className="text-[10px] text-brand-500">维度画像</div>
            </div>
            <div className="text-center px-3 py-2 bg-red-50 rounded-xl">
              <div className="text-base font-bold text-red-500">{profile.weaknesses.length}</div>
              <div className="text-[10px] text-red-400">知识短板</div>
            </div>
            <div className="text-center px-3 py-2 bg-green-50 rounded-xl">
              <div className="text-base font-bold text-green-500">{profile.history.completedTopics.length}</div>
              <div className="text-[10px] text-green-400">已完成</div>
            </div>
          </div>
        </div>

        {/* 完整度进度条 */}
        <div className="mt-5 pt-4 border-t border-gray-50">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs text-gray-500">画像完整度</span>
            <span className="text-xs font-semibold text-gray-700">{completeness}%</span>
          </div>
          <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-700 ${
                completeness >= 80 ? 'bg-green-500' : completeness >= 50 ? 'bg-amber-500' : 'bg-red-400'
              }`}
              style={{ width: `${completeness}%` }}
            />
          </div>
        </div>
      </div>

      {/* ========== 缺失维度提示 ========== */}
      {missingDimensions.length > 0 && (
        <div className="mb-6 p-4 bg-amber-50/70 border border-amber-100 rounded-2xl">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-xl bg-amber-100 flex items-center justify-center flex-shrink-0">
              <AlertCircle className="w-4 h-4 text-amber-600" />
            </div>
            <div className="flex-1">
              <h4 className="text-sm font-semibold text-amber-800 mb-1">补充以下信息，让画像更精准</h4>
              <p className="text-xs text-amber-600 mb-2">
                缺少 {missingDimensions.length} 个维度，回到对话页补充你的信息。
              </p>
              <div className="space-y-2">
                {missingDimensions.map((key) => (
                  <div key={key} className="flex items-start gap-2 bg-white border border-amber-200 rounded-xl p-2.5">
                    <div className="flex-shrink-0 mt-0.5">
                      <span className="w-5 h-5 rounded-lg bg-amber-100 flex items-center justify-center text-[10px] font-bold text-amber-600">
                        {DIMENSION_LABELS[key].slice(0, 1)}
                      </span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold text-amber-800">缺少 {DIMENSION_LABELS[key]}</p>
                      <p className="text-[10px] text-amber-600 mt-0.5">{MISSING_DIMENSION_TIPS[key]}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <button
              onClick={() => navigate('/chat')}
              className="flex items-center gap-1 px-3 py-1.5 bg-amber-500 text-white rounded-lg text-xs font-medium hover:bg-amber-600 transition-colors flex-shrink-0"
            >
              去补充
              <ArrowRight className="w-3 h-3" />
            </button>
          </div>
        </div>
      )}

      {/* ========== 雷达图 + 维度详情 ========== */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 mb-6">
        {/* 雷达图 */}
        <div className="lg:col-span-3 bg-white border border-gray-100 rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Brain className="w-4 h-4 text-brand-500" />
            能力雷达图
          </h3>
          <DimensionRadar dimensions={profile.dimensions} />
        </div>

        {/* 维度进度条 */}
        <div className="lg:col-span-2 bg-white border border-gray-100 rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">各维度得分</h3>
          <div className="space-y-4">
            {profile.dimensions.map((dim, i) => (
              <DimensionBar key={dim.key} dim={dim} index={i} />
            ))}
          </div>
        </div>
      </div>

      {/* ========== 维度详情卡片 (含来源标记) ========== */}
      <div className="mb-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
          <Info className="w-4 h-4 text-brand-500" />
          维度详析
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {profile.dimensions.map((dim, i) => (
            <DimensionCard key={dim.key} dim={dim} index={i} />
          ))}
        </div>
      </div>

      {/* ========== 知识短板 ========== */}
      {profile.weaknesses.length > 0 && (
        <div className="mb-6 bg-white border border-gray-100 rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Target className="w-4 h-4 text-red-400" />
            知识短板 · 优先修复
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {profile.weaknesses.map((gap) => (
              <div key={gap.topic} className="flex items-center justify-between p-3.5 bg-red-50/60 border border-red-100 rounded-xl hover:shadow-sm transition-shadow">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-gray-800 truncate">{gap.topic}</p>
                  <p className="text-[10px] text-gray-400 mt-0.5">优先修复 P{gap.priority}</p>
                </div>
                <div className="text-right flex-shrink-0 ml-3">
                  <div className="text-xs font-bold text-red-500">{gap.mastery}%</div>
                  <div className="h-1.5 w-16 bg-red-100 rounded-full mt-1 overflow-hidden">
                    <div className="h-full bg-red-400 rounded-full" style={{ width: `${gap.mastery}%` }} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ========== 学习偏好 ========== */}
      <div className="mb-6 bg-white border border-gray-100 rounded-2xl p-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-brand-500" />
          学习偏好
        </h3>
        <div className="flex flex-wrap gap-3">
          <span className="px-3 py-1.5 bg-brand-50 text-brand-600 rounded-xl text-xs font-medium border border-brand-100">
            📚 偏好格式：{(profile.preferences.preferredFormats || ['文本']).join(' / ')}
          </span>
          <span className="px-3 py-1.5 bg-green-50 text-green-600 rounded-xl text-xs font-medium border border-green-100">
            ⏱ 学习节奏：{formatDuration(profile.preferences.paceMinutes)} / 次
          </span>
          <span className="px-3 py-1.5 bg-amber-50 text-amber-600 rounded-xl text-xs font-medium border border-amber-100">
            📊 难度等级：{profile.preferences.difficulty === 'beginner' ? '入门' : profile.preferences.difficulty === 'intermediate' ? '进阶' : '高级'}
          </span>
          <span className="px-3 py-1.5 bg-purple-50 text-purple-600 rounded-xl text-xs font-medium border border-purple-100">
            🎨 讲解风格：{profile.preferences.explainStyle === 'diagram' ? '图解优先' : profile.preferences.explainStyle === 'code' ? '代码优先' : profile.preferences.explainStyle === 'case' ? '案例优先' : '理论优先'}
          </span>
        </div>
      </div>

      <div className="text-center py-6 border-t border-gray-50">
        <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-xs text-gray-400">
          <UpdateTimeRow label="画像更新" timestamp={profile.updatedAt} source="agent_generated" />
        </div>
        <p className="text-xs text-gray-400 mt-2">
          {dataVersion > 0 ? '已同步最新对话数据' : '等待新对话触发数据更新'}
        </p>
        <div className="flex items-center justify-center gap-3 mt-3">
          <SourceBadge source="user_input" size="xs" />
          <SourceBadge source="agent_generated" size="xs" />
          <SourceBadge source="system_inferred" size="xs" />
        </div>
        <p className="text-[10px] text-gray-300 mt-2">数据来源包含用户对话、智能体生成和系统推断</p>
      </div>
    </div>
  );
}
