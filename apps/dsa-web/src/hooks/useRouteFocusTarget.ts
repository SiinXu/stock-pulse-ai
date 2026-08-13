// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useContext, useLayoutEffect } from 'react';
import {
  RouteFocusRegistrationContext,
  type RouteFocusTarget,
} from '../contexts/routeFocusContext';

export type { RouteFocusTarget } from '../contexts/routeFocusContext';

/**
 * Register the page H1 for post-navigation focus (#879 F3).
 *
 * Production always mounts RouteFocusCoordinator in App. When the context is
 * missing (isolated unit tests / playground stories), registration is a no-op
 * so page unit tests do not need a full coordinator shell.
 */
export function useRouteFocusTarget({ routeId, headingRef, ready }: RouteFocusTarget): void {
  const context = useContext(RouteFocusRegistrationContext);

  useLayoutEffect(() => {
    if (!context) return undefined;
    return context.register({ routeId, headingRef, ready });
  }, [context, headingRef, ready, routeId]);
}
