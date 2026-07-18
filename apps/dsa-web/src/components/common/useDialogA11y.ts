// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useEffect, useRef, type RefObject } from 'react';

// Shared accessibility behaviour for modal-like surfaces (Modal / Drawer /
// ConfirmDialog / page sidebars): move focus in on open, trap Tab within the
// surface, close on Escape, restore focus to the trigger on close, and lock
// body scroll across stacked dialogs. Background application roots and lower
// overlay roots receive native inert plus aria-hidden while a surface is open.
//
// A shared stack tracks every open surface so that only the topmost one reacts
// to Escape and Tab. Without this, stacked overlays (e.g. a ConfirmDialog
// opened from inside a Drawer) would all close on a single Escape and fight
// over focus.

const dialogStack: Array<RefObject<HTMLElement | null>> = [];
const isolationState = new Map<HTMLElement, { inert: boolean; ariaHidden: string | null }>();
let previousBodyOverflow: string | null = null;

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

function restoreIsolationState(element: HTMLElement): void {
  const previous = isolationState.get(element);
  if (!previous) {
    return;
  }
  if (previous.inert) {
    element.setAttribute('inert', '');
  } else {
    element.removeAttribute('inert');
  }
  if (previous.ariaHidden === null) {
    element.removeAttribute('aria-hidden');
  } else {
    element.setAttribute('aria-hidden', previous.ariaHidden);
  }
}

function syncDocumentIsolation(): void {
  if (dialogStack.length === 0) {
    isolationState.forEach((_, element) => restoreIsolationState(element));
    isolationState.clear();
    if (previousBodyOverflow !== null) {
      document.body.style.overflow = previousBodyOverflow;
      previousBodyOverflow = null;
    }
    return;
  }

  if (previousBodyOverflow === null) {
    previousBodyOverflow = document.body.style.overflow;
  }
  document.body.style.overflow = 'hidden';

  const topContainer = dialogStack[dialogStack.length - 1]?.current;
  const topOverlayRoot = topContainer?.closest<HTMLElement>('[data-overlay-root]') ?? null;

  Array.from(document.body.children).forEach((child) => {
    if (!(child instanceof HTMLElement)) {
      return;
    }
    if (!isolationState.has(child)) {
      isolationState.set(child, {
        inert: child.hasAttribute('inert'),
        ariaHidden: child.getAttribute('aria-hidden'),
      });
    }

    if (topOverlayRoot && child.contains(topOverlayRoot)) {
      restoreIsolationState(child);
      return;
    }
    child.setAttribute('inert', '');
    child.setAttribute('aria-hidden', 'true');
  });
}

export function useDialogA11y({
  isOpen,
  containerRef,
  onEscape,
  closeOnEscape = true,
}: DialogA11yOptions): void {
  const onEscapeRef = useRef(onEscape);
  const closeOnEscapeRef = useRef(closeOnEscape);

  useEffect(() => {
    onEscapeRef.current = onEscape;
    closeOnEscapeRef.current = closeOnEscape;
  }, [onEscape, closeOnEscape]);

  // Stack registration, focus movement and key handling share one stable open
  // lifecycle. Changing callback identities must not reorder the stack or
  // restore focus while the dialog remains open.
  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    const previouslyFocused = document.activeElement as HTMLElement | null;
    dialogStack.push(containerRef);

    const container = containerRef.current;
    if (container && !container.contains(document.activeElement)) {
      const first = getFocusable(container)[0];
      (first ?? container).focus();
    }
    syncDocumentIsolation();

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
        if (
          target?.closest('[aria-haspopup][aria-expanded="true"]')
          || target?.closest('[data-dialog-popup="true"]')
        ) {
          return;
        }
        if (closeOnEscapeRef.current && onEscapeRef.current) {
          event.preventDefault();
          event.stopPropagation();
          onEscapeRef.current();
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
      const wasTopmost = dialogStack[dialogStack.length - 1] === containerRef;
      document.removeEventListener('keydown', handleKeyDown, true);
      const index = dialogStack.lastIndexOf(containerRef);
      if (index >= 0) {
        dialogStack.splice(index, 1);
      }
      syncDocumentIsolation();

      if (!wasTopmost) {
        return;
      }
      const nextTopContainer = dialogStack[dialogStack.length - 1]?.current ?? null;
      if (
        previouslyFocused
        && previouslyFocused.isConnected
        && (!nextTopContainer || nextTopContainer.contains(previouslyFocused))
      ) {
        previouslyFocused.focus();
      } else if (nextTopContainer) {
        const first = getFocusable(nextTopContainer)[0];
        (first ?? nextTopContainer).focus();
      }
    };
  }, [isOpen, containerRef]);
}
