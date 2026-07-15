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
  ariaLabel?: string;
  children: React.ReactNode;
  className?: string;
  dismissDisabled?: boolean;
  dismissDisabledReason?: string;
  onDismissBlocked?: () => void;
  zIndex?: number;
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
  ariaLabel,
  children,
  className = '',
  dismissDisabled = false,
  dismissDisabledReason,
  onDismissBlocked,
  zIndex = OVERLAY_Z.modal,
}) => {
  const { t } = useUiLanguage();
  const overlayRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const dismissStatusId = useId();
  const resolvedDismissReason = dismissDisabledReason ?? t('common.processing');
  const describedBy = [description ? descriptionId : undefined, dismissDisabled ? dismissStatusId : undefined]
    .filter(Boolean)
    .join(' ') || undefined;

  const { requestClose } = useDialogA11y({
    isOpen,
    containerRef: dialogRef,
    overlayRef,
    onEscape: onClose,
    onCloseBlocked: onDismissBlocked,
    dismissDisabled,
    zIndex,
  });

  if (!isOpen) {
    return null;
  }

  return createPortal(
    <div
      ref={overlayRef}
      data-overlay-root="modal"
      style={{ zIndex }}
      className="fixed inset-0 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm max-sm:items-end max-sm:p-0"
      onClick={requestClose}
      role="presentation"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-label={title ? undefined : (ariaLabel ?? t('common.detailView'))}
        aria-describedby={describedBy}
        tabIndex={-1}
        className={cn(
          // On phones the dialog docks to the bottom as a full-width sheet
          // (same flow, same component); centered card from `sm` up.
          'flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl focus:outline-none max-sm:max-h-[92vh] max-sm:rounded-b-none',
          className,
        )}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex min-h-16 items-center justify-between gap-3 border-b border-border px-4 py-2 sm:px-5">
          <div className="min-w-0">
            {title ? <h2 id={titleId} className="text-base font-semibold text-foreground">{title}</h2> : null}
            {description ? <p id={descriptionId} className="mt-1 text-sm text-secondary-text">{description}</p> : null}
            {dismissDisabled ? (
              <p id={dismissStatusId} role="status" className="mt-1 text-xs text-warning">
                {resolvedDismissReason}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={requestClose}
            aria-disabled={dismissDisabled || undefined}
            aria-describedby={dismissDisabled ? dismissStatusId : undefined}
            aria-label={t('common.close')}
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-border text-secondary-text transition-colors hover:bg-hover hover:text-foreground aria-disabled:cursor-not-allowed aria-disabled:opacity-60"
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
