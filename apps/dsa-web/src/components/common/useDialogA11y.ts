import { useCallback, useLayoutEffect, useRef, type RefObject } from 'react';

type OverlayEntry = {
  token: symbol;
  containerRef: RefObject<HTMLElement | null>;
  overlayRef: RefObject<HTMLElement | null>;
  zIndex: number;
  order: number;
};

type ManagedBackgroundState = {
  hadInertAttribute: boolean;
  inert: boolean;
  ariaHidden: string | null;
};

const overlayStack: OverlayEntry[] = [];
const managedBackground = new Map<HTMLElement, ManagedBackgroundState>();
let nextOverlayOrder = 0;
let initialBodyOverflow: string | null = null;

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[contenteditable="true"]',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

interface DialogA11yOptions {
  isOpen: boolean;
  containerRef: RefObject<HTMLElement | null>;
  overlayRef?: RefObject<HTMLElement | null>;
  onEscape?: () => void;
  onCloseBlocked?: () => void;
  closeOnEscape?: boolean;
  dismissDisabled?: boolean;
  zIndex?: number;
}

type DialogA11yResult = {
  requestClose: () => boolean;
};

function getTopOverlay(): OverlayEntry | undefined {
  return overlayStack.reduce<OverlayEntry | undefined>((top, entry) => {
    if (!top || entry.zIndex > top.zIndex || (entry.zIndex === top.zIndex && entry.order > top.order)) {
      return entry;
    }
    return top;
  }, undefined);
}

function isTopOverlay(token: symbol): boolean {
  return getTopOverlay()?.token === token;
}

function restoreManagedBackground(): void {
  managedBackground.forEach((state, element) => {
    element.inert = state.inert;
    if (state.hadInertAttribute) {
      element.setAttribute('inert', '');
    } else {
      element.removeAttribute('inert');
    }
    if (state.ariaHidden === null) {
      element.removeAttribute('aria-hidden');
    } else {
      element.setAttribute('aria-hidden', state.ariaHidden);
    }
  });
  managedBackground.clear();
}

function shouldIgnoreBackgroundElement(element: HTMLElement): boolean {
  return ['SCRIPT', 'STYLE', 'LINK'].includes(element.tagName);
}

function hideBackgroundElement(element: HTMLElement): void {
  if (shouldIgnoreBackgroundElement(element) || managedBackground.has(element)) {
    return;
  }
  managedBackground.set(element, {
    hadInertAttribute: element.hasAttribute('inert'),
    inert: element.inert,
    ariaHidden: element.getAttribute('aria-hidden'),
  });
  element.inert = true;
  element.setAttribute('inert', '');
  element.setAttribute('aria-hidden', 'true');
}

/**
 * Isolate the active overlay without assuming it was portalled. At every DOM
 * level between the surface and body, sibling branches become inert. This also
 * supports legacy inline surfaces while common overlays move through portals.
 */
function reconcileBackgroundIsolation(): void {
  restoreManagedBackground();
  const top = getTopOverlay();
  let activeBranch = top?.overlayRef.current ?? top?.containerRef.current ?? null;

  while (activeBranch && activeBranch !== document.body) {
    const parent = activeBranch.parentElement;
    if (!parent) {
      break;
    }
    Array.from(parent.children).forEach((sibling) => {
      if (sibling !== activeBranch && sibling instanceof HTMLElement) {
        hideBackgroundElement(sibling);
      }
    });
    activeBranch = parent;
  }
}

function registerOverlay(entry: OverlayEntry): void {
  overlayStack.push(entry);
  if (overlayStack.length === 1) {
    initialBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
  }
  reconcileBackgroundIsolation();
}

function unregisterOverlay(token: symbol): void {
  const index = overlayStack.findIndex((entry) => entry.token === token);
  if (index >= 0) {
    overlayStack.splice(index, 1);
  }
  if (overlayStack.length === 0) {
    restoreManagedBackground();
    document.body.style.overflow = initialBodyOverflow ?? '';
    initialBodyOverflow = null;
  } else {
    reconcileBackgroundIsolation();
  }
}

function getFocusable(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter((element) => {
    if (element.hidden || element.closest('[hidden], [inert], [aria-hidden="true"]')) {
      return false;
    }
    const style = window.getComputedStyle(element);
    return style.display !== 'none' && style.visibility !== 'hidden';
  });
}

function popupOwnsEscape(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return Boolean(
    target.closest('[aria-haspopup][aria-expanded="true"]')
    || target.closest('[data-dialog-popup="true"]'),
  );
}

/** Shared stack, focus, dismissal and background-isolation behavior for dialogs. */
export function useDialogA11y({
  isOpen,
  containerRef,
  overlayRef = containerRef,
  onEscape,
  onCloseBlocked,
  closeOnEscape = true,
  dismissDisabled = false,
  zIndex = 0,
}: DialogA11yOptions): DialogA11yResult {
  const tokenRef = useRef(Symbol('overlay'));
  const onEscapeRef = useRef(onEscape);
  const onCloseBlockedRef = useRef(onCloseBlocked);
  const dismissDisabledRef = useRef(dismissDisabled);
  const closeOnEscapeRef = useRef(closeOnEscape);

  onEscapeRef.current = onEscape;
  onCloseBlockedRef.current = onCloseBlocked;
  dismissDisabledRef.current = dismissDisabled;
  closeOnEscapeRef.current = closeOnEscape;

  const requestClose = useCallback((): boolean => {
    if (!isTopOverlay(tokenRef.current)) {
      return false;
    }
    if (dismissDisabledRef.current) {
      onCloseBlockedRef.current?.();
      return false;
    }
    onEscapeRef.current?.();
    return true;
  }, []);

  useLayoutEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    const token = tokenRef.current;
    const previouslyFocused = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    registerOverlay({
      token,
      containerRef,
      overlayRef,
      zIndex,
      order: nextOverlayOrder++,
    });

    const container = containerRef.current;
    if (container && !container.contains(document.activeElement)) {
      (getFocusable(container)[0] ?? container).focus();
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (!isTopOverlay(token)) {
        return;
      }

      if (event.key === 'Escape') {
        if (popupOwnsEscape(event.target)) {
          return;
        }
        if (closeOnEscapeRef.current) {
          event.preventDefault();
          event.stopPropagation();
          // The top overlay may unmount synchronously. Prevent another
          // document listener from seeing the same Escape after the stack has
          // already exposed the underlying surface.
          event.stopImmediatePropagation();
          requestClose();
        }
        return;
      }

      const currentContainer = containerRef.current;
      if (event.key !== 'Tab' || !currentContainer) {
        return;
      }

      const focusables = getFocusable(currentContainer);
      if (focusables.length === 0) {
        event.preventDefault();
        currentContainer.focus();
        return;
      }

      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !currentContainer.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !currentContainer.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown, true);
    return () => {
      document.removeEventListener('keydown', handleKeyDown, true);
      unregisterOverlay(token);
      if (previouslyFocused?.isConnected) {
        previouslyFocused.focus();
      }
    };
  }, [containerRef, isOpen, overlayRef, requestClose, zIndex]);

  return { requestClose };
}
