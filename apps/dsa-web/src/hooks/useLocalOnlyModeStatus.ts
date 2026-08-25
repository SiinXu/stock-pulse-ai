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

export function useLocalOnlyModeStatus(): LocalOnlyModeStatusState {
  const [state, setState] = useState<LocalOnlyModeStatusState>({ status: 'unknown' });

  useEffect(() => {
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
  }, []);

  return state;
}
