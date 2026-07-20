// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useContext, useLayoutEffect } from 'react';
import {
  RouteFocusRegistrationContext,
  type RouteFocusTarget,
} from '../components/routing/routeFocusContext';

export type { RouteFocusTarget } from '../components/routing/routeFocusContext';

export function useRouteFocusTarget({ routeId, headingRef, ready }: RouteFocusTarget): void {
  const context = useContext(RouteFocusRegistrationContext);
  if (!context) {
    throw new Error('useRouteFocusTarget must be used inside RouteFocusCoordinator');
  }

  useLayoutEffect(
    () => context.register({ routeId, headingRef, ready }),
    [context, headingRef, ready, routeId],
  );
}
