// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { LocalModelRuntimeState, LocalModelRuntimeStatus } from '../../types/localModels';
import type { GenerationBackendStatus, GenerationBackendStatusResponse } from '../../types/systemConfig';

export type HubProbeState = 'loading' | 'idle' | 'error';
export type HubAvailability = 'available' | 'unavailable' | 'not_configured' | 'failed' | 'loading' | 'starting';
export type HubStatusTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral';

export interface HubStatusSummary {
  availability: HubAvailability;
  tone: HubStatusTone;
  pulse?: boolean;
  /** Machine status token for local runtime, or backend id for CLI when present. */
  detailKey?: string;
  failureReason?: string | null;
}

const LOCAL_RUNTIME_STATUS_LABEL_KEYS: Record<LocalModelRuntimeStatus, string> = {
  running: 'runtimeRunning',
  stopped: 'runtimeStopped',
  starting: 'runtimeStarting',
  'not-installed': 'runtimeMissing',
  unavailable: 'runtimeUnavailable',
  error: 'runtimeUnavailable',
  unknown: 'runtimeUnknown',
};

export function localRuntimeStatusLabelKey(status: LocalModelRuntimeStatus | string | undefined): string {
  if (!status) {
    return LOCAL_RUNTIME_STATUS_LABEL_KEYS.unknown;
  }
  return LOCAL_RUNTIME_STATUS_LABEL_KEYS[status as LocalModelRuntimeStatus]
    ?? LOCAL_RUNTIME_STATUS_LABEL_KEYS.unknown;
}

/**
 * Map local-model runtime probe results to hub availability.
 * Probe transport errors are never treated as available.
 */
export function summarizeLocalRuntimeStatus(
  probeState: HubProbeState,
  runtime: LocalModelRuntimeState | null,
  failureReason?: string | null,
): HubStatusSummary {
  if (probeState === 'loading' && !runtime) {
    return { availability: 'loading', tone: 'neutral', pulse: true };
  }
  if (probeState === 'error') {
    return {
      availability: 'failed',
      tone: 'danger',
      failureReason: failureReason?.trim() || null,
    };
  }
  if (!runtime) {
    return { availability: 'failed', tone: 'danger', failureReason: failureReason?.trim() || null };
  }

  switch (runtime.status) {
    case 'running':
      return {
        availability: 'available',
        tone: 'success',
        detailKey: runtime.status,
      };
    case 'starting':
      return {
        availability: 'starting',
        tone: 'warning',
        pulse: true,
        detailKey: runtime.status,
      };
    case 'not-installed':
      return {
        availability: 'not_configured',
        tone: 'neutral',
        detailKey: runtime.status,
      };
    case 'stopped':
    case 'unavailable':
    case 'error':
      return {
        availability: 'unavailable',
        tone: 'danger',
        detailKey: runtime.status,
      };
    default:
      // unknown / unexpected — never default to available
      return {
        availability: 'unavailable',
        tone: 'neutral',
        detailKey: runtime.status || 'unknown',
      };
  }
}

/**
 * Map generation-backend status to local-CLI hub availability.
 * Failures and unconfigured cloud paths are explicit; never default to available.
 */
export function summarizeLocalCliStatus(
  probeState: HubProbeState,
  status: GenerationBackendStatusResponse | null,
  failureReason?: string | null,
): HubStatusSummary {
  if (probeState === 'loading' && !status) {
    return { availability: 'loading', tone: 'neutral', pulse: true };
  }
  if (probeState === 'error') {
    return {
      availability: 'failed',
      tone: 'danger',
      failureReason: failureReason?.trim() || null,
    };
  }
  if (!status?.primary) {
    return {
      availability: 'failed',
      tone: 'danger',
      failureReason: failureReason?.trim() || null,
    };
  }

  const primary: GenerationBackendStatus = status.primary;
  if (primary.backendType !== 'local_cli') {
    return {
      availability: 'not_configured',
      tone: 'neutral',
      detailKey: primary.backendId,
    };
  }

  if (primary.healthStatus === 'failed' || !primary.available) {
    const reason = [primary.lastErrorCode, primary.lastErrorMessage]
      .filter((part): part is string => Boolean(part && part.trim()))
      .join(': ');
    return {
      availability: 'unavailable',
      tone: 'danger',
      detailKey: primary.backendId,
      failureReason: reason || failureReason?.trim() || null,
    };
  }

  if (primary.healthStatus === 'passed' || primary.available) {
    // available without a smoke test still means the CLI was detected; health "passed"
    // is stronger. Never promote failed rows.
    return {
      availability: 'available',
      tone: primary.healthStatus === 'passed' ? 'success' : 'info',
      detailKey: primary.backendId,
    };
  }

  return {
    availability: 'unavailable',
    tone: 'neutral',
    detailKey: primary.backendId,
    failureReason: primary.lastErrorMessage || null,
  };
}

export function formatHubCheckedAt(checkedAtMs: number | null, locale: string): string | null {
  if (checkedAtMs === null || !Number.isFinite(checkedAtMs)) {
    return null;
  }
  try {
    return new Date(checkedAtMs).toLocaleString(locale);
  } catch {
    return new Date(checkedAtMs).toISOString();
  }
}
