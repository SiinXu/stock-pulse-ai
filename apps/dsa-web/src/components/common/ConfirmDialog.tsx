import type React from 'react';
import { useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { OVERLAY_Z } from './overlayZ';
import { useDialogA11y } from './useDialogA11y';

interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  confirmDisabled?: boolean;
  cancelDisabled?: boolean;
  isDanger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Generic confirmation dialog component.
 * Style is consistent with ChatPage.
 */
export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  isOpen,
  title,
  message,
  confirmText,
  cancelText,
  confirmDisabled = false,
  cancelDisabled = false,
  isDanger = false,
  onConfirm,
  onCancel,
}) => {
  const { t } = useUiLanguage();
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const messageId = useId();

  useDialogA11y({
    isOpen,
    containerRef: dialogRef,
    onEscape: onCancel,
    closeOnEscape: !cancelDisabled,
  });

  if (!isOpen) return null;

  const dialog = (
    <div
      data-overlay-root="confirm"
      // Confirmations sit above drawers/modals so a confirm opened from inside a
      // drawer is never hidden (see OVERLAY_Z).
      style={{ zIndex: OVERLAY_Z.confirm }}
      className="fixed inset-0 flex items-center justify-center bg-black/60 backdrop-blur-sm transition-all"
      onClick={() => {
        if (!cancelDisabled) {
          onCancel();
        }
      }}
      role="presentation"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={messageId}
        tabIndex={-1}
        className="mx-4 w-full max-w-sm rounded-xl border border-border/70 bg-elevated p-6 shadow-2xl animate-in fade-in zoom-in duration-200 focus:outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id={titleId} className="mb-2 text-lg font-medium text-foreground">{title}</h3>
        <p id={messageId} className="text-sm text-secondary-text mb-6 leading-relaxed">
          {message}
        </p>
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={cancelDisabled}
            className="min-h-11 rounded-full border border-border px-4 py-2 text-sm font-medium text-secondary-text transition-colors hover:bg-hover hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
          >
            {cancelText ?? t('common.cancel')}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={confirmDisabled}
            className={`min-h-11 rounded-full px-4 py-2 text-sm font-medium transition-all hover:brightness-110 ${
              isDanger
                ? 'bg-primary text-primary-foreground'
                : 'bg-foreground text-background'
            } disabled:cursor-not-allowed disabled:opacity-60`}
          >
            {confirmText ?? t('common.confirm')}
          </button>
        </div>
      </div>
    </div>
  );

  return createPortal(dialog, document.body);
};
