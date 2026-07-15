import type React from 'react';
import { useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { OVERLAY_Z } from './overlayZ';
import { useDialogA11y } from './useDialogA11y';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
  closeDisabled?: boolean;
}

/**
 * Centered modal dialog with backdrop, focus management, Escape-to-close and
 * body scroll lock (see useDialogA11y).
 */
export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  description,
  children,
  className = '',
  closeDisabled = false,
}) => {
  const { t } = useUiLanguage();
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  const handleClose = () => {
    if (!closeDisabled) onClose();
  };

  useDialogA11y({
    isOpen,
    containerRef: dialogRef,
    onEscape: handleClose,
    closeOnEscape: !closeDisabled,
  });

  if (!isOpen) {
    return null;
  }

  return createPortal(
    <div
      data-overlay-root="modal"
      className="fixed inset-0 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm max-sm:items-end max-sm:p-0"
      style={{ zIndex: OVERLAY_Z.modal }}
      onClick={handleClose}
      role="presentation"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-label={title ? undefined : t('common.detailView')}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className={cn(
          // On phones the dialog docks to the bottom as a full-width sheet
          // (same flow, same component); centered card from `sm` up.
          'flex max-h-[85dvh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl focus:outline-none max-sm:max-h-[92dvh] max-sm:rounded-b-none',
          className,
        )}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h2 id={titleId} className="text-base font-semibold tracking-tight text-foreground">{title}</h2>
            {description ? (
              <p id={descriptionId} className="mt-1 text-sm text-secondary-text">{description}</p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={handleClose}
            disabled={closeDisabled}
            aria-label={t('common.closeDrawer')}
            className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-border text-secondary-text transition-colors hover:bg-hover hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-secondary-text"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>,
    document.body,
  );
};
