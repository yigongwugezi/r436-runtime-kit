/** Search input for knowledge graph — typing highlights matching nodes. */
import { Search, X } from 'lucide-react';

interface KGSearchProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

export default function KGSearch({ value, onChange, placeholder = '搜索知识点...' }: KGSearchProps) {
  return (
    <div className="relative max-w-xs">
      <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400 pointer-events-none" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full pl-9 pr-8 py-2 rounded-xl border border-surface-200 bg-white text-sm text-surface-700 placeholder:text-surface-400 focus:ring-2 focus:ring-primary-200 focus:border-primary-400 outline-none transition-all"
      />
      {value && (
        <button
          onClick={() => onChange('')}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 p-0.5 rounded hover:bg-surface-100 text-surface-400 transition-colors"
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}
