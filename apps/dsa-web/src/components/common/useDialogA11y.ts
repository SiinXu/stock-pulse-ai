import { useEffect, type RefObject } from 'react';

// Shared accessibility behaviour for modal-like surfaces (Modal / Drawer /
// ConfirmDialog): move focus in on open, trap Tab within the surface, close on
// Escape, restore focus to the trigger on close, and lock body scroll across
// stacked dialogs. Combined with role="dialog" + aria-modal on the container,
// this makes the background effectively inert for keyboard and screen readers.

let openDialogCount = 0;

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

interface DialogA11yOptions {
  isOpen: boolean;
  containerRef: RefObject<HTMLElement | null>;
  onEscape?: () => void;
  closeOnEscape?: boolean;
}

function getFocusable(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (el) => el.offsetParent !== null || el === document.activeElement,
  );
}

export function useDialogA11y({
  isOpen,
  containerRef,
  onEscape,
  closeOnEscape = true,
}: DialogA11yOptions): void {
  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    const previouslyFocused = document.activeElement as HTMLElement | null;

    const container = containerRef.current;
    if (container && !container.contains(document.activeElement)) {
      const first = getFocusable(container)[0];
      (first ?? container).focus();
    }

    openDialogCount += 1;
    if (openDialogCount === 1) {
      document.body.style.overflow = 'hidden';
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      const container = containerRef.current;
      if (event.key === 'Escape') {
        if (closeOnEscape && onEscape) {
          event.stopPropagation();
          onEscape();
        }
        return;
      }
      if (event.key !== 'Tab' || !container) {
        return;
      }
      const focusables = getFocusable(container);
      if (focusables.length === 0) {
        event.preventDefault();
        container.focus();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;
      if (event.shiftKey) {
        if (active === first || !container.contains(active)) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last || !container.contains(active)) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown, true);

    return () => {
      document.removeEventListener('keydown', handleKeyDown, true);
      openDialogCount -= 1;
      if (openDialogCount === 0) {
        document.body.style.overflow = '';
      }
      // Only restore focus to a trigger that is still in the document.
      if (previouslyFocused && previouslyFocused.isConnected) {
        previouslyFocused.focus();
      }
    };
  }, [isOpen, containerRef, onEscape, closeOnEscape]);
}
