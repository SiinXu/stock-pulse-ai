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

export type DetailDrawerSize = 'compact' | 'default' | 'wide';

interface DrawerBaseProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  description?: string;
  footer?: React.ReactNode;
  closeDisabled?: boolean;
}

export type DrawerProps = DrawerBaseProps & (
  | { variant: 'navigation'; size?: never }
  | { variant: 'detail'; size?: DetailDrawerSize }
);

const DETAIL_DRAWER_SIZE_STYLES: Record<DetailDrawerSize, string> = {
  compact: 'max-w-[30rem]',
  default: 'max-w-xl',
  wide: 'max-w-[40rem]',
};

/** Semantic navigation/detail drawer with fixed header, body, and optional footer. */
export const Drawer: React.FC<DrawerProps> = ({
  isOpen,
  onClose,
  title,
  children,
  description,
  footer,
  variant,
  size = 'default',
  closeDisabled = false,
}) => {
  const { t } = useUiLanguage();
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const isNavigation = variant === 'navigation';
  const side = isNavigation ? 'left' : 'right';
  const widthClass = isNavigation ? 'max-w-xs' : DETAIL_DRAWER_SIZE_STYLES[size];

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
      data-overlay-root="drawer"
      className="fixed inset-0 overflow-hidden"
      style={getOverlayStyle('dialog')}
      role="presentation"
    >
      <div
        className="absolute inset-0 bg-background/80 backdrop-blur-sm transition-opacity duration-200 motion-reduce:transition-none"
        onClick={handleClose}
      />
      <div
        className={cn(
          'absolute inset-y-0 flex w-full',
          isNavigation ? 'left-0 justify-start' : 'right-0 justify-end',
          widthClass,
        )}
      >
        <div
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          aria-describedby={description ? descriptionId : undefined}
          tabIndex={-1}
          data-overlay-dialog="true"
          data-drawer-variant={variant}
          data-drawer-side={side}
          data-drawer-size={isNavigation ? undefined : size}
          className={cn(
            'relative flex min-h-0 w-full flex-col bg-elevated shadow-2xl focus:outline-none',
            isNavigation
              ? 'animate-slide-in-left border-r border-border'
              : 'animate-slide-in-right border-l border-border',
          )}
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
              aria-label={t('common.closeDrawer')}
              tooltip={false}
            >
              <X aria-hidden="true" />
            </IconButton>
          </header>
          <div
            data-overlay-slot="body"
            className={cn(
              'min-h-0 flex-1 overflow-y-auto',
              isNavigation ? 'p-0' : 'p-5 sm:p-6',
            )}
          >
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
      </div>
    </div>,
    document.body,
  );
};
