// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { IconButton } from './IconButton';
import { getOverlayStyle } from './overlayZ';
import { useDialogA11y } from './useDialogA11y';

export type ModalSize = 'compact' | 'default' | 'wide' | 'fullscreen';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: ModalSize;
  closeDisabled?: boolean;
  closeLabel?: string;
}

const MODAL_SIZE_STYLES: Record<ModalSize, string> = {
  compact: 'max-w-sm',
  default: 'max-w-lg',
  wide: 'max-w-xl',
  fullscreen: 'max-w-[96vw] max-h-[92dvh]',
};

/** Centered form dialog with fixed chrome and a single scrollable body. */
export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'default',
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

  if (!isOpen) return null;

  return createPortal(
    <div
      data-overlay-root="modal"
      className="fixed inset-0 flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm max-sm:items-end max-sm:p-0"
      style={getOverlayStyle('dialog')}
      onClick={handleClose}
      role="presentation"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        data-overlay-dialog="true"
        data-modal-size={size}
        className={cn(
          'flex max-h-[85dvh] min-h-0 w-full flex-col overflow-hidden rounded-xl border border-border bg-elevated shadow-2xl focus:outline-none',
          'max-sm:h-dvh max-sm:max-h-dvh max-sm:rounded-none max-sm:border-x-0 max-sm:border-b-0',
          MODAL_SIZE_STYLES[size],
        )}
        onClick={(event) => event.stopPropagation()}
      >
        <header
          data-overlay-slot="header"
          className="flex shrink-0 items-start justify-between gap-4 border-b border-border px-5 py-4"
        >
          <div className="min-w-0">
            <h2 id={titleId} className="text-base font-semibold text-foreground">{title}</h2>
            {description ? (
              <p id={descriptionId} className="mt-1 text-sm text-secondary-text">{description}</p>
            ) : null}
          </div>
          <IconButton
            variant="ghost"
            size="default"
            onClick={handleClose}
            disabled={closeDisabled}
            aria-label={closeLabel ?? t('common.close')}
            tooltip={false}
          >
            <X aria-hidden="true" />
          </IconButton>
        </header>
        <div data-overlay-slot="body" className="min-h-0 flex-1 overflow-y-auto p-5">
          {children}
        </div>
        {footer ? (
          <footer
            data-overlay-slot="footer"
            className="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-border bg-elevated px-5 py-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))]"
          >
            {footer}
          </footer>
        ) : null}
      </div>
    </div>,
    document.body,
  );
};
