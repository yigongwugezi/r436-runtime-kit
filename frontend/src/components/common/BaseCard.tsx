import type { ReactNode } from 'react';

interface BaseCardProps {
  children: ReactNode;
  className?: string;
  padding?: 'sm' | 'md' | 'lg';
  hover?: boolean;
  onClick?: () => void;
}

const PADDING = { sm: 'p-4', md: 'p-5', lg: 'p-6' };

/** 统一卡片容器 — 白底、圆角、阴影 */
export default function BaseCard({
  children,
  className = '',
  padding = 'md',
  hover = false,
  onClick,
}: BaseCardProps) {
  return (
    <div
      onClick={onClick}
      className={`bg-white border border-gray-100 rounded-2xl shadow-sm ${
        hover ? 'hover:shadow-md transition-shadow' : ''
      } ${PADDING[padding]} ${onClick ? 'cursor-pointer' : ''} ${className}`}
    >
      {children}
    </div>
  );
}
