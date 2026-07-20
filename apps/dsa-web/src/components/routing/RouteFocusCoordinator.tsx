// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigationType } from 'react-router-dom';
import {
  RouteFocusRegistrationContext,
  type RouteFocusRegistration,
  type RouteFocusTarget,
} from './routeFocusContext';

type RouteFocusEntry = {
  locationKey: string;
  focusKey?: string;
};

type PendingMarker = {
  locationKey: string;
  focusKey: string;
};

type PendingTransition = {
  locationKey: string;
  navigationType: 'PUSH' | 'REPLACE' | 'POP';
};

type RegisteredTarget = {
  target: RouteFocusTarget;
  token: symbol;
};

const MAX_ROUTE_FOCUS_ENTRIES = 100;

function routeFocusElements(focusKey: string): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>('[data-route-focus-key]'))
    .filter((element) => element.dataset.routeFocusKey === focusKey);
}

function isRendered(element: HTMLElement): boolean {
  for (let current: HTMLElement | null = element; current; current = current.parentElement) {
    if (current.hidden || current.hasAttribute('inert')) return false;
    const style = window.getComputedStyle(current);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
  }
  return true;
}

function isFocusableMarker(element: HTMLElement): boolean {
  if (
    !element.isConnected
    || !isRendered(element)
    || element.matches('[disabled], [aria-disabled="true"]')
  ) return false;
  if (element instanceof HTMLAnchorElement) {
    return Boolean(element.href) && !element.download && (!element.target || element.target === '_self');
  }
  if (element instanceof HTMLButtonElement || element instanceof HTMLInputElement || element instanceof HTMLSelectElement || element instanceof HTMLTextAreaElement) {
    return !element.disabled;
  }
  return element.tabIndex >= 0;
}

function uniqueFocusableMarker(focusKey: string): HTMLElement | null {
  const matches = routeFocusElements(focusKey);
  return matches.length === 1 && isFocusableMarker(matches[0]) ? matches[0] : null;
}

function trimEntries(entries: Map<string, RouteFocusEntry>): void {
  while (entries.size > MAX_ROUTE_FOCUS_ENTRIES) {
    const oldestKey = entries.keys().next().value;
    if (typeof oldestKey !== 'string') return;
    entries.delete(oldestKey);
  }
}

export interface RouteFocusCoordinatorProps {
  children: React.ReactNode;
}

export const RouteFocusCoordinator: React.FC<RouteFocusCoordinatorProps> = ({ children }) => {
  const location = useLocation();
  const navigationType = useNavigationType();
  const currentLocationKeyRef = useRef<string | null>(null);
  const entriesRef = useRef(new Map<string, RouteFocusEntry>());
  const pendingMarkerRef = useRef<PendingMarker | null>(null);
  const pendingTransitionRef = useRef<PendingTransition | null>(null);
  const activeTargetRef = useRef<RegisteredTarget | null>(null);
  const [registrationVersion, setRegistrationVersion] = useState(0);

  const clearPendingMarker = useCallback(() => {
    pendingMarkerRef.current = null;
  }, []);

  useEffect(() => {
    const captureMarker = (event: Event) => {
      if (event instanceof MouseEvent && (
        event.button !== 0
        || event.metaKey
        || event.ctrlKey
        || event.altKey
        || event.shiftKey
      )) {
        clearPendingMarker();
        return;
      }

      const target = event.target instanceof Element
        ? event.target.closest<HTMLElement>('[data-route-focus-key]')
        : null;
      const focusKey = target?.dataset.routeFocusKey?.trim();
      const currentLocationKey = currentLocationKeyRef.current;
      if (!target || !focusKey || !currentLocationKey || uniqueFocusableMarker(focusKey) !== target) {
        clearPendingMarker();
        return;
      }

      pendingMarkerRef.current = { locationKey: currentLocationKey, focusKey };
    };

    document.addEventListener('click', captureMarker, true);
    document.addEventListener('change', captureMarker, true);
    return () => {
      document.removeEventListener('click', captureMarker, true);
      document.removeEventListener('change', captureMarker, true);
      clearPendingMarker();
    };
  }, [clearPendingMarker]);

  useLayoutEffect(() => {
    const previousLocationKey = currentLocationKeyRef.current;
    if (previousLocationKey === null) {
      currentLocationKeyRef.current = location.key;
      clearPendingMarker();
      return;
    }
    if (previousLocationKey === location.key) return;

    const marker = pendingMarkerRef.current?.locationKey === previousLocationKey
      ? pendingMarkerRef.current.focusKey
      : undefined;

    if (navigationType === 'REPLACE') {
      entriesRef.current.delete(previousLocationKey);
      entriesRef.current.delete(location.key);
    } else {
      entriesRef.current.set(previousLocationKey, {
        locationKey: previousLocationKey,
        focusKey: marker,
      });
      trimEntries(entriesRef.current);
    }

    currentLocationKeyRef.current = location.key;
    pendingTransitionRef.current = {
      locationKey: location.key,
      navigationType,
    };
    clearPendingMarker();
  }, [clearPendingMarker, location.key, navigationType]);

  const register = useCallback<RouteFocusRegistration['register']>((target) => {
    const token = Symbol(target.routeId);
    activeTargetRef.current = { target, token };
    setRegistrationVersion((version) => version + 1);
    return () => {
      if (activeTargetRef.current?.token === token) {
        activeTargetRef.current = null;
        setRegistrationVersion((version) => version + 1);
      }
    };
  }, []);

  useEffect(() => {
    const transition = pendingTransitionRef.current;
    const registered = activeTargetRef.current;
    const heading = registered?.target.headingRef.current;
    if (
      !transition
      || transition.locationKey !== location.key
      || !registered?.target.ready
      || !heading?.isConnected
    ) {
      return undefined;
    }

    let secondFrame = 0;
    const firstFrame = window.requestAnimationFrame(() => {
      secondFrame = window.requestAnimationFrame(() => {
        if (pendingTransitionRef.current !== transition) return;
        const entry = entriesRef.current.get(location.key);
        const restoreTarget = transition.navigationType === 'POP' && entry?.focusKey
          ? uniqueFocusableMarker(entry.focusKey)
          : null;
        if (restoreTarget) restoreTarget.focus({ preventScroll: true });
        if (!restoreTarget || document.activeElement !== restoreTarget) {
          heading.focus({ preventScroll: true });
        }
        pendingTransitionRef.current = null;
      });
    });

    return () => {
      window.cancelAnimationFrame(firstFrame);
      if (secondFrame) window.cancelAnimationFrame(secondFrame);
    };
  }, [location.key, registrationVersion]);

  const contextValue = useMemo<RouteFocusRegistration>(() => ({ register }), [register]);

  return (
    <RouteFocusRegistrationContext.Provider value={contextValue}>
      {children}
    </RouteFocusRegistrationContext.Provider>
  );
};
