import type React from 'react';
import { useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { Button } from './Button';
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
  error?: string | null;
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
  error = null,
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
      className="fixed inset-0 flex items-center justify-center bg-[var(--page-drawer-overlay-bg)] backdrop-blur-sm transition-all"
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
        {error ? (
          <p className="mb-4 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-left text-xs text-danger" role="alert">
            {error}
          </p>
        ) : null}
        <div className="flex justify-end gap-3">
          <Button
            type="button"
            variant="secondary"
            size="xl"
            onClick={onCancel}
            disabled={cancelDisabled}
            className="min-h-11"
          >
            {cancelText ?? t('common.cancel')}
          </Button>
          <Button
            type="button"
            variant={isDanger ? 'danger' : 'primary'}
            size="xl"
            onClick={onConfirm}
            disabled={confirmDisabled}
            className="min-h-11"
          >
            {confirmText ?? t('common.confirm')}
          </Button>
        </div>
      </div>
    </div>
  );

  return createPortal(dialog, document.body);
};
