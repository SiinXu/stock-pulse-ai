import { useEffect, type RefObject } from 'react';

// Shared accessibility behaviour for modal-like surfaces (Modal / Drawer /
// ConfirmDialog / page sidebars): move focus in on open, trap Tab within the
// surface, close on Escape, restore focus to the trigger on close, and lock
// body scroll across stacked dialogs. Combined with role="dialog" + aria-modal
// on the container, this makes the background effectively inert for keyboard
// and screen readers.
//
// A shared stack tracks every open surface so that only the topmost one reacts
// to Escape and Tab. Without this, stacked overlays (e.g. a ConfirmDialog
// opened from inside a Drawer) would all close on a single Escape and fight
// over focus.

let openDialogCount = 0;
const dialogStack: Array<RefObject<HTMLElement | null>> = [];

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
  // Stack membership + body scroll lock. Depends only on open state so that
  // re-renders (e.g. a new onEscape identity) never reorder the stack or
  // flicker the scroll lock.
  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }
    dialogStack.push(containerRef);
    openDialogCount += 1;
    if (openDialogCount === 1) {
      document.body.style.overflow = 'hidden';
    }
    return () => {
      const index = dialogStack.lastIndexOf(containerRef);
      if (index >= 0) {
        dialogStack.splice(index, 1);
      }
      openDialogCount -= 1;
      if (openDialogCount === 0) {
        document.body.style.overflow = '';
      }
    };
  }, [isOpen, containerRef]);

  // Focus move-in / restore and key handling for the topmost dialog.
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

    const handleKeyDown = (event: KeyboardEvent) => {
      const container = containerRef.current;
      // Only the topmost open surface reacts, so stacked overlays don't all
      // close on one Escape or fight over focus.
      if (dialogStack[dialogStack.length - 1] !== containerRef) {
        return;
      }
      if (event.key === 'Escape') {
        // An open popup widget (Select / autocomplete) keeps focus on its
        // trigger with aria-expanded="true"; let it consume Escape to close
        // the popup instead of dismissing the whole dialog.
        const target = event.target instanceof HTMLElement ? event.target : null;
        if (target?.closest('[aria-haspopup][aria-expanded="true"]')) {
          return;
        }
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
      // Only restore focus to a trigger that is still in the document.
      if (previouslyFocused && previouslyFocused.isConnected) {
        previouslyFocused.focus();
      }
    };
  }, [isOpen, containerRef, onEscape, closeOnEscape]);
}
