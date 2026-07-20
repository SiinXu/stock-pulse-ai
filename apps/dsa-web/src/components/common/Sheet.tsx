// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { Button } from './Button';
import { IconButton } from './IconButton';
import { getOverlayStyle } from './overlayZ';
import { useDialogA11y } from './useDialogA11y';

export interface SheetProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  footer: React.ReactNode;
  closeDisabled?: boolean;
}

/** Bottom sheet with fixed header/footer and one compact scroll region. */
export const Sheet: React.FC<SheetProps> = ({
  isOpen,
  onClose,
  title,
  description,
  children,
  footer,
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

  if (!isOpen) return null;

  return createPortal(
    <div
      data-overlay-root="sheet"
      className="fixed inset-0 flex items-end justify-center bg-background/80 pt-2 backdrop-blur-sm"
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
        data-sheet-variant="filter"
        className="flex max-h-[calc(100dvh-0.5rem)] min-h-0 w-full max-w-2xl flex-col overflow-hidden rounded-t-xl border border-b-0 border-border bg-elevated shadow-2xl focus:outline-none sm:max-h-[85dvh]"
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
            aria-label={t('common.close')}
            tooltip={false}
          >
            <X aria-hidden="true" />
          </IconButton>
        </header>
        <div data-overlay-slot="body" className="min-h-0 flex-1 overflow-y-auto p-5">
          {children}
        </div>
        <footer
          data-overlay-slot="footer"
          className="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-border bg-elevated px-5 py-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))]"
        >
          {footer}
        </footer>
      </div>
    </div>,
    document.body,
  );
};

export interface FilterSheetProps extends Omit<SheetProps, 'footer'> {
  resetLabel: string;
  applyLabel: string;
  onReset: () => void;
  onApply: () => void;
  resetDisabled?: boolean;
  applyDisabled?: boolean;
  isApplying?: boolean;
  loadingLabel?: string;
}

export const FilterSheet: React.FC<FilterSheetProps> = ({
  children,
  resetLabel,
  applyLabel,
  onReset,
  onApply,
  resetDisabled = false,
  applyDisabled = false,
  isApplying = false,
  loadingLabel,
  closeDisabled,
  ...sheetProps
}) => {
  const formId = useId();
  const applyBlocked = applyDisabled || isApplying;
  return (
    <Sheet
      {...sheetProps}
      closeDisabled={closeDisabled || isApplying}
      footer={(
        <>
          <Button
            type="button"
            variant="ghost"
            size="comfortable"
            disabled={resetDisabled || isApplying}
            onClick={onReset}
          >
            {resetLabel}
          </Button>
          <Button
            type="submit"
            form={formId}
            variant="primary"
            size="comfortable"
            disabled={applyBlocked}
            isLoading={isApplying}
            loadingText={loadingLabel}
          >
            {applyLabel}
          </Button>
        </>
      )}
    >
      <form
        id={formId}
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          event.stopPropagation();
          if (applyBlocked) return;
          onApply();
        }}
      >
        {children}
      </form>
    </Sheet>
  );
};
