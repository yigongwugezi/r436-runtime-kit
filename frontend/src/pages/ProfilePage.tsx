import { useProfile } from '../hooks/useProfile';
import { DIMENSION_LABELS, type ProfileDimension } from '../types/profile';
import { DIMENSION_COLORS } from '../utils/constants';
import { formatDuration, timeAgo } from '../utils/format';
import {
  User, Clock, Target, TrendingUp, Zap, BookOpen, Shield, Brain, AlertTriangle,
} from 'lucide-react';
import Loading from '../components/common/Loading';
import EmptyState from '../components/common/EmptyState';

/* ===================================================================
 * 雷达图 (CSS-based, 简洁实现)
 * =================================================================== */

function DimensionRadar({ dimensions }: { dimensions: ProfileDimension[] }) {
  const size = 280;
  const center = size / 2;
  const radius = 110;
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

  // 辅助网格环
  const rings = Array.from({ length: levels }, (_, i) => ((i + 1) / levels) * radius);

  // 数据多边形
  const dataPoints = dimensions.map((d, i) => getPoint(i, d.value));
  const polygonPath = dataPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ') + ' Z';

  return (
    <div className="flex justify-center">
      <svg width={size} height={size} className="overflow-visible">
        {/* 网格环 */}
        {rings.map((r, ri) => (
          <circle
            key={ri}
            cx={center}
            cy={center}
            r={r}
            fill="none"
            stroke="#e2e8f0"
            strokeWidth={ri === levels - 1 ? 1.5 : 0.5}
            strokeDasharray={ri === 0 ? 'none' : '4 2'}
          />
        ))}
        {/* 轴线 */}
        {dimensions.map((_, i) => {
          const end = getPoint(i, 100);
          return (
            <line key={i} x1={center} y1={center} x2={end.x} y2={end.y} stroke="#e2e8f0" strokeWidth={0.5} />
          );
        })}
        {/* 数据多边形 */}
        <path d={polygonPath} fill="rgba(99, 102, 241, 0.15)" stroke="#6366f1" strokeWidth={2} />
        {/* 数据点 */}
        {dataPoints.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={4} fill="#6366f1" stroke="white" strokeWidth={2} />
        ))}
        {/* 标签 */}
        {dimensions.map((d, i) => {
          const labelPoint = getPoint(i, 130);
          return (
            <text
              key={i}
              x={labelPoint.x}
              y={labelPoint.y}
              textAnchor="middle"
              dominantBaseline="middle"
              className="text-[10px] font-medium"
              fill="#64748b"
            >
              {d.label}
            </text>
          );
        })}
      </svg>
    </div>
  );
}

/* ===================================================================
 * 维度卡片
 * =================================================================== */

function DimensionBar({ dim, index }: { dim: ProfileDimension; index: number }) {
  const color = DIMENSION_COLORS[index % DIMENSION_COLORS.length];
  return (
    <div className="flex items-center gap-3">
      <div className="w-20 text-xs text-gray-500 text-right flex-shrink-0">{dim.label}</div>
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${dim.value}%`, backgroundColor: color }}
        />
      </div>
      <div className="w-12 text-xs font-semibold text-gray-700">{dim.value}%</div>
    </div>
  );
}

/* ===================================================================
 * 主页面
 * =================================================================== */

export default function ProfilePage() {
  const { profile, loading, error } = useProfile();

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
        description="开始对话后，系统会自动分析并构建你的专属学习画像"
      />
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 md:py-8">
      {/* 顶部信息卡 */}
      <div className="bg-white border border-gray-100 rounded-2xl p-6 md:p-8 mb-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center gap-6">
          {/* 头像 */}
          <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white text-2xl font-bold shadow-lg flex-shrink-0">
            {profile.nickname?.[0] || '学'}
          </div>
          <div className="flex-1">
            <h1 className="text-2xl font-extrabold text-gray-900 mb-1">{profile.nickname || '学习者'}</h1>
            <p className="text-sm text-gray-500 mb-3">
              {profile.dimensions.find((d) => d.key === 'major_background')?.description || '等待画像分析'}
            </p>
            <div className="flex flex-wrap gap-4 text-xs text-gray-500">
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" />
                累计学习 {formatDuration(profile.history.totalStudyMinutes)}
              </span>
              <span className="flex items-center gap-1">
                <TrendingUp className="w-3.5 h-3.5" />
                正确率 {profile.history.quizAccuracy}%
              </span>
              <span className="flex items-center gap-1">
                <Zap className="w-3.5 h-3.5" />
                连续 {profile.history.streak} 天
              </span>
            </div>
          </div>
          <div className="text-center px-4 py-3 bg-brand-50 rounded-2xl flex-shrink-0">
            <div className="text-lg font-bold text-brand-600">{profile.dimensions.length}</div>
            <div className="text-[10px] text-brand-500">维度画像</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* 雷达图 */}
        <div className="lg:col-span-3 bg-white border border-gray-100 rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Brain className="w-4 h-4 text-brand-500" />
            能力雷达图
          </h3>
          <DimensionRadar dimensions={profile.dimensions} />
        </div>

        {/* 维度详情 */}
        <div className="lg:col-span-2 bg-white border border-gray-100 rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">各维度掌握度</h3>
          <div className="space-y-4">
            {profile.dimensions.map((dim, i) => (
              <DimensionBar key={dim.key} dim={dim} index={i} />
            ))}
          </div>
        </div>
      </div>

      {/* 知识短板 */}
      {profile.weaknesses.length > 0 && (
        <div className="mt-6 bg-white border border-gray-100 rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Target className="w-4 h-4 text-red-400" />
            知识短板
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {profile.weaknesses.map((gap) => (
              <div key={gap.topic} className="flex items-center justify-between p-3 bg-red-50/50 border border-red-100 rounded-xl">
                <div>
                  <p className="text-sm font-medium text-gray-800">{gap.topic}</p>
                  <p className="text-[10px] text-gray-400">优先修复 P{gap.priority}</p>
                </div>
                <div className="text-right">
                  <div className="text-xs font-bold text-red-500">{gap.mastery}%</div>
                  <div className="h-1 w-16 bg-red-100 rounded-full mt-0.5 overflow-hidden">
                    <div className="h-full bg-red-400 rounded-full" style={{ width: `${gap.mastery}%` }} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 学习偏好 */}
      <div className="mt-6 bg-white border border-gray-100 rounded-2xl p-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-brand-500" />
          学习偏好
        </h3>
        <div className="flex flex-wrap gap-3">
          <span className="px-3 py-1.5 bg-brand-50 text-brand-600 rounded-xl text-xs font-medium">
            偏好格式：{profile.preferences.preferredFormats.join('、')}
          </span>
          <span className="px-3 py-1.5 bg-green-50 text-green-600 rounded-xl text-xs font-medium">
            单次时长：{formatDuration(profile.preferences.paceMinutes)}
          </span>
          <span className="px-3 py-1.5 bg-amber-50 text-amber-600 rounded-xl text-xs font-medium">
            难度：{profile.preferences.difficulty}
          </span>
          <span className="px-3 py-1.5 bg-purple-50 text-purple-600 rounded-xl text-xs font-medium">
            讲解风格：{profile.preferences.explainStyle}
          </span>
        </div>
      </div>

      <p className="text-center text-xs text-gray-400 mt-8">
        画像更新时间：{timeAgo(profile.updatedAt)}
      </p>
    </div>
  );
}
