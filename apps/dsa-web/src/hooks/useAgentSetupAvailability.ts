// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useEffect, useState } from 'react';
import { systemConfigApi } from '../api/systemConfig';

/**
 * Returns whether Q&A Agent is currently unavailable according to setup status.
 * needs_action: missing API model; optional: user acknowledged Agent-off.
 */
export function useAgentSetupAvailability(): boolean {
  const [agentUnavailable, setAgentUnavailable] = useState(false);

  useEffect(() => {
    let active = true;
    void systemConfigApi.getSetupStatus()
      .then((status) => {
        if (!active) return;
        const agentCheck = status.checks.find((check) => check.key === 'llm_agent');
        setAgentUnavailable(
          agentCheck?.status === 'needs_action' || agentCheck?.status === 'optional',
        );
      })
      .catch(() => {
        if (active) setAgentUnavailable(false);
      });
    return () => {
      active = false;
    };
  }, []);

  return agentUnavailable;
}
