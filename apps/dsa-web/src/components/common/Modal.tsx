// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { IconButton } from './IconButton';
import { OVERLAY_Z } from './overlayZ';
import { useDialogA11y } from './useDialogA11y';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  footerClassName?: string;
  closeDisabled?: boolean;
  closeLabel?: string;
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
  footer,
  className = '',
  bodyClassName,
  footerClassName,
  closeDisabled = false,
  closeLabel,
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
      className="fixed inset-0 flex items-center justify-center bg-[var(--page-drawer-overlay-bg)] p-4 backdrop-blur-sm max-sm:items-end max-sm:p-0"
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
          'flex max-h-[85dvh] w-full max-w-lg flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl focus:outline-none max-sm:max-h-[92dvh] max-sm:rounded-b-none',
          className,
        )}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="text-base font-semibold text-foreground">{title}</h2>
            {description ? (
              <p id={descriptionId} className="mt-1 text-sm text-secondary-text">{description}</p>
            ) : null}
          </div>
          <IconButton
            onClick={handleClose}
            disabled={closeDisabled}
            aria-label={closeLabel ?? t('common.close')}
            tooltip={false}
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </IconButton>
        </div>
        <div data-modal-body="true" className={cn('min-h-0 flex-1 overflow-y-auto p-5', bodyClassName)}>{children}</div>
        {footer ? (
          <footer
            data-modal-footer="true"
            className={cn(
              'flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-border bg-card px-5 py-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))]',
              footerClassName,
            )}
          >
            {footer}
          </footer>
        ) : null}
      </div>
    </div>,
    document.body,
  );
};
