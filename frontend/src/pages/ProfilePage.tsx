import { useNavigate } from 'react-router-dom';
import { useProfile } from '../hooks/useProfile';
import { getCurrentLearner } from './LoginPage';
import { DIMENSION_COLORS } from '../utils/constants';
import { formatDuration, timeAgo } from '../utils/format';
import {
  User, Clock, Target, TrendingUp, Zap, BookOpen, Brain,
  Sparkles, AlertCircle, ArrowRight, Info, RefreshCw,
} from 'lucide-react';
import {
  PageLoading,
  PageEmpty,
  PageError,
  FallbackBanner,
  RefreshOverlay,
} from '../components/common/PageState';
import { DIMENSION_LABELS, type DimensionKey, type ProfileDimension } from '../types/profile';

const ALL_DIMENSION_KEYS: DimensionKey[] = [
  'major_background',
  'knowledge_base',
  'learning_goal',
  'cognitive_style',
  'error_patterns',
  'coding_ability',
  'learning_progress',
  'interest_direction',
  'learning_rhythm',
  'self_efficacy',
];

const SOURCE_LABELS: Record<string, { label: string; color: string }> = {
  user_input: { label: '用户提供', color: 'bg-blue-50 text-blue-600 border-blue-200' },
  inferred: { label: '系统推断', color: 'bg-amber-50 text-amber-600 border-amber-200' },
  llm_generated: { label: 'LLM 生成', color: 'bg-indigo-50 text-indigo-600 border-indigo-200' },
  rule_based_fallback: { label: '规则兜底', color: 'bg-slate-50 text-slate-600 border-slate-200' },
  diagnosis: { label: '诊断分析', color: 'bg-purple-50 text-purple-600 border-purple-200' },
  feedback: { label: '学习反馈', color: 'bg-green-50 text-green-600 border-green-200' },
};

function DimensionRadar({ dimensions }: { dimensions: ProfileDimension[] }) {
  const size = 300;
  const center = size / 2;
  const radius = 115;
  const levels = 5;
  const angleSlice = (2 * Math.PI) / dimensions.length;

  const getPoint = (i: number, score: number) => {
    const angle = angleSlice * i - Math.PI / 2;
    const r = (score / 100) * radius;
    return {
      x: center + r * Math.cos(angle),
      y: center + r * Math.sin(angle),
    };
  };

  const rings = Array.from({ length: levels }, (_, i) => ((i + 1) / levels) * radius);
  const dataPoints = dimensions.map((d, i) => getPoint(i, d.score));
  const polygonPath = dataPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ') + ' Z';

  return (
    <div className="flex justify-center">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="overflow-visible">
        {rings.map((r, ri) => (
          <circle
            key={ri}
            cx={center}
            cy={center}
            r={r}
            fill="none"
            stroke={ri === levels - 1 ? '#cbd5e1' : '#e2e8f0'}
            strokeWidth={ri === levels - 1 ? 1.5 : 0.5}
            strokeDasharray={ri === 0 ? 'none' : '3 3'}
          />
        ))}
        {dimensions.map((_, i) => {
          const end = getPoint(i, 100);
          return <line key={i} x1={center} y1={center} x2={end.x} y2={end.y} stroke="#e2e8f0" strokeWidth={0.5} />;
        })}
        <path d={polygonPath} fill="rgba(99,102,241,0.12)" stroke="url(#radarGradient)" strokeWidth={2} />
        {dataPoints.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={5} fill="#6366f1" stroke="white" strokeWidth={2.5} className="drop-shadow-sm" />
        ))}
        {dimensions.map((d, i) => {
          const labelPoint = getPoint(i, 138);
          return (
            <text
              key={i}
              x={labelPoint.x}
              y={labelPoint.y}
              textAnchor="middle"
              dominantBaseline="middle"
              className="text-[10px] font-semibold"
              fill="#475569"
            >
              {d.label.length > 4 ? d.label.slice(0, 4) : d.label}
            </text>
          );
        })}
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
 * 维度进度条（概要视图，仅分数+来源）
 * =================================================================== */
function DimensionBar({ dim, index }: { dim: ProfileDimension; index: number }) {
  const color = DIMENSION_COLORS[index % DIMENSION_COLORS.length];
  const sourceInfo = SOURCE_LABELS[dim.source];
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 text-[10px] text-gray-500 text-right flex-shrink-0 truncate" title={dim.label}>{dim.label}</div>
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${dim.score}%`, backgroundColor: color }} />
      </div>
      <div className="w-10 text-xs font-semibold text-right" style={{ color }}>{dim.score}</div>
      {sourceInfo && (
        <span className={`px-1.5 py-0.5 rounded text-[8px] font-medium border flex-shrink-0 ${sourceInfo.color}`}>
          {sourceInfo.label}
        </span>
      )}
    </div>
  );
}

/* ===================================================================
 * 维度卡片 — 分数 / 解释 / 证据 / 来源
 * =================================================================== */
function DimensionCard({ dim, index }: { dim: ProfileDimension; index: number }) {
  const color = DIMENSION_COLORS[index % DIMENSION_COLORS.length];
  const sourceInfo = SOURCE_LABELS[dim.source];

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-4 hover:shadow-md transition-all duration-200">
      {/* 头部：标签 + 来源 */}
      <div className="flex items-start justify-between mb-3 gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
          <h4 className="text-sm font-semibold text-gray-800 truncate">{dim.label}</h4>
        </div>
        {sourceInfo && (
          <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border whitespace-nowrap ${sourceInfo.color}`}>
            {sourceInfo.label}
          </span>
        )}
      </div>

      {/* 分数 */}
      <div className="flex items-center gap-3 mb-3">
        <div className="flex-1 h-2.5 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-full rounded-full transition-all duration-700" style={{ width: `${dim.score}%`, backgroundColor: color }} />
        </div>
        <span className="text-lg font-bold tabular-nums" style={{ color }}>{dim.score}</span>
      </div>

      {/* 数值 */}
      {dim.value && (
        <p className="text-xs text-gray-700 leading-relaxed mb-2">{dim.value}</p>
      )}

      {/* 解释 */}
      {(dim.explanation || dim.description) && (
        <p className="text-[11px] text-gray-500 leading-relaxed mb-2">
          {dim.explanation || dim.description}
        </p>
      )}

      {/* 证据 */}
      {dim.evidence && (
        <div className="mb-2 p-3 bg-gray-50 border border-gray-100 rounded-lg">
          <div className="flex items-center gap-1 mb-1.5">
            <Info className="w-3 h-3 text-gray-400" />
            <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">支撑证据</span>
          </div>
          <p className="text-[11px] text-gray-500 leading-relaxed">{dim.evidence}</p>
        </div>
      )}

      {/* 置信度 */}
      <div className="flex items-center gap-1.5 text-[10px] text-gray-400">
        <div className="flex-1 h-1 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-full rounded-full" style={{ width: `${dim.confidence * 100}%`, backgroundColor: color }} />
        </div>
        <span className="tabular-nums">置信度 {(dim.confidence * 100).toFixed(0)}%</span>
      </div>
    </div>
  );
}

export default function ProfilePage() {
  const navigate = useNavigate();
  const { profile, loading, error, fetchProfile } = useProfile();

  // —— Loading（首次无数据） ——
  if (loading && !profile) {
    return <PageLoading text="加载画像..." />;
  }

  // —— Error（首次无数据） ——
  if (error && !profile) {
    return (
      <PageError
        title="画像加载失败"
        description={error}
        onRetry={fetchProfile}
        onGoChat={() => navigate('/chat')}
      />
    );
  }

  // —— Empty（从未生成过画像） ——
  if (!profile) {
    return (
      <PageEmpty
        icon={<User className="w-8 h-8" />}
        title="暂无学习画像"
        description="先去聊天页输入你的专业背景、学习基础和目标，系统会自动构建 10 维专属学习画像"
        action={(
          <button
            onClick={() => navigate('/chat')}
            className="mt-3 px-5 py-2.5 bg-gray-900 text-white rounded-xl text-sm font-semibold hover:bg-gray-800 transition-all inline-flex items-center gap-2"
          >
            <Sparkles className="w-4 h-4" />
            去对话页生成画像
          </button>
        )}
      />
    );
  }

  const dimensionSources = profile.dimensions.map(d => d.source).filter(Boolean);
  const isFallback = dimensionSources.length > 0 && dimensionSources.every(s => s === 'rule_based_fallback' || s === 'inferred');

  const existingKeys = new Set(profile.dimensions.map((d) => d.key));
  const completedCount = ALL_DIMENSION_KEYS.filter((k) => existingKeys.has(k)).length;
  const completeness = Math.round((completedCount / ALL_DIMENSION_KEYS.length) * 100);
  const missingDimensions = ALL_DIMENSION_KEYS.filter((k) => !existingKeys.has(k));
  const learnerName = getCurrentLearner()?.name || profile.nickname || '学习者';
  const background = profile.dimensions.find((d) => d.key === 'major_background');

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 md:py-8 relative">
      {/* ========== 刷新遮罩 ========== */}
      {loading && profile && <RefreshOverlay />}

      {/* ========== 错误提示（已有画像但刷新失败） ========== */}
      {error && (
        <div className="mb-6 p-3 bg-red-50 border border-red-100 rounded-xl flex items-center gap-2 text-xs text-red-600">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
          <button onClick={fetchProfile} className="ml-auto flex items-center gap-1 px-2 py-1 bg-red-100 rounded-lg hover:bg-red-200 transition-colors">
            <RefreshCw className="w-3 h-3" /> 重试
          </button>
        </div>
      )}

      {/* ========== Fallback 提示 ========== */}
      {isFallback && !loading && (
        <FallbackBanner message="画像维度来自系统兜底规则。建议在 AI 对话中补充更多信息以获得精准画像。" />
      )}

      {/* ========== 顶部信息卡 — 含完整度 ========== */}
      <div className="bg-white border border-gray-100 rounded-2xl p-6 md:p-8 mb-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center gap-6">
          <div className="relative flex-shrink-0">
            <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white text-2xl font-bold shadow-lg shadow-brand-200">
              {learnerName?.[0] || '学'}
            </div>
            <svg className="absolute -bottom-1 -right-1 w-10 h-10" viewBox="0 0 36 36">
              <circle cx="18" cy="18" r="15" fill="none" stroke="#e2e8f0" strokeWidth="3" />
              <circle
                cx="18"
                cy="18"
                r="15"
                fill="none"
                stroke={completeness >= 80 ? '#22c55e' : completeness >= 50 ? '#f59e0b' : '#ef4444'}
                strokeWidth="3"
                strokeLinecap="round"
                strokeDasharray={`${completeness * 0.942} 94.2`}
                transform="rotate(-90 18 18)"
                className="transition-all duration-1000"
              />
            </svg>
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 mb-1">
              <h1 className="text-2xl font-extrabold text-gray-900">{learnerName}</h1>
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
              {background?.value || background?.description || '等待画像分析…'}
            </p>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" />
                累计 {formatDuration(profile.history.totalStudyMinutes)}
              </span>
              <span className="flex items-center gap-1">
                <TrendingUp className="w-3.5 h-3.5" />
                {profile.history.quizAccuracy == null ? '暂无正确率' : `正确率 ${profile.history.quizAccuracy}%`}
              </span>
              <span className="flex items-center gap-1">
                <Zap className="w-3.5 h-3.5" />
                {profile.history.streak > 0 ? `连续 ${profile.history.streak} 天` : '暂无连续记录'}
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

      {missingDimensions.length > 0 && (
        <div className="mb-6 p-4 bg-amber-50/70 border border-amber-100 rounded-2xl">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-xl bg-amber-100 flex items-center justify-center flex-shrink-0">
              <AlertCircle className="w-4 h-4 text-amber-600" />
            </div>
            <div className="flex-1">
              <h4 className="text-sm font-semibold text-amber-800 mb-1">补充以下信息，画像会更完整</h4>
              <p className="text-xs text-amber-600 mb-2">还缺少 {missingDimensions.length} 个维度，可回到对话页继续补充。</p>
              <div className="flex flex-wrap gap-1.5">
                {missingDimensions.map((key) => (
                  <span key={key} className="px-2 py-1 bg-white border border-amber-200 rounded-lg text-[10px] text-amber-700 font-medium">
                    {DIMENSION_LABELS[key]}
                  </span>
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

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 mb-6">
        <div className="lg:col-span-3 bg-white border border-gray-100 rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Brain className="w-4 h-4 text-brand-500" />
            能力雷达图
          </h3>
          <DimensionRadar dimensions={profile.dimensions} />
        </div>

        <div className="lg:col-span-2 bg-white border border-gray-100 rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">各维度得分</h3>
          <div className="space-y-4">
            {profile.dimensions.map((dim, i) => (
              <DimensionBar key={dim.key} dim={dim} index={i} />
            ))}
          </div>
        </div>
      </div>

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

      {profile.weaknesses.length > 0 && (
        <div className="mb-6 bg-white border border-gray-100 rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Target className="w-4 h-4 text-red-400" />
            知识短板
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

      <div className="mb-6 bg-white border border-gray-100 rounded-2xl p-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-brand-500" />
          学习偏好
        </h3>
        <div className="flex flex-wrap gap-3">
          <span className="px-3 py-1.5 bg-brand-50 text-brand-600 rounded-xl text-xs font-medium border border-brand-100">
            偏好格式：{(profile.preferences.preferredFormats || ['text']).join(' / ')}
          </span>
          <span className="px-3 py-1.5 bg-green-50 text-green-600 rounded-xl text-xs font-medium border border-green-100">
            学习节奏：{formatDuration(profile.preferences.paceMinutes)} / 次
          </span>
          <span className="px-3 py-1.5 bg-amber-50 text-amber-600 rounded-xl text-xs font-medium border border-amber-100">
            难度等级：{profile.preferences.difficulty === 'beginner' ? '入门' : profile.preferences.difficulty === 'intermediate' ? '进阶' : '高级'}
          </span>
          <span className="px-3 py-1.5 bg-purple-50 text-purple-600 rounded-xl text-xs font-medium border border-purple-100">
            讲解风格：{profile.preferences.explainStyle === 'diagram' ? '图解优先' : profile.preferences.explainStyle === 'code' ? '代码优先' : profile.preferences.explainStyle === 'case' ? '案例优先' : '理论优先'}
          </span>
        </div>
      </div>

      <p className="text-center text-xs text-gray-400 mt-8">
        画像更新时间：{timeAgo(profile.updatedAt)} · 数据来源包含用户对话、系统推断和画像生成结果
      </p>
    </div>
  );
}
