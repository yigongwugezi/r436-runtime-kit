import { Loader2 } from 'lucide-react';

interface LoadingProps {
  text?: string;
  fullScreen?: boolean;
}

export default function Loading({ text = '加载中...', fullScreen = false }: LoadingProps) {
  const base = 'flex flex-col items-center justify-center gap-3 text-gray-400';
  return (
    <div className={`${base} ${fullScreen ? 'min-h-[60vh]' : 'py-12'}`}>
      <Loader2 className="w-8 h-8 text-brand-500 animate-spin" />
      <span className="text-sm">{text}</span>
    </div>
  );
}
