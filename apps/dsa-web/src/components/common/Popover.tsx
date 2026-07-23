// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '../../utils/cn';
import { isFixedPopupOwnedBy, useFixedPopup } from './useFixedPopup';

interface PopoverRenderProps {
  open: boolean;
  close: () => void;
  toggle: () => void;
}

interface PopoverProps {
  trigger: (props: PopoverRenderProps) => React.ReactNode;
  children: React.ReactNode | ((props: { close: () => void }) => React.ReactNode);
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  rootClassName?: string;
  contentClassName?: string;
  contentRole?: React.AriaRole;
  contentId?: string;
  ariaLabel?: string;
  ariaLabelledBy?: string;
  closeOnEscape?: boolean;
  placement?: 'auto' | 'top' | 'bottom' | 'right';
  align?: 'start' | 'end';
  autoFocusContent?: boolean;
  onContentKeyDown?: React.KeyboardEventHandler<HTMLDivElement>;
  onContentMouseEnter?: React.MouseEventHandler<HTMLDivElement>;
  onContentMouseLeave?: React.MouseEventHandler<HTMLDivElement>;
}

export const Popover = ({
  trigger,
  children,
  open: controlledOpen,
  defaultOpen = false,
  onOpenChange,
  rootClassName,
  contentClassName,
  contentRole,
  contentId,
  ariaLabel,
  ariaLabelledBy,
  closeOnEscape = true,
  placement = 'auto',
  align = 'start',
  autoFocusContent = true,
  onContentKeyDown,
  onContentMouseEnter,
  onContentMouseLeave,
}: PopoverProps) => {
  const rootRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const [shouldRestoreFocus, setShouldRestoreFocus] = useState(false);
  const open = controlledOpen ?? internalOpen;
  const {
    portalHost,
    popupStyle,
    prepareForOpen,
    resetPosition,
    isTopmostPopup,
  } = useFixedPopup({
    isOpen: open,
    triggerRef: rootRef,
    popupRef: contentRef,
    contentVersion: open,
    constrainWidthToViewport: true,
    placement,
    align,
  });

  const setOpen = useCallback((nextOpen: boolean) => {
    if (controlledOpen === undefined) setInternalOpen(nextOpen);
    onOpenChange?.(nextOpen);
  }, [controlledOpen, onOpenChange]);

  const openPopover = useCallback(() => {
    setShouldRestoreFocus(false);
    prepareForOpen();
    setOpen(true);
  }, [prepareForOpen, setOpen]);

  const close = useCallback(() => {
    setShouldRestoreFocus(true);
    resetPosition();
    setOpen(false);
  }, [resetPosition, setOpen]);

  const dismiss = useCallback(() => {
    resetPosition();
    setOpen(false);
  }, [resetPosition, setOpen]);

  const toggle = useCallback(() => {
    if (open) close();
    else openPopover();
  }, [close, open, openPopover]);

  useEffect(() => {
    if (open && !portalHost) prepareForOpen();
  }, [open, portalHost, prepareForOpen]);

  useEffect(() => {
    if (open) {
      restoreFocusRef.current = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
      return;
    }
    if (!shouldRestoreFocus) return;
    const frame = requestAnimationFrame(() => {
      const trigger = rootRef.current?.querySelector<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      ) ?? null;
      const remembered = restoreFocusRef.current;
      const target = remembered && rootRef.current?.contains(remembered)
        ? remembered
        : trigger ?? remembered;
      target?.focus();
      setShouldRestoreFocus(false);
    });
    return () => cancelAnimationFrame(frame);
  }, [open, shouldRestoreFocus]);

  useEffect(() => {
    if (
      !open
      || !autoFocusContent
      || (contentRole !== 'menu' && contentRole !== 'dialog')
    ) return;
    const frame = requestAnimationFrame(() => {
      const content = contentRef.current;
      if (!content || content.contains(document.activeElement)) return;
      if (contentRole === 'dialog') {
        content.querySelector<HTMLElement>(
          'input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
        )?.focus();
        return;
      }
      const activeItem = content.querySelector<HTMLElement>('[role="menuitemradio"][aria-checked="true"], [role="menuitemcheckbox"][aria-checked="true"]');
      const firstItem = content.querySelector<HTMLElement>('[role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"]');
      const target = activeItem ?? firstItem;
      content.querySelectorAll<HTMLElement>('[role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"]').forEach((item) => {
        item.tabIndex = item === target ? 0 : -1;
      });
      target?.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, [autoFocusContent, contentRole, open, portalHost]);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) {
        dismiss();
        return;
      }
      if (
        rootRef.current?.contains(target)
        || contentRef.current?.contains(target)
        || (rootRef.current && isFixedPopupOwnedBy(rootRef.current, target))
        || (contentRef.current && isFixedPopupOwnedBy(contentRef.current, target))
      ) {
        return;
      }
      dismiss();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      const nestedPopupOpen = contentRef.current?.querySelector(
        '[data-dialog-popup="true"], [aria-haspopup][aria-expanded="true"]',
      );
      if (
        closeOnEscape
        && event.key === 'Escape'
        && !nestedPopupOpen
        && isTopmostPopup()
      ) {
        event.preventDefault();
        event.stopImmediatePropagation();
        close();
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [close, closeOnEscape, dismiss, isTopmostPopup, open]);

  const handleContentKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    onContentKeyDown?.(event);
    if (event.defaultPrevented || contentRole !== 'menu') return;
    const items = Array.from(
      contentRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"]') ?? [],
    ).filter((item) => !item.hasAttribute('disabled') && item.getAttribute('aria-disabled') !== 'true');
    if (items.length === 0) return;
    const currentIndex = Math.max(items.indexOf(document.activeElement as HTMLElement), 0);
    let nextIndex: number | null = null;
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % items.length;
    else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + items.length) % items.length;
    else if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = items.length - 1;
    if (nextIndex !== null) {
      event.preventDefault();
      items.forEach((item, index) => {
        item.tabIndex = index === nextIndex ? 0 : -1;
      });
      items[nextIndex]?.focus();
    }
  };

  return (
    <div ref={rootRef} className={cn('relative', rootClassName)}>
      {trigger({ open, close, toggle })}
      {open && portalHost && popupStyle
        ? createPortal(
            <div
              ref={contentRef}
              id={contentId}
              role={contentRole}
              aria-label={ariaLabel}
              aria-labelledby={ariaLabelledBy}
              data-dialog-popup="true"
              style={popupStyle}
              onKeyDown={handleContentKeyDown}
              onMouseEnter={onContentMouseEnter}
              onMouseLeave={onContentMouseLeave}
              className={cn(
                'fixed overflow-hidden rounded-xl border border-border bg-elevated shadow-lg',
                contentClassName,
              )}
            >
              {typeof children === 'function' ? children({ close }) : children}
            </div>,
            portalHost,
          )
        : null}
    </div>
  );
};
