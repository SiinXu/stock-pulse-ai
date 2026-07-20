import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { CSSProperties, RefObject } from 'react';
import { getOverlayStyle, OVERLAY_Z, type OverlayLayer } from './overlayZ';

export const FIXED_POPUP_GAP_PX = 4;
export const FIXED_POPUP_VIEWPORT_MARGIN_PX = 8;

type PopupEscapeLayer = Extract<OverlayLayer, 'popover' | 'tooltip'>;
type PopupEscapeToken = object;

interface PopupEscapeEntry {
  token: PopupEscapeToken;
  layer: PopupEscapeLayer;
}

const popupEscapeStack: PopupEscapeEntry[] = [];
const fixedPopupOwners = new WeakMap<HTMLElement, HTMLElement>();

export function registerPopupEscapeLayer(
  token: PopupEscapeToken,
  layer: PopupEscapeLayer,
): () => void {
  const entry = { token, layer };
  popupEscapeStack.push(entry);
  return () => {
    const index = popupEscapeStack.indexOf(entry);
    if (index >= 0) popupEscapeStack.splice(index, 1);
  };
}

export function isTopmostPopupEscapeLayer(token: PopupEscapeToken): boolean {
  let topmost: PopupEscapeEntry | undefined;
  for (const entry of popupEscapeStack) {
    if (!topmost || OVERLAY_Z[entry.layer] >= OVERLAY_Z[topmost.layer]) {
      topmost = entry;
    }
  }
  return topmost?.token === token;
}

export function isFixedPopupOwnedBy(container: HTMLElement, target: Element): boolean {
  let popup = target.closest<HTMLElement>('[data-dialog-popup="true"]');
  const visited = new Set<HTMLElement>();
  while (popup && !visited.has(popup)) {
    visited.add(popup);
    const owner = fixedPopupOwners.get(popup);
    if (!owner) {
      popup = popup.parentElement?.closest<HTMLElement>('[data-dialog-popup="true"]') ?? null;
      continue;
    }
    if (container.contains(owner)) return true;
    popup = owner.closest<HTMLElement>('[data-dialog-popup="true"]');
  }
  return false;
}

interface PopupPosition {
  top: number;
  left: number;
  maxHeight: number;
}

interface UseFixedPopupOptions<
  TTrigger extends HTMLElement,
  TPopup extends HTMLElement,
> {
  isOpen: boolean;
  triggerRef: RefObject<TTrigger | null>;
  popupRef: RefObject<TPopup | null>;
  /** Stable value that changes whenever popup content can affect its geometry. */
  contentVersion: unknown;
  constrainWidthToViewport?: boolean;
  placement?: 'auto' | 'top' | 'bottom';
  align?: 'start' | 'end';
}

/**
 * Positions a fixed popup against its trigger and portals it to the nearest
 * dialog (or document body) so clipping and dialog focus traps remain intact.
 */
export const useFixedPopup = <
  TTrigger extends HTMLElement,
  TPopup extends HTMLElement,
>({
  isOpen,
  triggerRef,
  popupRef,
  contentVersion,
  constrainWidthToViewport = false,
  placement = 'auto',
  align = 'start',
}: UseFixedPopupOptions<TTrigger, TPopup>) => {
  const [triggerRect, setTriggerRect] = useState<DOMRect | null>(null);
  const [portalHost, setPortalHost] = useState<HTMLElement | null>(null);
  const [popupPosition, setPopupPosition] = useState<PopupPosition | null>(null);
  const escapeLayerTokenRef = useRef<PopupEscapeToken>({});

  const prepareForOpen = useCallback(() => {
    const trigger = triggerRef.current;
    setPopupPosition(null);
    setTriggerRect(trigger?.getBoundingClientRect() ?? null);
    setPortalHost(
      (trigger?.closest('[data-overlay-dialog="true"]') as HTMLElement | null) ?? document.body,
    );
  }, [triggerRef]);

  const resetPosition = useCallback(() => {
    setPopupPosition(null);
  }, []);

  useLayoutEffect(() => {
    const popup = popupRef.current;
    if (!isOpen || !triggerRect || !popup) {
      return;
    }

    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const popupRect = popup.getBoundingClientRect();
    const maxHeight = Math.max(
      viewportHeight - (FIXED_POPUP_VIEWPORT_MARGIN_PX * 2),
      0,
    );
    const popupHeight = Math.min(popupRect.height, maxHeight);
    const availableBelow = viewportHeight
      - triggerRect.bottom
      - FIXED_POPUP_GAP_PX
      - FIXED_POPUP_VIEWPORT_MARGIN_PX;
    const availableAbove = triggerRect.top
      - FIXED_POPUP_GAP_PX
      - FIXED_POPUP_VIEWPORT_MARGIN_PX;
    const openAbove = placement === 'top'
      || (placement === 'auto' && popupHeight > availableBelow && availableAbove > availableBelow);
    const preferredTop = openAbove
      ? triggerRect.top - FIXED_POPUP_GAP_PX - popupHeight
      : triggerRect.bottom + FIXED_POPUP_GAP_PX;
    const maxTop = Math.max(
      viewportHeight - FIXED_POPUP_VIEWPORT_MARGIN_PX - popupHeight,
      FIXED_POPUP_VIEWPORT_MARGIN_PX,
    );
    const top = Math.min(
      Math.max(preferredTop, FIXED_POPUP_VIEWPORT_MARGIN_PX),
      maxTop,
    );
    const maxLeft = Math.max(
      viewportWidth - FIXED_POPUP_VIEWPORT_MARGIN_PX - popupRect.width,
      FIXED_POPUP_VIEWPORT_MARGIN_PX,
    );
    const preferredLeft = align === 'end'
      ? triggerRect.right - popupRect.width
      : triggerRect.left;
    const left = Math.min(
      Math.max(preferredLeft, FIXED_POPUP_VIEWPORT_MARGIN_PX),
      maxLeft,
    );

    setPopupPosition({ top, left, maxHeight });
  }, [align, contentVersion, isOpen, placement, popupRef, portalHost, triggerRect]);

  useLayoutEffect(() => {
    const popup = popupRef.current;
    const trigger = triggerRef.current;
    if (!isOpen || !portalHost || !popup || !trigger) return undefined;
    fixedPopupOwners.set(popup, trigger);
    return () => {
      fixedPopupOwners.delete(popup);
    };
  }, [isOpen, popupRef, portalHost, triggerRef]);

  useEffect(() => {
    if (!isOpen || !portalHost || !popupRef.current) return undefined;
    return registerPopupEscapeLayer(escapeLayerTokenRef.current, 'popover');
  }, [isOpen, popupRef, portalHost]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const updateTriggerRect = () => {
      setTriggerRect(triggerRef.current?.getBoundingClientRect() ?? null);
    };
    window.addEventListener('scroll', updateTriggerRect, true);
    window.addEventListener('resize', updateTriggerRect);
    return () => {
      window.removeEventListener('scroll', updateTriggerRect, true);
      window.removeEventListener('resize', updateTriggerRect);
    };
  }, [isOpen, triggerRef]);

  const popupStyle: CSSProperties | undefined = triggerRect
    ? getOverlayStyle('popover', {
        top: popupPosition?.top ?? triggerRect.bottom + FIXED_POPUP_GAP_PX,
        left: popupPosition?.left ?? triggerRect.left,
        minWidth: triggerRect.width,
        maxWidth: constrainWidthToViewport
          ? `calc(100vw - ${FIXED_POPUP_VIEWPORT_MARGIN_PX * 2}px)`
          : undefined,
        maxHeight: popupPosition?.maxHeight,
        visibility: popupPosition ? 'visible' : 'hidden',
      })
    : undefined;
  const isTopmostPopup = useCallback(
    () => isTopmostPopupEscapeLayer(escapeLayerTokenRef.current),
    [],
  );

  return {
    portalHost,
    popupStyle,
    prepareForOpen,
    resetPosition,
    isTopmostPopup,
  };
};
