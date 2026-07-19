import type React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { cn } from '../../utils/cn';
import { getOverlayStyle, type OverlayLayer } from './overlayZ';

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
  onContentKeyDown?: React.KeyboardEventHandler<HTMLDivElement>;
  layer?: OverlayLayer;
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
  onContentKeyDown,
  layer = 'dropdown',
}: PopoverProps) => {
  const rootRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const [shouldRestoreFocus, setShouldRestoreFocus] = useState(false);
  const open = controlledOpen ?? internalOpen;

  const setOpen = useCallback((nextOpen: boolean) => {
    if (controlledOpen === undefined) {
      setInternalOpen(nextOpen);
    }
    onOpenChange?.(nextOpen);
  }, [controlledOpen, onOpenChange]);

  const close = useCallback(() => {
    setShouldRestoreFocus(true);
    setOpen(false);
  }, [setOpen]);

  const dismiss = useCallback(() => setOpen(false), [setOpen]);

  const toggle = useCallback(() => {
    if (open) {
      close();
      return;
    }
    setShouldRestoreFocus(false);
    setOpen(true);
  }, [close, open, setOpen]);

  useEffect(() => {
    if (open) {
      restoreFocusRef.current = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
      return;
    }
    if (!shouldRestoreFocus) return;
    const frame = requestAnimationFrame(() => {
      const target = restoreFocusRef.current
        ?? rootRef.current?.querySelector<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
      target?.focus();
      setShouldRestoreFocus(false);
    });
    return () => cancelAnimationFrame(frame);
  }, [open, shouldRestoreFocus]);

  useEffect(() => {
    if (!open || contentRole !== 'menu') return;
    const frame = requestAnimationFrame(() => {
      const content = contentRef.current;
      if (!content || content.contains(document.activeElement)) return;
      const activeItem = content.querySelector<HTMLElement>('[role="menuitemradio"][aria-checked="true"], [role="menuitemcheckbox"][aria-checked="true"]');
      const firstItem = content.querySelector<HTMLElement>('[role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"]');
      const target = activeItem ?? firstItem;
      content.querySelectorAll<HTMLElement>('[role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"]').forEach((item) => {
        item.tabIndex = item === target ? 0 : -1;
      });
      target?.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, [contentRole, open]);

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) {
        dismiss();
        return;
      }
      if (rootRef.current?.contains(target) || target.closest('[role="listbox"]')) return;
      dismiss();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (closeOnEscape && event.key === 'Escape') {
        event.preventDefault();
        close();
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [close, closeOnEscape, dismiss, open]);

  const handleContentKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    onContentKeyDown?.(event);
    if (event.defaultPrevented || contentRole !== 'menu') return;
    const items = Array.from(
      contentRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"]') ?? [],
    ).filter((item) => !item.hasAttribute('disabled') && item.getAttribute('aria-disabled') !== 'true');
    if (items.length === 0) return;
    const currentIndex = Math.max(items.indexOf(document.activeElement as HTMLElement), 0);
    let nextIndex: number | null = null;
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
      nextIndex = (currentIndex + 1) % items.length;
    } else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
      nextIndex = (currentIndex - 1 + items.length) % items.length;
    } else if (event.key === 'Home') {
      nextIndex = 0;
    } else if (event.key === 'End') {
      nextIndex = items.length - 1;
    }
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
      {open ? (
        <div
          ref={contentRef}
          id={contentId}
          role={contentRole}
          aria-label={ariaLabel}
          aria-labelledby={ariaLabelledBy}
          style={getOverlayStyle(layer)}
          onKeyDown={handleContentKeyDown}
          className={cn(
            'absolute overflow-hidden rounded-xl border border-border bg-elevated shadow-lg',
            contentClassName,
          )}
        >
          {typeof children === 'function' ? children({ close }) : children}
        </div>
      ) : null}
    </div>
  );
};
