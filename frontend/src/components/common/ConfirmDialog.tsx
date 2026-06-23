import { AlertTriangle, Check, X } from 'lucide-react';
import Modal from './Modal';

interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'default' | 'danger';
}

/** 统一确认弹窗 — 用于阶段完成、批量操作等需要确认的场景 */
export default function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = '确认',
  cancelLabel = '取消',
  variant = 'default',
}: ConfirmDialogProps) {
  return (
    <Modal open={open} onClose={onClose} title={title}>
      <div className="space-y-4">
        {variant === 'danger' && (
          <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-100 rounded-xl">
            <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0" />
            <p className="text-xs text-red-600">{description || '此操作不可撤销，请确认。'}</p>
          </div>
        )}
        {variant === 'default' && description && (
          <p className="text-sm text-gray-500 leading-relaxed">{description}</p>
        )}

        <div className="flex items-center justify-end gap-2 pt-2">
          <button
            onClick={onClose}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-medium text-gray-500 bg-gray-50 border border-gray-200 hover:bg-gray-100 transition-all"
          >
            <X className="w-3.5 h-3.5" />
            {cancelLabel}
          </button>
          <button
            onClick={() => { onConfirm(); onClose(); }}
            className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white transition-all ${
              variant === 'danger'
                ? 'bg-red-500 hover:bg-red-600'
                : 'bg-gray-900 hover:bg-gray-800'
            }`}
          >
            <Check className="w-3.5 h-3.5" />
            {confirmLabel}
          </button>
        </div>
      </div>
    </Modal>
  );
}
