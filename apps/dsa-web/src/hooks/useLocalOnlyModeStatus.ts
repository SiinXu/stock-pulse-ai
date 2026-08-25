// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useEffect, useState } from 'react';
import { outboundActivityApi } from '../api/outboundActivity';

/**
 * Shell/Settings status of GET /api/v1/security/local-only via the existing
 * outboundActivityApi.getLocalOnlyStatus() path.
 *
 * Unknown (loading or request failure) is distinct from enabled=false so
 * callers cannot treat a missing answer as protection.
 */
export type LocalOnlyModeStatusState =
  | { status: 'unknown' }
  | { status: 'off' }
  | { status: 'on' };

export type UseLocalOnlyModeStatusOptions = {
  /** Playground preview skips the live endpoint. */
  enabled?: boolean;
};

export function useLocalOnlyModeStatus(
  options: UseLocalOnlyModeStatusOptions = {},
): LocalOnlyModeStatusState {
  const fetchEnabled = options.enabled ?? true;
  const [state, setState] = useState<LocalOnlyModeStatusState>({ status: 'unknown' });

  useEffect(() => {
    if (!fetchEnabled) {
      return undefined;
    }
    let cancelled = false;
    void outboundActivityApi.getLocalOnlyStatus()
      .then((result) => {
        if (cancelled) return;
        setState(result.enabled === true ? { status: 'on' } : { status: 'off' });
      })
      .catch(() => {
        if (cancelled) return;
        setState({ status: 'unknown' });
      });
    return () => {
      cancelled = true;
    };
  }, [fetchEnabled]);

  return state;
}
