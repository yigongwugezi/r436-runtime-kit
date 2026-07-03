import { X } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  wide?: boolean;
  xwide?: boolean;
}

export default function Modal({ open, onClose, title, children, wide, xwide }: ModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    if (open) window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 bg-black/45 backdrop-blur-sm animate-fade-in"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className={`bg-white rounded-2xl shadow-elevated w-full max-h-[90vh] overflow-y-auto animate-fade-in ${xwide ? 'max-w-6xl' : wide ? 'max-w-3xl' : 'max-w-lg'}`}>
        {title && (
          <div className="flex items-center justify-between px-6 py-4 border-b border-surface-200">
            <h3 className="font-display text-lg font-semibold text-surface-800">{title}</h3>
            <button onClick={onClose} className="p-2 rounded-xl hover:bg-surface-100 transition-colors"><X className="w-5 h-5 text-surface-400" /></button>
          </div>
        )}
        <div className="p-6">{children}</div>
      </div>
    </div>,
    document.body
  );
}
