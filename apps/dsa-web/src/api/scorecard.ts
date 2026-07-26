// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import apiClient, { locallyRecoverableResourceConfig } from './index';
import { toCamelCase } from './utils';
import type { SignalScorecardResponse } from '../types/scorecard';

export const scorecardApi = {
  /**
   * Fetch the opt-in public scorecard. When SIGNAL_SCORECARD_PUBLIC_ENABLED is
   * false the backend returns 404; callers should treat that as disabled.
   */
  async getPublic(): Promise<SignalScorecardResponse> {
    // Keep a disabled/404 scorecard inside Settings instead of forcing logout
    // navigation when the public route is intentionally closed.
    const response = await apiClient.get(
      '/api/v1/scorecard',
      locallyRecoverableResourceConfig(),
    );
    return toCamelCase<SignalScorecardResponse>(response.data);
  },
};
