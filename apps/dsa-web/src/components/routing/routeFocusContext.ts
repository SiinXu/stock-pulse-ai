// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createContext, type RefObject } from 'react';

export interface RouteFocusTarget {
  routeId: string;
  headingRef: RefObject<HTMLElement | null>;
  ready: boolean;
}

export interface RouteFocusRegistration {
  register: (target: RouteFocusTarget) => () => void;
}

export const RouteFocusRegistrationContext = createContext<RouteFocusRegistration | null>(null);
