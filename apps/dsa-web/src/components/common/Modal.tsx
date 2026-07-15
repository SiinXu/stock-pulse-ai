import type React from 'react';
import { useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { useDialogA11y } from './useDialogA11y';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  className?: string;
}

/**
 * Centered modal dialog with backdrop, focus management, Escape-to-close and
 * body scroll lock (see useDialogA11y).
 */
export const Modal: React.FC<ModalProps> = ({ isOpen, onClose, title, children, className = '' }) => {
  const { t } = useUiLanguage();
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useDialogA11y({ isOpen, containerRef: dialogRef, onEscape: onClose });

  if (!isOpen) {
    return null;
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm max-sm:items-end max-sm:p-0"
      onClick={onClose}
      role="presentation"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        tabIndex={-1}
        className={cn(
          // On phones the dialog docks to the bottom as a full-width sheet
          // (same flow, same component); centered card from `sm` up.
          'flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl focus:outline-none max-sm:max-h-[92vh] max-sm:rounded-b-none',
          className,
        )}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 id={titleId} className="text-base font-semibold tracking-tight text-foreground">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common.closeDrawer')}
            className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-border text-secondary-text transition-colors hover:bg-hover hover:text-foreground"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>,
    document.body,
  );
};
