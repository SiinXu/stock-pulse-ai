import type React from 'react';
import { useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { OVERLAY_Z } from './overlayZ';
import { useDialogA11y } from './useDialogA11y';

interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  ariaLabel?: string;
  children: React.ReactNode;
  width?: string;
  zIndex?: number;
  side?: 'left' | 'right';
  backdropClassName?: string;
  overlayClassName?: string;
  className?: string;
  contentClassName?: string;
  headerActions?: React.ReactNode;
  showEyebrow?: boolean;
  dismissDisabled?: boolean;
  dismissDisabledReason?: string;
  onDismissBlocked?: () => void;
}

/**
 * Side drawer component with terminal-inspired styling.
 */
export const Drawer: React.FC<DrawerProps> = ({
  isOpen,
  onClose,
  title,
  description,
  ariaLabel,
  children,
  width = 'max-w-2xl',
  zIndex = OVERLAY_Z.drawer,
  side = 'right',
  backdropClassName,
  overlayClassName,
  className,
  contentClassName,
  headerActions,
  showEyebrow = true,
  dismissDisabled = false,
  dismissDisabledReason,
  onDismissBlocked,
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

  if (!isOpen) return null;

  const sidePositionClass = side === 'left' ? 'left-0 justify-start' : 'right-0 justify-end';
  const borderClass = side === 'left' ? 'border-r' : 'border-l';

  return createPortal(
    <div
      ref={overlayRef}
      data-overlay-root="drawer"
      className={cn('fixed inset-0 overflow-hidden', overlayClassName)}
      style={{ zIndex }}
      role="presentation"
    >
      {/* Backdrop */}
      <div
        className={cn(
          'absolute inset-0 bg-background/80 backdrop-blur-sm transition-opacity duration-300',
          backdropClassName,
        )}
        onClick={requestClose}
      />

      <div className={cn('absolute inset-y-0 flex w-full', sidePositionClass, width)}>
        <div
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={title ? titleId : undefined}
          aria-label={title ? undefined : (ariaLabel ?? t('common.detailView'))}
          aria-describedby={describedBy}
          tabIndex={-1}
          className={cn(
            'relative flex w-full flex-col bg-card focus:outline-none',
            borderClass,
            side === 'right' ? 'border-border/80' : 'border-border/70 shadow-2xl',
            side === 'left' ? 'animate-slide-in-left' : 'animate-slide-in-right',
            className,
          )}
        >
          <div className="flex min-h-16 items-center justify-between gap-3 border-b border-border/60 px-4 py-2 sm:px-6">
            {title ? (
              <div className="min-w-0">
                {showEyebrow ? <span className="label-uppercase">{t('common.detailView')}</span> : null}
                <h2 id={titleId} className="mt-1 text-lg font-semibold text-foreground">{title}</h2>
                {description ? <p id={descriptionId} className="mt-1 text-sm text-secondary-text">{description}</p> : null}
                {dismissDisabled ? (
                  <p id={dismissStatusId} role="status" className="mt-1 text-xs text-warning">
                    {resolvedDismissReason}
                  </p>
                ) : null}
              </div>
            ) : <div />}
            <div className="flex shrink-0 items-center gap-2">
              {headerActions}
              <button
              type="button"
              onClick={requestClose}
              aria-disabled={dismissDisabled || undefined}
              aria-describedby={dismissDisabled ? dismissStatusId : undefined}
              className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-border/70 bg-card/80 text-secondary-text transition-colors hover:bg-hover hover:text-foreground aria-disabled:cursor-not-allowed aria-disabled:opacity-60"
              aria-label={t('common.closeDrawer')}
            >
              <X className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>
          </div>
          <div className={cn('flex-1 overflow-y-auto p-4 sm:p-6', contentClassName)}>
            {children}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
};
