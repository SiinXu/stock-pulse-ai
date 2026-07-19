import type React from 'react';
import { useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { IconButton } from './IconButton';
import { OVERLAY_Z } from './overlayZ';
import { useDialogA11y } from './useDialogA11y';

interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  description?: string;
  eyebrow?: string;
  width?: string;
  zIndex?: number;
  side?: 'left' | 'right';
  backdropClassName?: string;
  rootClassName?: string;
  panelClassName?: string;
  contentClassName?: string;
  showHeader?: boolean;
  closeDisabled?: boolean;
}

/**
 * Side drawer component with terminal-inspired styling.
 */
export const Drawer: React.FC<DrawerProps> = ({
  isOpen,
  onClose,
  title,
  children,
  description,
  eyebrow,
  width = 'max-w-2xl',
  zIndex = OVERLAY_Z.drawer,
  side = 'right',
  backdropClassName,
  rootClassName,
  panelClassName,
  contentClassName,
  showHeader = true,
  closeDisabled = false,
}) => {
  const { t } = useUiLanguage();
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const handleClose = () => {
    if (!closeDisabled) {
      onClose();
    }
  };

  useDialogA11y({
    isOpen,
    containerRef: dialogRef,
    onEscape: handleClose,
    closeOnEscape: !closeDisabled,
  });

  if (!isOpen) return null;

  const sidePositionClass = side === 'left' ? 'left-0 justify-start' : 'right-0 justify-end';
  const borderClass = side === 'left' ? 'border-r' : 'border-l';

  return createPortal(
    <div
      data-overlay-root="drawer"
      className={cn('fixed inset-0 overflow-hidden', rootClassName)}
      style={{ zIndex }}
      role="presentation"
    >
      {/* Backdrop */}
      <div
        className={cn(
          'absolute inset-0 bg-background/80 backdrop-blur-sm transition-opacity duration-300',
          backdropClassName,
        )}
        onClick={handleClose}
      />

      <div className={cn('absolute inset-y-0 flex w-full', sidePositionClass, width)}>
        <div
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          aria-describedby={description ? descriptionId : undefined}
          tabIndex={-1}
          className={cn(
            'relative flex w-full flex-col bg-card focus:outline-none',
            borderClass,
            side === 'right' ? 'border-border/80' : 'border-border/70 shadow-2xl',
            side === 'left' ? 'animate-slide-in-left' : 'animate-slide-in-right',
            panelClassName,
          )}
        >
          {showHeader ? (
            <div className="flex items-center justify-between border-b border-border/60 px-6 py-4">
              <div>
                {eyebrow ? <span className="label-uppercase">{eyebrow}</span> : null}
                <h2 id={titleId} className={cn('text-lg font-semibold text-foreground', eyebrow && 'mt-1')}>{title}</h2>
                {description ? (
                  <p id={descriptionId} className="mt-1 text-sm text-secondary-text">{description}</p>
                ) : null}
              </div>
              <IconButton
                onClick={handleClose}
                disabled={closeDisabled}
                aria-label={t('common.closeDrawer')}
                tooltip={false}
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </IconButton>
            </div>
          ) : (
            <>
              <h2 id={titleId} className="sr-only">{title}</h2>
              {description ? <p id={descriptionId} className="sr-only">{description}</p> : null}
            </>
          )}
          <div className={cn('flex-1 overflow-y-auto p-6', contentClassName)}>
            {children}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
};
